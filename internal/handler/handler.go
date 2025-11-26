package handler

import (
	"bitmap-approach/internal/config"
	"bitmap-approach/internal/duckdb"
	"bitmap-approach/internal/service"
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
	var req CalculateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request body: " + err.Error()})
		return
	}

	if len(req.ListR) == 0 || len(req.ListS) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "listR and listS must not be empty"})
		return
	}

	listR := normalizeStrings(req.ListR)
	listS := normalizeStrings(req.ListS)

	duckDBPath := config.DuckDBPath()
	if duckDBPath == "" {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "DUCKDB_PATH environment variable is not set"})
		return
	}

	duckClient, err := duckdb.NewClient(duckDBPath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create DuckDB client: " + err.Error()})
		return
	}
	defer duckClient.Close()

	pairs := make([][2]string, 0, len(listR)*len(listS))
	for _, val1 := range listR {
		for _, val2 := range listS {
			pairs = append(pairs, [2]string{val1, val2})
		}
	}

	tableIDs, err := duckClient.FetchRelevantTableIDs(pairs)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch table IDs: " + err.Error()})
		return
	}

	allValues := append(listR, listS...)
	tableRows, err := duckClient.LoadTableRows(tableIDs, allValues, 0)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to load table rows: " + err.Error()})
		return
	}

	quadCounts, err := service.CalculateQuadScores(listR, listS, tableRows)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to calculate quad scores: " + err.Error()})
		return
	}

	pairTableCounts, err := duckClient.FetchPairTableCounts(pairs)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch pair table counts: " + err.Error()})
		return
	}

	totalTables, err := duckClient.GetTotalTableCount()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get total table count: " + err.Error()})
		return
	}

	results, err := service.CalculatePMIForQuadScores(quadCounts, pairTableCounts, totalTables)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to calculate PMI: " + err.Error()})
		return
	}

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

	c.JSON(http.StatusOK, response)
}
