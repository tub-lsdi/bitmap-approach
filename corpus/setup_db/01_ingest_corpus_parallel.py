import os
import shutil

import pyarrow as pa
import pyarrow.parquet as pq

from pathlib import Path
from multiprocessing import Pool, cpu_count

import duckdb
from loguru import logger
from tqdm import tqdm

from corpus_utils import stream_json_tables, extract_rows, table_hash
from normalization import NormalizationStrategy, set_normalization_strategy

# Configuration
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
INPUT_DIR = PROJECT_ROOT / "corpus" / "example_data"
TEMP_META_DIR = PROJECT_ROOT / "temp_parquet_meta"
TEMP_CELLS_DIR = PROJECT_ROOT / "temp_parquet_cells"
DB_PATH = PROJECT_ROOT / "corpus.db"
CELL_BATCH_SIZE = 500000  # Increased from 50k to 500k for fewer disk writes
TABLE_BATCH_SIZE = 1000


def get_db_connection() -> duckdb.DuckDBPyConnection:
    """Get connection to DuckDB database."""
    return duckdb.connect(str(DB_PATH))


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

    con.execute(
        """
        CREATE SEQUENCE IF NOT EXISTS table_id_seq START 1;
    """
    )

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


def process_file_to_parquet(file_path: str) -> tuple[str, str, int]:
    """
    Worker function that reads one JSON-L file, processes all tables,
    and writes metadata and cell data to temporary Parquet files.

    Returns a tuple: (file_path, status, tables_processed)
    """
    worker_pid = os.getpid()
    base_name = os.path.basename(file_path)
    logger.info(f"[Worker {worker_pid}] Starting on {base_name}")
    total_tables = 0
    try:
        # memory-efficient way to count non-empty lines
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            total_tables = sum(1 for line in f if line.strip())

    except Exception as e:
        logger.error(f"[Worker {worker_pid}] Could not count lines in {base_name}: {e}")
        return file_path, f"Failed: Could not count lines", 0

    if total_tables == 0:
        logger.info(f"[Worker {worker_pid}] No tables found in {base_name}. Skipping.")
        return file_path, "Success (empty)", 0

    logger.info(
        f"[Worker {worker_pid}] Found {total_tables} total tables in {base_name}."
    )

    meta_batch = []
    cell_batch = []

    meta_batch_count = 0
    cell_batch_count = 0
    tables_processed = 0

    try:
        for table_json in stream_json_tables(file_path):
            rows = extract_rows(table_json)
            if not rows:
                continue

            h = table_hash(rows)
            url = table_json.get("url", "")

            meta_batch.append({"table_hash": h, "source_file": file_path, "url": url})

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

            tables_processed += 1

            # Flush cell batch if it gets too big
            if len(cell_batch) >= CELL_BATCH_SIZE:
                file_name = f"{base_name}_{worker_pid}_cells_{cell_batch_count}.parquet"
                _write_parquet_batch(
                    cell_batch, str(TEMP_CELLS_DIR), file_name, CELL_SCHEMA
                )
                cell_batch = []
                cell_batch_count += 1
                logger.info(
                    f"[Worker {worker_pid}] Progress on {base_name}: "
                    f"{tables_processed}/{total_tables} tables "
                    f"({tables_processed / total_tables:.0%})"
                )

        # Write any remaining data
        if cell_batch:
            file_name = f"{base_name}_{worker_pid}_cells_{cell_batch_count}.parquet"
            _write_parquet_batch(
                cell_batch, str(TEMP_CELLS_DIR), file_name, CELL_SCHEMA
            )

        if meta_batch:
            file_name = f"{base_name}_{worker_pid}_cells_{meta_batch_count}.parquet"
            _write_parquet_batch(
                meta_batch, str(TEMP_META_DIR), file_name, META_SCHEMA
            )

        return file_path, "Success", tables_processed

    except Exception as e:
        logger.error(f"[Worker {worker_pid}] FAILED on {base_name}: {e}")
        return file_path, f"Failed: {e}", tables_processed


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


