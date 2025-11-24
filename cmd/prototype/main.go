package main

import (
	"bitmap-approach/internal/config"
	"bitmap-approach/internal/duckdb"
	"bitmap-approach/internal/model"
	"bitmap-approach/internal/service"
	"bitmap-approach/internal/vertica"
	"bufio"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"
)

func loadListsFromCase(caseNum string) ([]string, []string, error) {
	filePath := fmt.Sprintf("benchmark-data/Case%s_input.txt", caseNum)
	file, err := os.Open(filePath)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to open case file: %w", err)
	}
	defer file.Close()

	var listR []string
	var listS []string
	scanner := bufio.NewScanner(file)
	inListR := true

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			inListR = false
			continue
		}
		line = strings.ToLower(line)
		if inListR {
			listR = append(listR, line)
		} else {
			listS = append(listS, line)
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, nil, fmt.Errorf("error reading case file: %w", err)
	}

	return listR, listS, nil
}

func main() {
	caseFlag := flag.String("case", "", "Case number to load lists from (e.g., '1' for Case1_input.txt)")
	dbFlag := flag.String("db", "duckdb", "Database to use: 'duckdb' or 'vertica'")
	flag.Parse()

	if *caseFlag == "" {
		log.Fatal("Error: -case flag is required")
	}

	if *dbFlag != "duckdb" && *dbFlag != "vertica" {
		log.Fatalf("Error: -db must be either 'duckdb' or 'vertica', got '%s'", *dbFlag)
	}

	listR, listS, err := loadListsFromCase(*caseFlag)
	if err != nil {
		log.Fatalf("Failed to load case %s: %v", *caseFlag, err)
	}
	log.Printf("Loaded case %s: ListR cardinality = %d, ListS cardinality = %d\n", *caseFlag, len(listR), len(listS))

	if err := config.Load(); err != nil {
		log.Printf("Warning: failed to load .env file: %v", err)
	}

	var client model.DBClient
	dbName := strings.ToLower(*dbFlag)

	if dbName == "duckdb" {
		duckDBPath := config.DuckDBPath()
		if duckDBPath == "" {
			log.Fatalf("DUCKDB_PATH environment variable is not set")
		}
		var err error
		client, err = duckdb.NewClient(duckDBPath)
		if err != nil {
			log.Fatalf("Failed to create DuckDB client: %v", err)
		}
		log.Printf("Connected to DuckDB: %s\n", duckDBPath)
	} else {
		host, port, database, username, password := config.VerticaConfig()
		if host == "" || port == "" || database == "" || username == "" || password == "" {
			log.Fatalf("Vertica environment variables are not set. Required: VERTICA_HOST, VERTICA_PORT, VERTICA_DATABASE, VERTICA_USERNAME, VERTICA_PASSWORD")
		}
		var err error
		client, err = vertica.NewClient(host, port, database, username, password)
		if err != nil {
			log.Fatalf("Failed to create Vertica client: %v", err)
		}
		log.Printf("Connected to Vertica: %s@%s:%s/%s\n", username, host, port, database)
	}
	defer client.Close()

	log.Println("Generating all pairs...")
	pairs := make([][2]string, 0, len(listR)*len(listS))
	for _, val1 := range listR {
		for _, val2 := range listS {
			pairs = append(pairs, [2]string{val1, val2})
		}
	}
	log.Printf("Generated %d pairs between ListR and ListS\n", len(pairs))

	var tableIDs []uint64
	if dbName == "duckdb" {
		log.Println("Fetching relevant table_ids...")
		var err error
		tableIDs, err = client.FetchRelevantTableIDs(pairs)
		if err != nil {
			log.Fatalf("Failed to fetch table IDs: %v", err)
		}
		log.Printf("Found %d relevant table_ids\n", len(tableIDs))
	} else {
		log.Println("Skipping table_id prefiltering for Vertica")
	}

	log.Printf("Loading data from DB")
	allValues := append(listR, listS...)
	var limit int
	if dbName == "vertica" {
		limit = config.VerticaRowLimit()
		log.Printf("Using Vertica row limit: %d\n", limit)
	} else {
		limit = 0
	}
	tableRows, err := client.LoadTableRows(tableIDs, allValues, limit)
	if err != nil {
		log.Fatalf("Failed to load table rows: %v", err)
	}
	log.Printf("Loaded %d table rows\n", len(tableRows))
	if dbName == "vertica" && len(tableRows) >= limit {
		log.Printf("Warning: Reached row limit (%d) for Vertica", limit)
	}

	log.Println("Calculating quad scores...")
	results, err := service.CalculateQuadScores(listR, listS, tableRows)
	if err != nil {
		log.Fatalf("Failed to calculate quad scores: %v", err)
	}

	log.Printf("Found %d quadruples with non-zero counts\n", len(results))

	top := 20
	if len(results) < top {
		top = len(results)
	}

	log.Println("Top quadruples:")
	for i := 0; i < top; i++ {
		log.Printf("%d. %s => %d\n", i+1, results[i].Quad, results[i].Count)
	}
}
