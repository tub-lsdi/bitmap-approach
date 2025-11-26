package handler

import (
	"bitmap-approach/internal/config"
	"bitmap-approach/internal/duckdb"
	"bitmap-approach/internal/service"
	"log"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

type CalculateRequest struct {
	ListR []string `json:"listR" binding:"required"`
	ListS []string `json:"listS" binding:"required"`
}

type QuadPMIResponse struct {
	Quad string  `json:"quad"`
	PMI  float64 `json:"pmi"`
}

type CalculateResponse struct {
	Results    []QuadPMIResponse `json:"results"`
	TotalFound int               `json:"total_found"`
	Metadata   MetadataResponse  `json:"metadata"`
}

type MetadataResponse struct {
	ListRCardinality int `json:"listR_cardinality"`
	ListSCardinality int `json:"listS_cardinality"`
	PairsGenerated   int `json:"pairs_generated"`
	TableRowsLoaded  int `json:"table_rows_loaded"`
}

func normalizeStrings(strs []string) []string {
	normalized := make([]string, len(strs))
	for i, s := range strs {
		normalized[i] = strings.ToLower(strings.TrimSpace(s))
	}
	return normalized
}

func CalculateQuadScores(c *gin.Context) {
	log.Printf("Received request to calculate quad scores")

	var req CalculateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		log.Printf("Error parsing request body: %v", err)
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request body: " + err.Error()})
		return
	}

	log.Printf("Request parsed: listR=%d items, listS=%d items", len(req.ListR), len(req.ListS))

	if len(req.ListR) == 0 || len(req.ListS) == 0 {
		log.Printf("Error: empty lists - listR=%d, listS=%d", len(req.ListR), len(req.ListS))
		c.JSON(http.StatusBadRequest, gin.H{"error": "listR and listS must not be empty"})
		return
	}

	listR := normalizeStrings(req.ListR)
	listS := normalizeStrings(req.ListS)
	log.Printf("Normalized lists: listR=%d items, listS=%d items", len(listR), len(listS))

	duckDBPath := config.DuckDBPath()
	if duckDBPath == "" {
		log.Printf("Error: DUCKDB_PATH environment variable is not set")
		c.JSON(http.StatusInternalServerError, gin.H{"error": "DUCKDB_PATH environment variable is not set"})
		return
	}

	log.Printf("Connecting to DuckDB at: %s", duckDBPath)
	duckClient, err := duckdb.NewClient(duckDBPath)
	if err != nil {
		log.Printf("Error creating DuckDB client: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create DuckDB client: " + err.Error()})
		return
	}
	defer duckClient.Close()
	log.Printf("Successfully connected to DuckDB")

	pairs := make([][2]string, 0, len(listR)*len(listS))
	for _, val1 := range listR {
		for _, val2 := range listS {
			pairs = append(pairs, [2]string{val1, val2})
		}
	}
	log.Printf("Generated %d pairs", len(pairs))

	log.Printf("Fetching relevant table IDs...")
	tableIDs, err := duckClient.FetchRelevantTableIDs(pairs)
	if err != nil {
		log.Printf("Error fetching table IDs: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch table IDs: " + err.Error()})
		return
	}
	log.Printf("Found %d relevant table IDs", len(tableIDs))

	allValues := append(listR, listS...)
	log.Printf("Loading table rows for %d values...", len(allValues))
	tableRows, err := duckClient.LoadTableRows(tableIDs, allValues, 0)
	if err != nil {
		log.Printf("Error loading table rows: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to load table rows: " + err.Error()})
		return
	}
	log.Printf("Loaded %d table rows", len(tableRows))

	log.Printf("Calculating quad scores...")
	quadCounts, err := service.CalculateQuadScores(listR, listS, tableRows)
	if err != nil {
		log.Printf("Error calculating quad scores: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to calculate quad scores: " + err.Error()})
		return
	}
	log.Printf("Calculated %d quad counts", len(quadCounts))

	log.Printf("Fetching pair table counts...")
	pairTableCounts, err := duckClient.FetchPairTableCounts(pairs)
	if err != nil {
		log.Printf("Error fetching pair table counts: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch pair table counts: " + err.Error()})
		return
	}
	log.Printf("Found pair table counts for %d pairs", len(pairTableCounts))

	log.Printf("Getting total table count...")
	totalTables, err := duckClient.GetTotalTableCount()
	if err != nil {
		log.Printf("Error getting total table count: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get total table count: " + err.Error()})
		return
	}
	log.Printf("Total tables: %d", totalTables)

	log.Printf("Calculating PMI for %d quad counts...", len(quadCounts))
	results, err := service.CalculatePMIForQuadScores(quadCounts, pairTableCounts, totalTables)
	if err != nil {
		log.Printf("Error calculating PMI: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to calculate PMI: " + err.Error()})
		return
	}
	log.Printf("Calculated PMI for %d quads", len(results))

	responseResults := make([]QuadPMIResponse, len(results))
	for i, r := range results {
		responseResults[i] = QuadPMIResponse{
			Quad: r.Quad.String(),
			PMI:  r.PMI,
		}
	}

	response := CalculateResponse{
		Results:    responseResults,
		TotalFound: len(results),
		Metadata: MetadataResponse{
			ListRCardinality: len(listR),
			ListSCardinality: len(listS),
			PairsGenerated:   len(pairs),
			TableRowsLoaded:  len(tableRows),
		},
	}

	log.Printf("Returning response with %d results", len(results))
	c.JSON(http.StatusOK, response)
}
