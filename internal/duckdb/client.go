package duckdb

import (
	"bitmap-approach/internal/model"
	"database/sql"
	"fmt"
	"strings"

	_ "github.com/duckdb/duckdb-go/v2"
)

type Client struct {
	db *sql.DB
}

func NewClient(path string) (*Client, error) {
	db, err := sql.Open("duckdb", path)
	if err != nil {
		return nil, fmt.Errorf("failed to open DuckDB: %w", err)
	}
	return &Client{db: db}, nil
}

func (c *Client) Close() error {
	return c.db.Close()
}

func (c *Client) FetchRelevantTableIDs(pairs [][2]string) ([]uint64, error) {
	valuesParts := make([]string, len(pairs))
	for i, pair := range pairs {
		r_i := strings.ReplaceAll(pair[0], "'", "''")
		s_j := strings.ReplaceAll(pair[1], "'", "''")
		valuesParts[i] = fmt.Sprintf("('%s', '%s')", r_i, s_j)
	}
	valuesClause := strings.Join(valuesParts, ",\n        ")

	query := fmt.Sprintf(`
		WITH pairs AS (
			SELECT * FROM (VALUES
				%s
			) AS t(r_i, s_j)
		),
		-- 1. Collect all unique values
		all_values AS (
			SELECT r_i AS val FROM pairs
			UNION
			SELECT s_j FROM pairs
		),
		-- 2. Filter cells once
		filtered_cells AS (
			SELECT *
			FROM cells
			WHERE value IN (SELECT val FROM all_values)
		),
		-- 3. Find all table_ids where ANY pair co-occurs in the same row
		matches AS (
			SELECT DISTINCT
				f1.table_id
			FROM pairs p
			JOIN filtered_cells f1 ON f1.value = p.r_i
			JOIN filtered_cells f2
				ON f2.value = p.s_j
			AND f2.table_id = f1.table_id
			AND f2.row_id = f1.row_id
		)
		-- 4. Output: one column of table_ids
		SELECT table_id
		FROM matches
		ORDER BY table_id`, valuesClause)

	rows, err := c.db.Query(query)
	if err != nil {
		return nil, fmt.Errorf("failed to execute prefilter query: %w", err)
	}
	defer rows.Close()

	var tableIDs []uint64
	for rows.Next() {
		var tableID uint64
		if err := rows.Scan(&tableID); err != nil {
			return nil, fmt.Errorf("failed to scan table_id: %w", err)
		}
		tableIDs = append(tableIDs, tableID)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating rows: %w", err)
	}

	return tableIDs, nil
}

func (c *Client) LoadTableRows(tableIDs []uint64, values []string) ([]model.TableRow, error) {
	inClause := buildInClause(values)

	query := fmt.Sprintf(
		`SELECT table_id, row_id, col_id, value
		 FROM cells
		 WHERE value IN %s`, inClause)

	if len(tableIDs) > 0 {
		tableIDClause := buildInClauseUint64(tableIDs)
		query += fmt.Sprintf(" AND table_id IN %s", tableIDClause)
	}

	query += " ORDER BY value"

	rows, err := c.db.Query(query)
	if err != nil {
		return nil, fmt.Errorf("failed to query table rows: %w", err)
	}
	defer rows.Close()

	var tableRows []model.TableRow
	for rows.Next() {
		var tableID, rowID, colID uint64
		var value string
		if err := rows.Scan(&tableID, &rowID, &colID, &value); err != nil {
			return nil, fmt.Errorf("failed to scan row: %w", err)
		}
		tableRows = append(tableRows, NewTableRow(tableID, rowID, colID, value))
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating rows: %w", err)
	}

	return tableRows, nil
}

func buildInClause(values []string) string {
	quoted := make([]string, len(values))
	for i, v := range values {
		escaped := strings.ReplaceAll(v, "'", "''")
		quoted[i] = "'" + escaped + "'"
	}
	return "(" + strings.Join(quoted, ", ") + ")"
}

func buildInClauseUint64(values []uint64) string {
	quoted := make([]string, len(values))
	for i, v := range values {
		quoted[i] = fmt.Sprintf("%d", v)
	}
	return "(" + strings.Join(quoted, ", ") + ")"
}
