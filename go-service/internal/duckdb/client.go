package duckdb

import (
	"bitmap-approach/internal/model"
	"database/sql"
	"fmt"
	"strings"
	"sync"

	_ "github.com/marcboeker/go-duckdb"
)

type Client struct {
	db *sql.DB
}

func NewClient(dbPath string) (*Client, error) {
	// Open DuckDB database in read-only mode
	connStr := fmt.Sprintf("%s?access_mode=READ_ONLY", dbPath)
	db, err := sql.Open("duckdb", connStr)
	if err != nil {
		return nil, fmt.Errorf("failed to open DuckDB: %w", err)
	}

	// Configure connection pooling
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)

	if err := db.Ping(); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to ping DuckDB: %w", err)
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
		`SELECT table_id, row_id, col_id, value
		 FROM cells
		 WHERE value IN %s`, inClause)

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
	query := `SELECT COUNT(DISTINCT table_id) FROM cells`

	var count int
	err := c.db.QueryRow(query).Scan(&count)
	if err != nil {
		return 0, fmt.Errorf("failed to get total table count: %w", err)
	}

	return count, nil
}

// LoadTableRowsStreaming streams table rows directly to a processor function
// This avoids loading all rows into memory at once
func (c *Client) LoadTableRowsStreaming(values []string, processor func(model.TableRow) error) error {


	inClause := buildInClause(values)

	query := fmt.Sprintf(
		`SELECT table_id, row_id, col_id, value
		 FROM cells
		 WHERE value IN %s`, inClause)

	rows, err := c.db.Query(query)
	if err != nil {
		return fmt.Errorf("failed to query table rows: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var tableID, rowID, colID uint64
		var value string
		if err := rows.Scan(&tableID, &rowID, &colID, &value); err != nil {
			return fmt.Errorf("failed to scan row: %w", err)
		}

		if err := processor(NewTableRow(tableID, rowID, colID, value)); err != nil {
			return fmt.Errorf("processor error: %w", err)
		}
	}

	if err := rows.Err(); err != nil {
		return fmt.Errorf("error iterating rows: %w", err)
	}

	return nil
}

// LoadTableRowsStreamingBatched splits values into batches and queries in parallel
// This can improve performance for large value sets
func (c *Client) LoadTableRowsStreamingBatched(values []string, processor func(model.TableRow) error, batchSize int) error {
	// Split values into batches
	batches := make([][]string, 0)
	for i := 0; i < len(values); i += batchSize {
		end := i + batchSize
		if end > len(values) {
			end = len(values)
		}
		batches = append(batches, values[i:end])
	}

	// Process batches in parallel with limited concurrency
	maxConcurrent := 4 // Limit concurrent queries to avoid overwhelming database
	semaphore := make(chan struct{}, maxConcurrent)
	errChan := make(chan error, len(batches))
	var wg sync.WaitGroup

	// Mutex to protect processor calls
	var processorMu sync.Mutex

	for _, batch := range batches {
		wg.Add(1)
		go func(batchValues []string) {
			defer wg.Done()

			// Acquire semaphore
			semaphore <- struct{}{}
			defer func() { <-semaphore }()

			inClause := buildInClause(batchValues)
			query := fmt.Sprintf(
				`SELECT table_id, row_id, col_id, value
				 FROM cells
				 WHERE value IN %s`, inClause)

			rows, err := c.db.Query(query)
			if err != nil {
				errChan <- fmt.Errorf("failed to query batch: %w", err)
				return
			}
			defer rows.Close()

			for rows.Next() {
				var tableID, rowID, colID uint64
				var value string
				if err := rows.Scan(&tableID, &rowID, &colID, &value); err != nil {
					errChan <- fmt.Errorf("failed to scan row: %w", err)
					return
				}

				processorMu.Lock()
				err := processor(NewTableRow(tableID, rowID, colID, value))
				processorMu.Unlock()

				if err != nil {
					errChan <- fmt.Errorf("processor error: %w", err)
					return
				}
			}

			if err := rows.Err(); err != nil {
				errChan <- fmt.Errorf("error iterating rows: %w", err)
			}
		}(batch)
	}

	wg.Wait()
	close(errChan)

	// Check for errors
	for err := range errChan {
		if err != nil {
			return err
		}
	}

	return nil
}

func buildInClause(values []string) string {
	quoted := make([]string, len(values))
	for i, v := range values {
		escaped := strings.ReplaceAll(v, "'", "''")
		quoted[i] = "'" + escaped + "'"
	}
	return "(" + strings.Join(quoted, ", ") + ")"
}
