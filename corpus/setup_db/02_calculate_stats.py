import os
import sys
from pathlib import Path


# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import duckdb
from loguru import logger
from backend.services import get_db_connection


def main():
    con = get_db_connection()

    calculate_stats_rs(con)
    calculate_stats_cs(con)

    con.close()
    logger.info("All statistics (RS-JP & CS-JP) computed and indexed.")


def calculate_stats_rs(con: duckdb.DuckDBPyConnection) -> None:
    # --- 1. Compute Value Counts (|T(r_i)|) ---
    logger.info("Computing value counts (values_index)...")
    con.execute("DROP TABLE IF EXISTS values_index;")
    con.execute(
        """
                CREATE TABLE values_index AS
                WITH distinct_values AS (
                    -- Find unique value/table pairs first
                    SELECT DISTINCT value, table_id
                    FROM cells)
                SELECT value,
                       -- Count the distinct pairs
                       COUNT(*) AS num_tables
                FROM distinct_values
                GROUP BY value
                HAVING num_tables >= 2; -- Pruning
                """
    )
    con.commit()
    con.execute("CREATE INDEX IF NOT EXISTS idx_values_val ON values_index(value);")
    con.commit()
    logger.info("Created values_index")

    # --- 2. Compute Co-occurrence Counts (|T(r_i, s_j)|) ---
    # Filter cells to only those with values in values_index (removing rare values)
    logger.info("Creating temp_filtered_cells...")
    con.execute("DROP TABLE IF EXISTS temp_filtered_cells;")
    con.execute(
        """
                CREATE TEMPORARY TABLE temp_filtered_cells AS
                SELECT c.table_id, c.row_id, c.value
                FROM cells c
                JOIN values_index v ON c.value = v.value;
                """
    )
    con.commit()
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_temp_filtered_cells ON temp_filtered_cells(table_id, row_id);"
    )
    con.commit()

    # Log reduction achieved by filtering
    original_count = con.execute("SELECT COUNT(*) FROM cells").fetchone()[0]
    filtered_count = con.execute("SELECT COUNT(*) FROM temp_filtered_cells").fetchone()[
        0
    ]
    reduction_percent = ((original_count - filtered_count) / original_count) * 100
    logger.debug(
        f"Removed {original_count - filtered_count:,} rows (a {reduction_percent:.2f}% reduction)."
    )
    # Compute row co-occurrences based on filtered cells
    # pairs are canonicalized, v1 < v2
    logger.info("Computing row co-occurrences (row_cooccurrences)...")
    con.execute("DROP TABLE IF EXISTS row_cooccurrences;")
    con.execute(
        """
                CREATE TABLE row_cooccurrences AS
                WITH distinct_pairs_by_table AS (SELECT DISTINCT LEAST(c1.value, c2.value)    AS v1,
                                                                 GREATEST(c1.value, c2.value) AS v2,
                                                                 c1.table_id
                                                 FROM temp_filtered_cells c1
                                                          JOIN temp_filtered_cells c2
                                                               ON c1.table_id = c2.table_id
                                                                   AND c1.row_id = c2.row_id
                                                                   AND c1.value < c2.value)
                SELECT v1,
                       v2,
                       COUNT(*) AS num_tables
                FROM distinct_pairs_by_table
                GROUP BY v1, v2
                HAVING num_tables >= 2;
                """
    )
    con.commit()

    # Clean up temp tables
    con.execute("DROP TABLE IF EXISTS temp_filtered_cells;")
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_pairs_v1v2 ON row_cooccurrences(v1, v2);"
    )
    con.commit()
    logger.info("Created row_cooccurrences.")

    # --- 3. Pre-compute PMI Scores (RS-JP) ---
    # Get total number of tables (n)
    logger.info("Pre-computing row-level PMI scores (for RS-JP)...")
    try:
        N = con.execute("SELECT COUNT(DISTINCT table_id) FROM tables_meta;").fetchone()[
            0
        ]
    except Exception as e:
        logger.error(f"Could not get table count. Error: {e}")
        return

    if N == 0:
        logger.error("No tables found in tables_meta. Run ingestion script first.")
        return

    logger.debug(f"Total tables (N) = {N}")

    con.execute("DROP TABLE IF EXISTS pmi_scores;")
    con.execute(
        f"""
        CREATE TABLE pmi_scores AS
        SELECT
            rc.v1,
            rc.v2,
            rc.num_tables AS num_tables_pair,
            v1s.num_tables AS num_tables_v1,
            v2s.num_tables AS num_tables_v2,
            LOG(({N} * rc.num_tables) / (v1s.num_tables * v2s.num_tables)) AS pmi
        FROM row_cooccurrences rc
        JOIN values_index v1s ON rc.v1 = v1s.value
        JOIN values_index v2s ON rc.v2 = v2s.value;
        """
    )
    con.commit()
    con.execute("CREATE INDEX IF NOT EXISTS idx_pmi_v1v2 ON pmi_scores(v1, v2);")
    con.commit()
    logger.info("Created pmi_scores (RS-JP).")

    # --- 4. Compute Normalized PMI (NPMI) ---
    logger.info("Computing normalized PMI scores (npmi_scores)...")
    con.execute("DROP TABLE IF EXISTS npmi_scores;")
    con.execute(
        f"""
            CREATE TABLE npmi_scores AS
            SELECT
                v1,
                v2,
                pmi,
                -- Handle the p(x, y) = 1 edge case, which results in 0/0
                CASE
                    WHEN num_tables_pair = {N} THEN 1.0
                    ELSE pmi / -LOG(num_tables_pair / CAST({N} AS DOUBLE))
                END AS npmi
            FROM pmi_scores;
        """
    )
    con.commit()

    # Add an index, just like for the other tables
    con.execute("CREATE INDEX IF NOT EXISTS idx_npmi_v1v2 ON npmi_scores(v1, v2);")
    con.commit()
    logger.info("Created npmi_scores for row score.")
    return


