package vertica

import (
	"bitmap-approach/internal/model"
	"database/sql"
	"fmt"
	"strings"

	_ "github.com/vertica/vertica-sql-go"
)

type Client struct {
	db *sql.DB
}

func NewClient(host, port, database, username, password string) (*Client, error) {
	connStr := fmt.Sprintf("vertica://%s:%s@%s:%s/%s",
		username, password, host, port, database)

	db, err := sql.Open("vertica", connStr)
	if err != nil {
		return nil, fmt.Errorf("failed to open Vertica: %w", err)
	}

	if err := db.Ping(); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to ping Vertica: %w", err)
	}

	return &Client{db: db}, nil
}

func (c *Client) Close() error {
	return c.db.Close()
}

func (c *Client) FetchRelevantTableIDs(pairs [][2]string) ([]uint64, error) {
	return nil, nil
}

func (c *Client) LoadTableRows(tableIDs []uint64, values []string, limit int) ([]model.TableRow, error) {
	inClause := buildInClause(values)

	query := fmt.Sprintf(
		`SELECT tableid, rowid, colid, tokenized
		 FROM main_tokenized
		 WHERE tokenized IN %s`, inClause)

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

func (c *Client) FetchPairTableCounts(pairs [][2]string) (map[[2]string]int, error) {
	if len(pairs) == 0 {
		return make(map[[2]string]int), nil
	}

	valuesParts := make([]string, len(pairs))
	for i, pair := range pairs {
		r_i := strings.ReplaceAll(pair[0], "'", "''")
		s_j := strings.ReplaceAll(pair[1], "'", "''")
		valuesParts[i] = fmt.Sprintf("('%s', '%s')", r_i, s_j)
	}
	valuesClause := strings.Join(valuesParts, ", ")

	query := fmt.Sprintf(`
		WITH pairs AS (
			SELECT * FROM (VALUES %s) AS t(r_i, s_j)
		),
		all_values AS (
			SELECT r_i AS val FROM pairs
			UNION
			SELECT s_j FROM pairs
		),
		filtered_cells AS (
			SELECT *
			FROM main_tokenized
			WHERE tokenized IN (SELECT val FROM all_values)
		),
		pair_matches AS (
			SELECT DISTINCT
				p.r_i,
				p.s_j,
				f1.tableid
			FROM pairs p
			JOIN filtered_cells f1 ON f1.tokenized = p.r_i
			JOIN filtered_cells f2 ON f2.tokenized = p.s_j
			   AND f2.tableid = f1.tableid
			   AND f2.rowid = f1.rowid
		)
		SELECT
			r_i,
			s_j,
			COUNT(DISTINCT tableid) AS table_count
		FROM pair_matches
		GROUP BY r_i, s_j
		ORDER BY r_i, s_j`, valuesClause)

	rows, err := c.db.Query(query)
	if err != nil {
		return nil, fmt.Errorf("failed to execute pair table counts query: %w", err)
	}
	defer rows.Close()

	result := make(map[[2]string]int)
	for rows.Next() {
		var r_i, s_j string
		var tableCount int
		if err := rows.Scan(&r_i, &s_j, &tableCount); err != nil {
			return nil, fmt.Errorf("failed to scan row: %w", err)
		}
		pair := [2]string{r_i, s_j}
		result[pair] = tableCount
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating rows: %w", err)
	}

	return result, nil
}

func (c *Client) GetTotalTableCount() (int, error) {
	query := `SELECT COUNT(DISTINCT tableid) FROM main_tokenized`

	var count int
	err := c.db.QueryRow(query).Scan(&count)
	if err != nil {
		return 0, fmt.Errorf("failed to get total table count: %w", err)
	}

	return count, nil
}

func buildInClause(values []string) string {
	quoted := make([]string, len(values))
	for i, v := range values {
		escaped := strings.ReplaceAll(v, "'", "''")
		quoted[i] = "'" + escaped + "'"
	}
	return "(" + strings.Join(quoted, ", ") + ")"
}
