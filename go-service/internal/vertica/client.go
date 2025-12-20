package vertica

import (
	"bitmap-approach/internal/model"
	"database/sql"
	"fmt"
	"strings"
	"sync"
	"time"

	_ "github.com/vertica/vertica-sql-go"
)

type Client struct {
	db              *sql.DB
	totalTableCount int
}

func NewClient(host, port, database, username, password string) (*Client, error) {
	connStr := fmt.Sprintf("vertica://%s:%s@%s:%s/%s",
		username, password, host, port, database)

	db, err := sql.Open("vertica", connStr)
	if err != nil {
		return nil, fmt.Errorf("failed to open Vertica: %w", err)
	}

	// Configure connection pooling for better performance
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)
	db.SetConnMaxIdleTime(1 * time.Minute)

	if err := db.Ping(); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to ping Vertica: %w", err)
	}

	client := &Client{db: db}

	// Fetch total table count during initialization
	query := `SELECT COUNT(DISTINCT tableid) FROM main_tokenized`
	err = db.QueryRow(query).Scan(&client.totalTableCount)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to get total table count: %w", err)
	}

	return client, nil
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
		 FROM main_tokenized /**PROJS('public.inv_index_proj')*/
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
	// Return cached value that was fetched during client initialization
	return c.totalTableCount, nil
}

// LoadTableRowsStreaming streams table rows directly to a processor function
// This avoids loading all rows into memory at once
func (c *Client) LoadTableRowsStreaming(values []string, processor func(model.TableRow) error) error {


	inClause := buildInClause(values)

	query := fmt.Sprintf(
		`SELECT tableid, rowid, colid, tokenized
		 FROM main_tokenized /**PROJS('public.inv_index_proj')*/
		 WHERE tokenized IN %s`, inClause)

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
				`SELECT tableid, rowid, colid, tokenized
				 FROM main_tokenized /**PROJS('public.inv_index_proj')*/
				 WHERE tokenized IN %s`, inClause)

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
