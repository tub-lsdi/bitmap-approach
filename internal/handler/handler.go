package handler

import (
	"bitmap-approach/internal/config"
	"bitmap-approach/internal/duckdb"
	"bitmap-approach/internal/model"
	"bitmap-approach/internal/service"
	"bitmap-approach/internal/vertica"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

type CalculateRequest struct {
	ListR []string `json:"listR" binding:"required"`
	ListS []string `json:"listS" binding:"required"`
	DB    string   `json:"db"`
}

type QuadScoreResponse struct {
	Quad  string `json:"quad"`
	Count int    `json:"count"`
}

type CalculateResponse struct {
	Results    []QuadScoreResponse `json:"results"`
	TotalFound int                 `json:"total_found"`
	Metadata   MetadataResponse    `json:"metadata"`
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

	dbName := strings.ToLower(req.DB)
	if dbName == "" {
		dbName = "duckdb"
	}
	if dbName != "duckdb" && dbName != "vertica" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "db must be either 'duckdb' or 'vertica'"})
		return
	}

	listR := normalizeStrings(req.ListR)
	listS := normalizeStrings(req.ListS)

	var client model.DBClient
	var err error

	if dbName == "duckdb" {
		duckDBPath := config.DuckDBPath()
		if duckDBPath == "" {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "DUCKDB_PATH environment variable is not set"})
			return
		}
		client, err = duckdb.NewClient(duckDBPath)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create DuckDB client: " + err.Error()})
			return
		}
		defer client.Close()
	} else {
		host, port, database, username, password := config.VerticaConfig()
		if host == "" || port == "" || database == "" || username == "" || password == "" {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Vertica environment variables are not set. Required: VERTICA_HOST, VERTICA_PORT, VERTICA_DATABASE, VERTICA_USERNAME, VERTICA_PASSWORD"})
			return
		}
		client, err = vertica.NewClient(host, port, database, username, password)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create Vertica client: " + err.Error()})
			return
		}
		defer client.Close()
	}

	pairs := make([][2]string, 0, len(listR)*len(listS))
	for _, val1 := range listR {
		for _, val2 := range listS {
			pairs = append(pairs, [2]string{val1, val2})
		}
	}

	var tableIDs []uint64
	if dbName == "duckdb" {
		tableIDs, err = client.FetchRelevantTableIDs(pairs)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch table IDs: " + err.Error()})
			return
		}
	}

	allValues := append(listR, listS...)
	var limit int
	if dbName == "vertica" {
		limit = config.VerticaRowLimit()
	} else {
		limit = 0
	}

	tableRows, err := client.LoadTableRows(tableIDs, allValues, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to load table rows: " + err.Error()})
		return
	}

	results, err := service.CalculateQuadScores(listR, listS, tableRows)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to calculate quad scores: " + err.Error()})
		return
	}

	responseResults := make([]QuadScoreResponse, len(results))
	for i, r := range results {
		responseResults[i] = QuadScoreResponse{
			Quad:  r.Quad,
			Count: r.Count,
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
