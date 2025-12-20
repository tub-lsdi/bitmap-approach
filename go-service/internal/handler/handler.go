package handler

import (
	"bitmap-approach/internal/config"
	"bitmap-approach/internal/model"
	"bitmap-approach/internal/service"
	"bitmap-approach/internal/vertica"
	"log"
	"net/http"
	"strings"
	"time"

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

type MetadataResponse struct {
	ListRCardinality int `json:"listR_cardinality"`
	ListSCardinality int `json:"listS_cardinality"`
	PairsGenerated   int `json:"pairs_generated"`
	TableRowsLoaded  int `json:"table_rows_loaded"`
}

type TimingInfo struct {
	Step            string  `json:"step"`
	StartTime       string  `json:"start_time"`
	EndTime         string  `json:"end_time"`
	DurationSeconds float64 `json:"duration_seconds"`
}

type CalculateResponse struct {
	Results    []QuadPMIResponse `json:"results"`
	TotalFound int               `json:"total_found"`
	Metadata   MetadataResponse  `json:"metadata"`
	Timings    []TimingInfo      `json:"timings"`
}

type PairPMIResponse struct {
	R_i string  `json:"r_i"`
	S_j string  `json:"s_j"`
	PMI float64 `json:"pmi"`
}

type RowPMIMetadata struct {
	ListRCardinality int `json:"listR_cardinality"`
	ListSCardinality int `json:"listS_cardinality"`
	TotalPairs       int `json:"total_pairs"`
	ValidPairs       int `json:"valid_pairs"`
	TotalTables      int `json:"total_tables"`
	ZerosFiltered    int `json:"zeros_filtered"`
}

type RowPMIResponse struct {
	Results  []PairPMIResponse `json:"results"`
	Metadata RowPMIMetadata    `json:"metadata"`
	Timings  []TimingInfo      `json:"timings"`
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

	timings := make([]TimingInfo, 0)

	verticaConnectStart := time.Now()
	log.Printf("Connecting to Vertica: %s@%s:%s/%s", username, host, port, database)
	verticaClient, err := vertica.NewClient(host, port, database, username, password)
	if err != nil {
		log.Printf("Error creating Vertica client: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create Vertica client: " + err.Error()})
		return
	}
	defer verticaClient.Close()
	verticaConnectEnd := time.Now()
	log.Printf("Successfully connected to Vertica")
	timings = append(timings, TimingInfo{
		Step:            "vertica_connection",
		StartTime:       verticaConnectStart.Format(time.RFC3339Nano),
		EndTime:         verticaConnectEnd.Format(time.RFC3339Nano),
		DurationSeconds: verticaConnectEnd.Sub(verticaConnectStart).Seconds(),
	})

	pairs := make([][2]string, 0, len(listR)*len(listS))
	for _, val1 := range listR {
		for _, val2 := range listS {
			pairs = append(pairs, [2]string{val1, val2})
		}
	}
	log.Printf("Generated %d pairs", len(pairs))

	allValues := append(listR, listS...)

	// Use streaming approach to load and process data without storing all rows in memory
	createBitmapStart := time.Now()
	log.Printf("Loading and processing table rows for %d values...", len(allValues))
	bitmapStore, tableRowsLoaded, err := service.NewBitmapStoreStreaming(func(processor func(model.TableRow) error) error {
		return verticaClient.LoadTableRowsStreaming(allValues, processor)
	})
	if err != nil {
		log.Printf("Error creating bitmap store: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create bitmap store: " + err.Error()})
		return
	}
	createBitmapEnd := time.Now()
	log.Printf("Created bitmap store")
	timings = append(timings, TimingInfo{
		Step:            "load_and_create_bitmaps",
		StartTime:       createBitmapStart.Format(time.RFC3339Nano),
		EndTime:         createBitmapEnd.Format(time.RFC3339Nano),
		DurationSeconds: createBitmapEnd.Sub(createBitmapStart).Seconds(),
	})

	filterBitmapsStart := time.Now()
	log.Printf("Computing relevant table IDs and filtering bitmaps...")
	relevantTableIDsRS := service.ComputeRelevantTableIDsCrossPairs(listR, listS, bitmapStore)
	bitmapStore.FilterToRelevantTables(relevantTableIDsRS)
	relevantTableIDsInterColumn := service.ComputeRelevantTableIDsInterColumnPairs(listR, listS, bitmapStore)
	bitmapStore.FilterToRelevantTables(relevantTableIDsInterColumn)
	filterBitmapsEnd := time.Now()
	log.Printf("Filtered bitmaps to relevant table IDs")
	timings = append(timings, TimingInfo{
		Step:            "filter_bitmaps_to_relevant_tables",
		StartTime:       filterBitmapsStart.Format(time.RFC3339Nano),
		EndTime:         filterBitmapsEnd.Format(time.RFC3339Nano),
		DurationSeconds: filterBitmapsEnd.Sub(filterBitmapsStart).Seconds(),
	})

	calculatePairCountsStart := time.Now()
	log.Printf("Calculating pair table counts from bitmaps...")
	pairTableCounts := bitmapStore.CalculatePairTableCounts(pairs)
	calculatePairCountsEnd := time.Now()
	log.Printf("Calculated pair table counts for %d pairs", len(pairTableCounts))
	timings = append(timings, TimingInfo{
		Step:            "calculate_pair_table_counts",
		StartTime:       calculatePairCountsStart.Format(time.RFC3339Nano),
		EndTime:         calculatePairCountsEnd.Format(time.RFC3339Nano),
		DurationSeconds: calculatePairCountsEnd.Sub(calculatePairCountsStart).Seconds(),
	})

	calculateQuadScoresStart := time.Now()
	log.Printf("Calculating quad scores...")
	quadCounts, err := service.CalculateQuadScores(listR, listS, bitmapStore)
	if err != nil {
		log.Printf("Error calculating quad scores: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to calculate quad scores: " + err.Error()})
		return
	}
	calculateQuadScoresEnd := time.Now()
	log.Printf("Calculated %d quad counts", len(quadCounts))
	timings = append(timings, TimingInfo{
		Step:            "calculate_quad_scores",
		StartTime:       calculateQuadScoresStart.Format(time.RFC3339Nano),
		EndTime:         calculateQuadScoresEnd.Format(time.RFC3339Nano),
		DurationSeconds: calculateQuadScoresEnd.Sub(calculateQuadScoresStart).Seconds(),
	})

	getTotalTablesStart := time.Now()
	log.Printf("Getting total table count...")
	totalTables, err := verticaClient.GetTotalTableCount()
	if err != nil {
		log.Printf("Error getting total table count: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get total table count: " + err.Error()})
		return
	}
	getTotalTablesEnd := time.Now()
	log.Printf("Total tables: %d", totalTables)
	timings = append(timings, TimingInfo{
		Step:            "get_total_table_count",
		StartTime:       getTotalTablesStart.Format(time.RFC3339Nano),
		EndTime:         getTotalTablesEnd.Format(time.RFC3339Nano),
		DurationSeconds: getTotalTablesEnd.Sub(getTotalTablesStart).Seconds(),
	})

	calculatePMIStart := time.Now()
	log.Printf("Calculating PMI for %d quad counts...", len(quadCounts))
	results, err := service.CalculatePMIForQuadScores(quadCounts, pairTableCounts, totalTables)
	if err != nil {
		log.Printf("Error calculating PMI: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to calculate PMI: " + err.Error()})
		return
	}
	calculatePMIEnd := time.Now()
	log.Printf("Calculated PMI for %d quads", len(results))
	timings = append(timings, TimingInfo{
		Step:            "calculate_pmi_scores",
		StartTime:       calculatePMIStart.Format(time.RFC3339Nano),
		EndTime:         calculatePMIEnd.Format(time.RFC3339Nano),
		DurationSeconds: calculatePMIEnd.Sub(calculatePMIStart).Seconds(),
	})

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
			TableRowsLoaded:  tableRowsLoaded,
		},
		Timings: timings,
	}

	log.Printf("Returning response with %d results", len(results))
	c.JSON(http.StatusOK, response)
}

