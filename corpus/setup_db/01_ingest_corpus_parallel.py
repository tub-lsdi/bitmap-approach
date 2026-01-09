import os
import shutil

import pyarrow as pa
import pyarrow.parquet as pq

from pathlib import Path
from multiprocessing import Pool, cpu_count

import duckdb
from loguru import logger
from tqdm import tqdm

from corpus_utils import (
    stream_json_tables,
    extract_rows,
    table_hash,
    extract_rows_from_parquet_records,
)
from normalization import NormalizationStrategy, set_normalization_strategy

# --- Configuration ---
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
INPUT_DIR = PROJECT_ROOT / "corpus" / "example_data"
TEMP_META_DIR = PROJECT_ROOT / "temp_parquet_meta"
TEMP_CELLS_DIR = PROJECT_ROOT / "temp_parquet_cells"
DB_PATH = PROJECT_ROOT / "corpus.db"
DB_TEMP_DIR = PROJECT_ROOT / "duckdb_temp"

# Batching thresholds
CELL_FLUSH_THRESHOLD = 500000
META_FLUSH_THRESHOLD = 50000
FILE_CHUNK_SIZE = 100
NUM_INGESTION_CHUNKS = 4


def get_db_connection() -> duckdb.DuckDBPyConnection:
    """Get connection to DuckDB database."""
    return duckdb.connect(str(DB_PATH), config={"temp_directory": DB_TEMP_DIR})


CELL_SCHEMA = pa.schema(
    [
        ("table_hash", pa.string()),
        ("row_id", pa.int32()),
        ("col_id", pa.int32()),
        ("value", pa.string()),
    ]
)

META_SCHEMA = pa.schema(
    [("table_hash", pa.string()), ("source_file", pa.string()), ("url", pa.string())]
)

set_normalization_strategy(NormalizationStrategy.ALPHANUMERIC_STRICT)


