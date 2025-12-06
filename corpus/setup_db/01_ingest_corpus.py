import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import duckdb
from dotenv import load_dotenv
from loguru import logger
import polars as pl
from tqdm import tqdm

from backend.config import settings
from backend.services import get_db_connection
from backend.utils import (
    stream_json_tables,
    extract_rows,
    table_hash,
    set_normalization_strategy,
    NormalizationStrategy,
)

set_normalization_strategy(NormalizationStrategy.ALPHANUMERIC_STRICT)


def create_schema(con: duckdb.DuckDBPyConnection):
    """Creates the core tables for storing corpus metadata and cells."""
    con.execute(
        """
                CREATE TABLE IF NOT EXISTS tables_meta (
                                                           table_id BIGINT,
                                                           table_hash TEXT UNIQUE,
                                                           source_file TEXT,
                                                           url TEXT,
                                                           PRIMARY KEY(table_id)
                    );
                """
    )
    con.execute(
        """
                CREATE TABLE IF NOT EXISTS cells (
                                                     table_id BIGINT,
                                                     row_id INTEGER,
                                                     col_id INTEGER,
                                                     value TEXT
                );
                """
    )
    con.commit()
    logger.info("Schema created successfully.")


def main():
    con = get_db_connection()
    create_schema(con)

    # Load existing hashes to prevent re-inserting tables
    existing_hashes = set(
        h[0] for h in con.execute("SELECT table_hash FROM tables_meta;").fetchall()
    )
    logger.info(f"Found {len(existing_hashes)} existing tables. Resuming ingestion.")

    # Get the next available table_id
    table_counter = con.execute(
        "SELECT COALESCE(MAX(table_id), -1) + 1 FROM tables_meta;"
    ).fetchone()[0]

    cell_batch = []

    json_files = [
        os.path.join(root, f)
        for root, _, files in os.walk(settings.INPUT_DIR)
        for f in files
        if f.endswith(".json")
    ]

    if not json_files:
        logger.warning(f"No .json files found in {settings.INPUT_DIR}. Exiting.")
        return

    logger.info(f"Found {len(json_files)} .json files to process.")

    for file_path in json_files:
        logger.info(f"Processing file: {file_path}")

        # Quickly count total tables for logging progress
        total_tables = 0
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                total_tables = sum(1 for line in f if line.strip())

        except Exception as e:
            logger.error(f"Could not read or count lines in {file_path}: {e}")
            continue

        if total_tables == 0:
            continue

        for table_json in tqdm(
            stream_json_tables(file_path),
            desc=f"Loading {os.path.basename(file_path)}",
            total=total_tables,
        ):
            rows = extract_rows(table_json)
            if not rows:
                logger.debug(
                    f"No rows found in one of the tables in {file_path}. Skipping."
                )
                continue

            h = table_hash(rows)
            if h in existing_hashes:
                continue

            table_id = table_counter
            table_counter += 1
            existing_hashes.add(h)

            url = table_json.get("url", "")
            con.execute(
                "INSERT INTO tables_meta (table_id, table_hash, source_file, url) VALUES (?, ?, ?, ?)",
                (table_id, h, file_path, url),
            )

            # Append table cells to the batch
            for row_id, row in enumerate(rows):
                for col_id, val in enumerate(row):
                    cell_batch.append((table_id, row_id, col_id, val))

            # Flush batch if too large
            if len(cell_batch) >= settings.TABLE_BATCH_SIZE:
                logger.debug(
                    f"{table_counter}/{total_tables - len(existing_hashes)} rows ingested"
                )
                con.executemany("INSERT INTO cells VALUES (?, ?, ?, ?)", cell_batch)
                logger.debug(f"Ingested latest batch")

                cell_batch = []

    # Flush any remaining rows
    if cell_batch:
        # con.executemany("INSERT INTO cells VALUES (?, ?, ?, ?)", cell_batch)
        # speed up with polars code above is the shorter, slightly slower way
        df_cell = pl.DataFrame(
            cell_batch, schema=["table_id", "row_id", "col_id", "value"]
        )
        con.register("cell_batch_df", df_cell)
        con.execute("INSERT INTO cells SELECT * FROM cell_batch_df")

    con.commit()
    con.close()
    logger.info(f"✅ Ingestion complete. Total tables in database: {table_counter}")


if __name__ == "__main__":
    main()
