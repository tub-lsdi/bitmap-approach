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