def main():
    # Gather all .json files recursively
    json_files = [
        os.path.join(root, f)
        for root, _, files in os.walk(str(INPUT_DIR))
        for f in files
        if f.endswith(".json")
    ]

    # Get all .json files in the input directory
    # input_path = Path(INPUT_DIR)
    # json_files = [
    #     str(f) for f in input_path.glob("*.json") if f.is_file()
    # ]

    if not json_files:
        logger.warning(f"No .json files found in {INPUT_DIR}. Exiting.")
        return
    logger.info(f"Found {len(json_files)} .json files to process.")

    # 1. Parallel ETL -> Parquet
    logger.info("--- Starting Phase 1: Parallel ETL to Parquet ---")

    # Clean up temp directories from a previous failed run if they exist
    if os.path.exists(TEMP_META_DIR):
        shutil.rmtree(TEMP_META_DIR)
    if os.path.exists(TEMP_CELLS_DIR):
        shutil.rmtree(TEMP_CELLS_DIR)

    os.makedirs(TEMP_META_DIR, exist_ok=True)
    os.makedirs(TEMP_CELLS_DIR, exist_ok=True)

    num_workers = cpu_count()
    logger.info(f"Starting processing with {num_workers} workers.")

    total_tables_processed = 0

    with Pool(processes=num_workers) as pool:
        results = list(
            tqdm(
                pool.imap_unordered(process_file_to_parquet, json_files),
                total=len(json_files),
                desc="Processing files",
            )
        )

    failed_files = 0
    for file_path, status, tables_processed in results:
        total_tables_processed += tables_processed
        if status != "Success":
            failed_files += 1
            logger.warning(f"File {file_path} failed: {status}")

    logger.info(f"--- Phase 1 Complete ---")
    logger.info(
        f"Processed {total_tables_processed} tables across {len(json_files)} files."
    )
    if failed_files:
        logger.error(f"{failed_files} files failed to process.")

    # 2. Serial DB Ingestion
    logger.info("--- Starting Phase 2: Ingesting Parquet into DuckDB ---")

    try:
        con = get_db_connection()
        create_schema(con)  # Ensure schema is up-to-date

        # Create a staging table for metadata, deduplicating at the source
        logger.info("Ingesting and deduplicating metadata...")
        # prevent ._ parquet files from being mistakenly read (required on macOS)
        meta_dir = Path(TEMP_META_DIR)
        meta_files = [
            str(f)
            for f in meta_dir.glob("*.parquet")
            if f.is_file() and not f.name.startswith("._")
        ]

        if not meta_files:
            logger.warning(
                "No valid meta parquet files found. Skipping meta ingestion."
            )
        else:
            con.execute(
                f"""
                        CREATE TEMP TABLE meta_staging AS
                        SELECT DISTINCT table_hash, source_file, url
                        FROM read_parquet({meta_files});
                    """
            )

        # Insert new metadata. ON CONFLICT handles deduplication.
        con.execute(
            """
                    INSERT INTO tables_meta (table_hash, source_file, url)
                    SELECT table_hash, source_file, url
                    FROM meta_staging
                    ON CONFLICT (table_hash) DO NOTHING;
                    """
        )
        logger.info("Metadata ingestion complete.")

        # Create a staging table for all cell data
        logger.info("Staging cell data...")
        # prevent ._ parquet files from being mistakenly read (required on macOS)
        cells_dir = Path(TEMP_CELLS_DIR)
        cells_files = [
            str(f)
            for f in cells_dir.glob("*.parquet")
            if f.is_file() and not f.name.startswith("._")
        ]
        if not cells_files:
            logger.warning(
                "No valid cell parquet files found. Skipping cell ingestion."
            )
        else:
            con.execute(
                f"""
                        CREATE TEMP TABLE cells_staging AS
                        SELECT * FROM read_parquet({cells_files});
                    """
            )

        # Ingest cells by joining with the meta table
        # This join ensures we only add cells for tables that are
        # actually in the meta table and correctly assigns the new table_id.
        logger.info("Joining and ingesting cell data...")
        con.execute(
            """
                    INSERT INTO cells (table_id, row_id, col_id, value)
                    SELECT m.table_id, s.row_id, s.col_id, s.value
                    FROM cells_staging AS s
                             JOIN tables_meta AS m ON s.table_hash = m.table_hash;
                    """
        )

        # Clean up staging tables
        con.execute("DROP TABLE meta_staging;")
        con.execute("DROP TABLE cells_staging;")

        con.commit()

        total_db_tables = con.execute("SELECT COUNT(*) FROM tables_meta;").fetchone()[0]

        logger.info(f"--- Phase 2 Complete ---")

        logger.info(f"Starting Phase 3: Create Indexes")

        con.execute(
            """
                    CREATE INDEX IF NOT EXISTS idx_cells_table_id ON cells(table_id);
                    """
        )
        con.commit()
        logger.info(f"Created index idx_cells_table_id")

        con.execute(
            """
                    CREATE INDEX IF NOT EXISTS idx_cells_value ON cells(value);
                    """
        )
        con.commit()
        logger.info(f"Created index idx_cells_value")

        con.execute(
            """
                    CREATE INDEX IF NOT EXISTS idx_cells_table_row ON cells(table_id, row_id);
                    """
        )
        con.commit()
        logger.info(f"Created index idx_cells_table_row")

        con.execute(
            """
                    CREATE INDEX IF NOT EXISTS idx_cells_table_col ON cells(table_id, col_id);
                    """
        )
        con.commit()
        logger.info(f"Created index idx_cells_table_col")

        logger.info(f"--- Phase 3 Complete ---")
        con.close()
        logger.info(
            f"✅ Ingestion complete. Total tables in database: {total_db_tables}"
        )

    except Exception as e:
        logger.error(f"Failed during Phase 2 (Database Ingestion): {e}")
        logger.error(
            "Your data is safe in the 'temp_parquet_*' directories. You can re-run the `main` function to restart Phase 2."
        )


if __name__ == "__main__":
    main()