def calculate_stats_cs(con: duckdb.DuckDBPyConnection) -> None:
    """
    Calculate Column-Level PMI statistics for CS-JP-LP algorithm.

    For each pair of value-pairs ((ri, sj), (rk, sl)) where i ≠ k, we compute:
    - T((ri, sj), (rk, sl)) = set of tables where:
      1. ri and sj are in the same row
      2. rk and sl are in the same row
      3. ri and rk are in the same column
      4. sj and sl are in the same column

    Then calculate: PMI((ri, sj), (rk, sl)) = log(p((ri, sj), (rk, sl)) / (p(ri, sj) × p(rk, sl)))
    """

    # Get total number of tables (N)
    logger.info("Computing column-level PMI scores (for CS-JP-LP)...")
    try:
        N = con.execute("SELECT COUNT(DISTINCT table_id) FROM tables_meta;").fetchone()[
            0
        ]
    except Exception as e:
        logger.error(f"Could not get table count. Error: {e}")
        return

    if N == 0:
        logger.error("No tables found in tables_meta. Run ingestion script first.")
        return

    logger.debug(f"Total tables (N) = {N}")

    # --- 1. Compute Column-Level Co-occurrences ---
    # Find all instances where two value pairs (ri, sj) and (rk, sl) satisfy:
    # - ri and sj are in the same row
    # - rk and sl are in the same row
    # - ri and rk are in the same column (col_id)
    # - sj and sl are in the same column (col_id)
    #
    # IMPORTANT: We canonicalize the pairs to avoid double-counting.
    # Since PMI((ri,sj),(rk,sl)) = PMI((rk,sl),(ri,sj)) (symmetric),
    # we only store one direction using lexicographic ordering.
    # This prevents the objective function from counting the same pair twice.
    logger.info("Computing column-level co-occurrences...")

    con.execute("DROP TABLE IF EXISTS column_cooccurrences;")
    con.execute(
        """
        CREATE TABLE column_cooccurrences AS
        WITH distinct_pairs_by_table AS (
            SELECT DISTINCT
                c1.value AS ri,
                c2.value AS sj,
                c3.value AS rk,
                c4.value AS sl,
                c1.table_id
            FROM cells c1
            JOIN cells c2 ON c1.table_id = c2.table_id
                         AND c1.row_id = c2.row_id
                         AND c1.col_id < c2.col_id  -- ri and sj in same row, different columns
            JOIN cells c3 ON c1.table_id = c3.table_id
                         AND c1.col_id = c3.col_id  -- ri and rk in same column
                         AND c1.row_id < c3.row_id  -- different rows (i ≠ k)
            JOIN cells c4 ON c1.table_id = c4.table_id
                         AND c2.col_id = c4.col_id  -- sj and sl in same column
                         AND c3.row_id = c4.row_id  -- rk and sl in same row
        ),
        canonicalized AS (
            -- Canonicalize: ensure (ri,sj) comes "before" (rk,sl) to avoid duplicates
            -- We use lexicographic ordering: if ri < rk, or if ri = rk and sj < sl
            SELECT DISTINCT
                CASE WHEN ri < rk OR (ri = rk AND sj <= sl)
                     THEN ri ELSE rk END AS ri,
                CASE WHEN ri < rk OR (ri = rk AND sj <= sl)
                     THEN sj ELSE sl END AS sj,
                CASE WHEN ri < rk OR (ri = rk AND sj <= sl)
                     THEN rk ELSE ri END AS rk,
                CASE WHEN ri < rk OR (ri = rk AND sj <= sl)
                     THEN sl ELSE sj END AS sl,
                table_id
            FROM distinct_pairs_by_table
        )
        SELECT
            ri,
            sj,
            rk,
            sl,
            COUNT(*) AS num_tables
        FROM canonicalized
        GROUP BY ri, sj, rk, sl
        HAVING num_tables >= 2;  -- Pruning: only keep pairs that occur in at least 2 tables
    """
    )
    con.commit()
    logger.info("Created column_cooccurrences.")

    # --- 2. Calculate Column-Level PMI Scores ---
    # PMI((ri, sj), (rk, sl)) = log(p((ri, sj), (rk, sl)) / (p(ri, sj) × p(rk, sl)))
    # Where:
    # - p(ri, sj) = |T(ri, sj)| / N  (from row_cooccurrences)
    # - p(rk, sl) = |T(rk, sl)| / N  (from row_cooccurrences)
    # - p((ri, sj), (rk, sl)) = |T((ri, sj), (rk, sl))| / N  (from column_cooccurrences)
    logger.info("Computing column-level PMI scores...")

    con.execute("DROP TABLE IF EXISTS column_pmi_scores;")
    con.execute(
        f"""
        CREATE TABLE column_pmi_scores AS
        SELECT
            cc.ri,
            cc.sj,
            cc.rk,
            cc.sl,
            cc.num_tables AS num_tables_quad,
            rc1.num_tables AS num_tables_ri_sj,
            rc2.num_tables AS num_tables_rk_sl,
            LOG(({N} * cc.num_tables) / (rc1.num_tables * rc2.num_tables)) AS column_pmi
        FROM column_cooccurrences cc
        -- Join with row_cooccurrences to get p(ri, sj)
        JOIN row_cooccurrences rc1 ON (
            (cc.ri = rc1.v1 AND cc.sj = rc1.v2) OR
            (cc.ri = rc1.v2 AND cc.sj = rc1.v1)
        )
        -- Join with row_cooccurrences to get p(rk, sl)
        JOIN row_cooccurrences rc2 ON (
            (cc.rk = rc2.v1 AND cc.sl = rc2.v2) OR
            (cc.rk = rc2.v2 AND cc.sl = rc2.v1)
        )
        WHERE LOG(({N} * cc.num_tables) / (rc1.num_tables * rc2.num_tables)) > 0;  -- Only keep positive PMI
    """
    )
    con.commit()

    # Create index for efficient lookups
    con.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_column_pmi_all
        ON column_pmi_scores(ri, sj, rk, sl);
    """
    )
    con.commit()
    logger.info("Created column_pmi_scores (CS-JP-LP).")

    return


if __name__ == "__main__":
    main()