def create_schema(con: duckdb.DuckDBPyConnection):
    """
    Creates the core tables.
    - tables_meta uses BIGSERIAL for auto-incrementing IDs.
    - cells uses a FOREIGN KEY to link to tables_meta.
    """
    con.execute("CREATE SEQUENCE IF NOT EXISTS table_id_seq START 1;")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS tables_meta (
                                                table_id BIGINT PRIMARY KEY DEFAULT nextval('table_id_seq'),
                                                table_hash TEXT UNIQUE,
                                                source_file TEXT,
                                                url TEXT
                                                );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS cells (
                                            table_id BIGINT REFERENCES tables_meta(table_id),
                                            row_id INTEGER,
                                            col_id INTEGER,
                                            value TEXT
                                            );
        """
    )

    con.commit()
    logger.info("Schema created/verified successfully.")


def _write_parquet_batch(
    batch: list, directory: str, file_name: str, schema: pa.Schema
):
    """Helper to write a batch to a compressed Parquet file."""
    if not batch:
        return

    try:
        os.makedirs(directory, exist_ok=True)
        table = pa.Table.from_pylist(batch, schema=schema)
        pq.write_table(table, os.path.join(directory, file_name), compression="ZSTD")
    except Exception as e:
        logger.error(f"Failed to write batch {file_name}: {e}")


def _stream_json_file(file_path):
    """Yields table objects from a JSON file."""
    for table_json in stream_json_tables(file_path):
        yield table_json


def _stream_parquet_file(file_path):
    """
    Yields (rows, url) tuples from a Parquet file.
    Treats the whole parquet file as one 'table' unit for consistency.
    """
    try:
        t = pq.read_table(file_path)
        records = t.to_pylist()
        rows = extract_rows_from_parquet_records(records)
        url = Path(file_path).stem
        yield rows, url
    except Exception as e:
        logger.warning(f"Could not read parquet file {file_path}: {e}")
        return


def chunk_list(data, size):
    """Yield successive chunks from data."""
    for i in range(0, len(data), size):
        yield data[i : i + size]


def process_data_chunk(file_paths: list[str]) -> tuple[int, int, int]:
    """
    Unified worker that processes a list of files (Chunk).
    Handles both JSON and Parquet input.
    """
    worker_pid = os.getpid()

    # Generate a unique ID for this chunk based on the first file's hash
    if not file_paths:
        return 0, 0, 0
    chunk_id = abs(hash(file_paths[0])) % 10000000

    meta_batch = []
    cell_batch = []

    meta_batch_index = 0
    cell_batch_index = 0

    tables_processed_count = 0
    files_processed_count = 0
    failure_count = 0

    for file_path in file_paths:
        try:
            is_json = file_path.endswith(".json")

            if is_json:
                iterator = _stream_json_file(file_path)
            else:
                iterator = _stream_parquet_file(file_path)

            for table_data in iterator:
                if is_json:
                    rows = extract_rows(table_data)
                    url = table_data.get("url", "")
                else:
                    rows, url = table_data

                if not rows:
                    continue

                h = table_hash(rows)

                meta_batch.append(
                    {"table_hash": h, "source_file": file_path, "url": url}
                )

                for row_id, row in enumerate(rows):
                    for col_id, val in enumerate(row):
                        cell_batch.append(
                            {
                                "table_hash": h,
                                "row_id": row_id,
                                "col_id": col_id,
                                "value": val,
                            }
                        )

                tables_processed_count += 1

                # Flush cell batch if it gets too big
                if len(cell_batch) >= CELL_FLUSH_THRESHOLD:
                    file_name = f"chunk_{worker_pid}_{chunk_id}_cells_{cell_batch_index}.parquet"
                    _write_parquet_batch(
                        cell_batch, str(TEMP_CELLS_DIR), file_name, CELL_SCHEMA
                    )
                    cell_batch = []
                    cell_batch_index += 1

                # Flush meta batch if it gets too big
                if len(meta_batch) >= META_FLUSH_THRESHOLD:
                    file_name = (
                        f"chunk_{worker_pid}_{chunk_id}_meta_{meta_batch_index}.parquet"
                    )
                    _write_parquet_batch(
                        meta_batch, str(TEMP_META_DIR), file_name, META_SCHEMA
                    )
                    meta_batch = []
                    meta_batch_index += 1

            files_processed_count += 1

        except Exception as e:
            logger.error(
                f"[Worker {worker_pid}] FAILED on {os.path.basename(file_path)}: {e}"
            )
            failure_count += 1

    # Write any remaining data
    if cell_batch:
        file_name = f"chunk_{worker_pid}_{chunk_id}_cells_{cell_batch_index}.parquet"
        _write_parquet_batch(cell_batch, str(TEMP_CELLS_DIR), file_name, CELL_SCHEMA)

    if meta_batch:
        file_name = f"chunk_{worker_pid}_{chunk_id}_meta_{meta_batch_index}.parquet"
        _write_parquet_batch(meta_batch, str(TEMP_META_DIR), file_name, META_SCHEMA)

    return files_processed_count, tables_processed_count, failure_count


def main():
    # Gather all files recursively
    logger.info("Scanning for files...")
    json_files = [
        os.path.join(root, f)
        for root, _, files in os.walk(str(INPUT_DIR))
        for f in files
        if f.endswith(".json")
    ]
    parquet_files = [
        os.path.join(root, f)
        for root, _, files in os.walk(str(INPUT_DIR))
        for f in files
        if f.endswith(".parquet") and not f.startswith("._")
    ]

    all_files = json_files + parquet_files

    if not all_files:
        logger.warning(f"No .json or .parquet files found in {INPUT_DIR}. Exiting.")
        return

    # 1. Parallel ETL -> Parquet
    logger.info("--- Starting Phase 1: Parallel ETL to Parquet ---")
    logger.info(f"Found {len(json_files)} JSON and {len(parquet_files)} Parquet files.")

    # Clean up temp directories from a previous failed run if they exist
    if os.path.exists(TEMP_META_DIR):
        shutil.rmtree(TEMP_META_DIR)
    if os.path.exists(TEMP_CELLS_DIR):
        shutil.rmtree(TEMP_CELLS_DIR)

    os.makedirs(TEMP_META_DIR, exist_ok=True)
    os.makedirs(TEMP_CELLS_DIR, exist_ok=True)

    # Chunk inputs for better performance
    file_chunks = list(chunk_list(all_files, FILE_CHUNK_SIZE))
    logger.info(
        f"Grouped files into {len(file_chunks)} chunks (size {FILE_CHUNK_SIZE}) for processing."
    )

    num_workers = cpu_count()
    total_tables_processed = 0
    total_failures = 0

    with Pool(processes=num_workers) as pool:
        results = list(
            tqdm(
                pool.imap_unordered(process_data_chunk, file_chunks),
                total=len(file_chunks),
                desc="Processing File Chunks",
            )
        )

        for files_proc, tables_proc, fails in results:
            total_tables_processed += tables_proc
            total_failures += fails

    logger.info(f"--- Phase 1 Complete ---")
    logger.info(
        f"Processed {total_tables_processed} tables. Failures: {total_failures}"
    )

    # 2. Serial DB Ingestion
    logger.info("--- Starting Phase 2: Ingesting Parquet into DuckDB ---")

    try:
        con = get_db_connection()

        # 1. Set Memory Limit to ~80% of RAM (e.g., '12GB' for a 16GB machine)
        # This is CRITICAL. It tells DuckDB to spill to disk rather than crashing.
        con.execute("SET memory_limit='12GB';")
        con.execute(f"SET threads TO {cpu_count()};")

        create_schema(con)

        # --- Metadata (Do this once, it's usually safe) ---
        logger.info("Ingesting and deduplicating metadata...")
        meta_files = [
            str(f) for f in Path(TEMP_META_DIR).glob("*.parquet")
            if f.is_file() and not f.name.startswith("._")
        ]

        if meta_files:
            con.execute(f"""
                    INSERT INTO tables_meta (table_hash, source_file, url)
                    SELECT DISTINCT table_hash, source_file, url
                    FROM read_parquet({meta_files})
                    ON CONFLICT (table_hash) DO NOTHING;
                """)
            con.commit()

            # Analyze is crucial for the Join logic below
            logger.info("Analyzing metadata table...")
            con.execute("ANALYZE tables_meta;")
            con.commit()
        else:
            logger.warning("No valid meta parquet files found.")

        # --- Cell Data (The Optimized Strategy) ---
        logger.info("Ingesting cell data...")
        cells_files = [
            str(f) for f in Path(TEMP_CELLS_DIR).glob("*.parquet")
            if f.is_file() and not f.name.startswith("._")
        ]

        if not cells_files:
            logger.warning("No valid cell parquet files found.")
        else:
            # STRATEGY:
            # Instead of small batches (overhead heavy), we use LARGE CHUNKS.
            # Splitting into ~10 chunks is usually the perfect balance.
            # It amortizes the Join cost while preventing Infinite Transaction Growth.

            # Calculate chunk size (ceiling division)
            chunk_size = (len(cells_files) + NUM_INGESTION_CHUNKS - 1) // NUM_INGESTION_CHUNKS

            logger.info(f"Processing {len(cells_files)} files in {NUM_INGESTION_CHUNKS} chunks of ~{chunk_size} files.")

            with tqdm(total=len(cells_files), desc="Ingesting Cell Chunks") as pbar:
                for i in range(0, len(cells_files), chunk_size):
                    # 1. Get the list of files for this large chunk
                    batch_files = cells_files[i : i + chunk_size]

                    # 2. Direct Stream Insert
                    # We skip 'CREATE TEMP TABLE'. We stream strictly from Parquet.
                    # DuckDB will manage the memory buffering automatically thanks to 'memory_limit'.
                    con.execute(f"""
                            INSERT INTO cells (table_id, row_id, col_id, value)
                            SELECT m.table_id, s.row_id, s.col_id, s.value
                            FROM read_parquet({batch_files}) AS s
                            JOIN tables_meta AS m ON s.table_hash = m.table_hash;
                        """)

                    # 3. Commit
                    # This frees the Transaction Log (WAL) space on disk.
                    con.commit()

                    pbar.update(len(batch_files))


        logger.info(f"--- Phase 2 Complete ---")

        # Check total tables
        total_db_tables = con.execute("SELECT COUNT(*) FROM tables_meta;").fetchone()[0]

        logger.info(f"Starting Phase 3: Create Indexes")

        con.execute("CREATE INDEX IF NOT EXISTS idx_cells_table_id ON cells(table_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cells_value ON cells(value);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cells_table_row ON cells(table_id, row_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cells_table_col ON cells(table_id, col_id);")

        con.commit()
        logger.info(f"--- Phase 3 Complete ---")

        con.close()
        logger.info(f"✅ Ingestion complete. Total tables in database: {total_db_tables}")

    except Exception as e:
        logger.error(f"Failed during Phase 2 (Database Ingestion): {e}")


if __name__ == "__main__":
    main()
