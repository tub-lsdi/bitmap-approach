package service

import (
	"fmt"
	"log"
	"math"
	"sort"

	"github.com/RoaringBitmap/roaring/v2/roaring64"
)

// PairPMI represents a pair with its PMI score
type PairPMI struct {
	R_i string
	S_j string
	PMI float64
}

// RowPMIStats contains statistics about the PMI calculation
type RowPMIStats struct {
	TotalPairs    int
	ValidPairs    int
	ZerosFiltered int
}

// CalculateRowPMIsWithBitmaps calculates NPMI (Normalized PMI) scores for all pairs from listR × listS using bitmaps
// Returns NPMI scores sorted by descending NPMI value (range: -1 to 1, where 1 = perfect co-occurrence)
func CalculateRowPMIsWithBitmaps(listR, listS []string, bitmapStore *BitmapStore, totalTables int) ([]PairPMI, RowPMIStats, error) {
	if totalTables <= 0 {
		return nil, RowPMIStats{}, fmt.Errorf("totalTables must be greater than 0")
	}

	log.Printf("Calculating row NPMI scores using bitmaps for %d x %d pairs...", len(listR), len(listS))

	// Generate all pairs from listR × listS
	pairs := make([][2]string, 0, len(listR)*len(listS))
	for _, r := range listR {
		for _, s := range listS {
			pairs = append(pairs, [2]string{r, s})
		}
	}
	totalPairs := len(pairs)
	log.Printf("Generated %d pairs", totalPairs)

	// Calculate pair co-occurrence counts using bitmaps
	pairCounts := bitmapStore.CalculatePairTableCounts(pairs)
	log.Printf("Calculated co-occurrence counts for %d pairs", len(pairCounts))

	// Calculate individual value frequencies (count of tables where each value appears in any row)
	valueCounts := make(map[string]int)
	for _, r := range listR {
		rowBitmap := bitmapStore.GetRowBitmap(r)
		tableBitmap := bitmapStore.positionsToTableBitmapCached(rowBitmap)
		valueCounts[r] = int(tableBitmap.GetCardinality())
	}
	for _, s := range listS {
		if _, exists := valueCounts[s]; !exists {
			rowBitmap := bitmapStore.GetRowBitmap(s)
			tableBitmap := bitmapStore.positionsToTableBitmapCached(rowBitmap)
			valueCounts[s] = int(tableBitmap.GetCardinality())
		}
	}
	log.Printf("Calculated value frequencies for %d unique values", len(valueCounts))

	// Calculate NPMI scores
	results := make([]PairPMI, 0, len(pairCounts))
	zerosFiltered := 0

	for pair, pairCount := range pairCounts {
		rI, sJ := pair[0], pair[1]

		// Get individual value counts
		countRI, okRI := valueCounts[rI]
		countSJ, okSJ := valueCounts[sJ]

		if !okRI || !okSJ || countRI == 0 || countSJ == 0 || pairCount == 0 {
			zerosFiltered++
			continue
		}

		// Calculate probabilities
		jointProb := float64(pairCount) / float64(totalTables)
		marginalProbRI := float64(countRI) / float64(totalTables)
		marginalProbSJ := float64(countSJ) / float64(totalTables)

		// Calculate PMI
		denominator := marginalProbRI * marginalProbSJ
		if denominator == 0 {
			log.Printf("Warning: zero denominator for pair (%s, %s)", rI, sJ)
			zerosFiltered++
			continue
		}

		pmi := math.Log(jointProb / denominator)

		// Calculate NPMI (Normalized PMI)
		// NPMI = PMI / -log(P(x,y))
		// NPMI ranges from -1 to 1, where 1 indicates perfect co-occurrence
		var npmi float64
		if pairCount == totalTables {
			// Special case: if pair appears in all tables, NPMI = 1.0
			npmi = 1.0
		} else {
			npmi = pmi / -math.Log(jointProb)
		}

		// Filter out invalid values
		if math.IsNaN(npmi) || math.IsInf(npmi, 0) {
			log.Printf("Warning: invalid NPMI value for pair (%s, %s)", rI, sJ)
			zerosFiltered++
			continue
		}

		// Filter out negative NPMI (negative association)
		if npmi <= 0 {
			zerosFiltered++
			continue
		}

		results = append(results, PairPMI{
			R_i: rI,
			S_j: sJ,
			PMI: npmi, // Store NPMI in the PMI field
		})
	}

	// Count pairs with zero co-occurrences (pairs not in pairCounts)
	zerosFiltered += totalPairs - len(pairCounts)

	// Sort by descending NPMI
	sort.Slice(results, func(i, j int) bool {
		return results[i].PMI > results[j].PMI
	})

	stats := RowPMIStats{
		TotalPairs:    totalPairs,
		ValidPairs:    len(results),
		ZerosFiltered: zerosFiltered,
	}

	log.Printf("Calculated NPMI for %d pairs (filtered %d)", len(results), zerosFiltered)

	return results, stats, nil
}

// ComputeRelevantTableIDsForRowPairs finds tables where R and S values co-occur in rows
// This is used to filter bitmaps to only relevant tables before PMI calculation
func ComputeRelevantTableIDsForRowPairs(listR, listS []string, bitmapStore *BitmapStore) *roaring64.Bitmap {
	// This is identical to ComputeRelevantTableIDsCrossPairs but extracted for clarity
	return ComputeRelevantTableIDsCrossPairs(listR, listS, bitmapStore)
}