func CalculateRowPMIs(c *gin.Context) {
	log.Printf("Received request to calculate row PMIs")

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

	timings := make([]TimingInfo, 0)

	verticaConnectStart := time.Now()
	log.Printf("Connecting to Vertica: %s@%s:%s/%s", username, host, port, database)
	verticaClient, err := vertica.NewClient(host, port, database, username, password)
	if err != nil {
		log.Printf("Error creating Vertica client: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create Vertica client: " + err.Error()})
		return
	}
	defer verticaClient.Close()
	verticaConnectEnd := time.Now()
	log.Printf("Successfully connected to Vertica")
	timings = append(timings, TimingInfo{
		Step:            "vertica_connection",
		StartTime:       verticaConnectStart.Format(time.RFC3339Nano),
		EndTime:         verticaConnectEnd.Format(time.RFC3339Nano),
		DurationSeconds: verticaConnectEnd.Sub(verticaConnectStart).Seconds(),
	})

	allValues := append(listR, listS...)

	// Use streaming approach to load and process data without storing all rows in memory
	createBitmapStart := time.Now()
	log.Printf("Loading and processing table rows for %d values...", len(allValues))
	bitmapStore, tableRowsLoaded, err := service.NewBitmapStoreStreaming(func(processor func(model.TableRow) error) error {
		return verticaClient.LoadTableRowsStreaming(allValues, processor)
	})
	if err != nil {
		log.Printf("Error creating bitmap store: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create bitmap store: " + err.Error()})
		return
	}
	createBitmapEnd := time.Now()
	log.Printf("Created bitmap store with %d rows", tableRowsLoaded)
	timings = append(timings, TimingInfo{
		Step:            "load_and_create_bitmaps",
		StartTime:       createBitmapStart.Format(time.RFC3339Nano),
		EndTime:         createBitmapEnd.Format(time.RFC3339Nano),
		DurationSeconds: createBitmapEnd.Sub(createBitmapStart).Seconds(),
	})

	filterBitmapsStart := time.Now()
	log.Printf("Computing relevant table IDs and filtering bitmaps...")
	relevantTableIDs := service.ComputeRelevantTableIDsForRowPairs(listR, listS, bitmapStore)
	bitmapStore.FilterToRelevantTables(relevantTableIDs)
	filterBitmapsEnd := time.Now()
	log.Printf("Filtered bitmaps to %d relevant tables", relevantTableIDs.GetCardinality())
	timings = append(timings, TimingInfo{
		Step:            "filter_bitmaps_to_relevant_tables",
		StartTime:       filterBitmapsStart.Format(time.RFC3339Nano),
		EndTime:         filterBitmapsEnd.Format(time.RFC3339Nano),
		DurationSeconds: filterBitmapsEnd.Sub(filterBitmapsStart).Seconds(),
	})

	getTotalTablesStart := time.Now()
	log.Printf("Getting total table count...")
	totalTables, err := verticaClient.GetTotalTableCount()
	if err != nil {
		log.Printf("Error getting total table count: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get total table count: " + err.Error()})
		return
	}
	getTotalTablesEnd := time.Now()
	log.Printf("Total tables: %d", totalTables)
	timings = append(timings, TimingInfo{
		Step:            "get_total_table_count",
		StartTime:       getTotalTablesStart.Format(time.RFC3339Nano),
		EndTime:         getTotalTablesEnd.Format(time.RFC3339Nano),
		DurationSeconds: getTotalTablesEnd.Sub(getTotalTablesStart).Seconds(),
	})

	calculatePMIStart := time.Now()
	log.Printf("Calculating row NPMI scores with bitmaps...")
	results, stats, err := service.CalculateRowPMIsWithBitmaps(listR, listS, bitmapStore, totalTables)
	if err != nil {
		log.Printf("Error calculating row NPMI scores: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to calculate row NPMI scores: " + err.Error()})
		return
	}
	calculatePMIEnd := time.Now()
	log.Printf("Calculated NPMI for %d pairs", len(results))
	timings = append(timings, TimingInfo{
		Step:            "calculate_pmi_scores",
		StartTime:       calculatePMIStart.Format(time.RFC3339Nano),
		EndTime:         calculatePMIEnd.Format(time.RFC3339Nano),
		DurationSeconds: calculatePMIEnd.Sub(calculatePMIStart).Seconds(),
	})

	responseResults := make([]PairPMIResponse, len(results))
	for i, r := range results {
		responseResults[i] = PairPMIResponse{
			R_i: r.R_i,
			S_j: r.S_j,
			PMI: r.PMI,
		}
	}

	response := RowPMIResponse{
		Results: responseResults,
		Metadata: RowPMIMetadata{
			ListRCardinality: len(listR),
			ListSCardinality: len(listS),
			TotalPairs:       stats.TotalPairs,
			ValidPairs:       stats.ValidPairs,
			TotalTables:      totalTables,
			ZerosFiltered:    stats.ZerosFiltered,
		},
		Timings: timings,
	}

	log.Printf("Returning response with %d results", len(results))
	c.JSON(http.StatusOK, response)
}
