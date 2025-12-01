package handler

import (
	"bitmap-approach/internal/config"
	"bitmap-approach/internal/service"
	"bitmap-approach/internal/vertica"
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

	host, port, database, username, password := config.VerticaConfig()
	if host == "" || port == "" || database == "" || username == "" || password == "" {
		log.Printf("Error: Vertica environment variables are not set")
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Vertica environment variables are not set. Required: VERTICA_HOST, VERTICA_PORT, VERTICA_DATABASE, VERTICA_USERNAME, VERTICA_PASSWORD"})
		return
	}

	log.Printf("Connecting to Vertica: %s@%s:%s/%s", username, host, port, database)
	verticaClient, err := vertica.NewClient(host, port, database, username, password)
	if err != nil {
		log.Printf("Error creating Vertica client: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create Vertica client: " + err.Error()})
		return
	}
	defer verticaClient.Close()
	log.Printf("Successfully connected to Vertica")

	pairs := make([][2]string, 0, len(listR)*len(listS))
	for _, val1 := range listR {
		for _, val2 := range listS {
			pairs = append(pairs, [2]string{val1, val2})
		}
	}
	log.Printf("Generated %d pairs", len(pairs))

	log.Printf("Skipping table_id prefiltering for Vertica")
	var tableIDs []uint64

	allValues := append(listR, listS...)
	log.Printf("Loading table rows for %d values...", len(allValues))
	tableRows, err := verticaClient.LoadTableRows(tableIDs, allValues, 0)
	if err != nil {
		log.Printf("Error loading table rows: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to load table rows: " + err.Error()})
		return
	}
	log.Printf("Loaded %d table rows", len(tableRows))

	log.Printf("Creating bitmaps for all values...")
	bitmapStore := service.NewBitmapStore(tableRows)
	log.Printf("Created bitmap store")

	log.Printf("Calculating pair table counts from bitmaps...")
	pairTableCounts := bitmapStore.CalculatePairTableCounts(pairs)
	log.Printf("Calculated pair table counts for %d pairs", len(pairTableCounts))

	log.Printf("Calculating quad scores...")
	quadCounts, err := service.CalculateQuadScores(listR, listS, bitmapStore)
	if err != nil {
		log.Printf("Error calculating quad scores: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to calculate quad scores: " + err.Error()})
		return
	}
	log.Printf("Calculated %d quad counts", len(quadCounts))

	log.Printf("Getting total table count...")
	totalTables, err := verticaClient.GetTotalTableCount()
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
