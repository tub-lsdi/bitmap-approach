package service

import (
	"bitmap-approach/internal/model"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"runtime"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"github.com/RoaringBitmap/roaring/v2/roaring64"
)

type Quad [4]string

func (q Quad) String() string {
	return fmt.Sprintf("%s,%s,%s,%s", q[0], q[1], q[2], q[3])
}

func (q Quad) MarshalJSON() ([]byte, error) {
	return json.Marshal(q.String())
}

type QuadCount struct {
	Quad  Quad
	Count int
}

type QuadPMI struct {
	Quad Quad
	PMI  float64
}

type BitmapStore struct {
	rowBitmaps       map[string]*roaring64.Bitmap
	colBitmaps       map[string]*roaring64.Bitmap
	tableBitmapCache sync.Map // thread-safe cache for positionsToTableBitmap results
}

func NewBitmapStore(tableRows []model.TableRow) *BitmapStore {
	// Pre-allocate maps with expected capacity to reduce allocations
	rowBitmaps := make(map[string]*roaring64.Bitmap, 500)
	colBitmaps := make(map[string]*roaring64.Bitmap, 500)

	rowsProcessed := 0
	for _, tableRow := range tableRows {
		tableID := tableRow.TableID()
		rowID := tableRow.RowID()
		colID := tableRow.ColID()
		value := tableRow.Value()

		if _, ok := rowBitmaps[value]; !ok {
			rowBitmaps[value] = roaring64.NewBitmap()
			colBitmaps[value] = roaring64.NewBitmap()
		}

		posRow := (tableID << 32) | rowID
		posCol := (tableID << 32) | colID

		rowBitmaps[value].Add(posRow)
		colBitmaps[value].Add(posCol)
		rowsProcessed++
	}

	log.Printf("Created bitmaps for %d values\n", len(rowBitmaps))
	log.Printf("Processed %d rows\n", rowsProcessed)

	return &BitmapStore{
		rowBitmaps: rowBitmaps,
		colBitmaps: colBitmaps,
	}
}

// NewBitmapStoreStreaming creates a BitmapStore by streaming rows from a data source
// This avoids loading all rows into memory at once, significantly reducing memory usage
// Returns the BitmapStore and the number of rows processed
func NewBitmapStoreStreaming(streamFunc func(func(model.TableRow) error) error) (*BitmapStore, int, error) {
	// Use parallel sharding for faster bitmap population
	numShards := runtime.NumCPU()
	shards := make([]*bitmapShard, numShards)
	for i := 0; i < numShards; i++ {
		shards[i] = &bitmapShard{
			rowBitmaps: make(map[string]*roaring64.Bitmap, 500/numShards),
			colBitmaps: make(map[string]*roaring64.Bitmap, 500/numShards),
		}
	}

	var rowsProcessed atomic.Int64

	err := streamFunc(func(tableRow model.TableRow) error {
		value := tableRow.Value()
		tableID := tableRow.TableID()
		rowID := tableRow.RowID()
		colID := tableRow.ColID()

		// Hash value to determine shard (consistent assignment)
		shardIdx := hashString(value) % uint64(numShards)
		shard := shards[shardIdx]

		shard.mu.Lock()
		if _, ok := shard.rowBitmaps[value]; !ok {
			shard.rowBitmaps[value] = roaring64.NewBitmap()
			shard.colBitmaps[value] = roaring64.NewBitmap()
		}

		posRow := (tableID << 32) | rowID
		posCol := (tableID << 32) | colID

		shard.rowBitmaps[value].Add(posRow)
		shard.colBitmaps[value].Add(posCol)
		shard.mu.Unlock()

		if current := rowsProcessed.Add(1); current%10000000 == 0 {
			log.Printf("Processed %d rows...", current)
		}

		return nil
	})

	if err != nil {
		return nil, 0, fmt.Errorf("error streaming rows: %w", err)
	}

	// Merge shards in parallel
	finalRowBitmaps := make(map[string]*roaring64.Bitmap, 500)
	finalColBitmaps := make(map[string]*roaring64.Bitmap, 500)
	var mergeMu sync.Mutex

	var wg sync.WaitGroup
	for _, shard := range shards {
		wg.Add(1)
		go func(s *bitmapShard) {
			defer wg.Done()
			s.mu.Lock()
			defer s.mu.Unlock()

			for value, rowBitmap := range s.rowBitmaps {
				mergeMu.Lock()
				if existing, ok := finalRowBitmaps[value]; ok {
					existing.Or(rowBitmap)
				} else {
					finalRowBitmaps[value] = rowBitmap
				}
				mergeMu.Unlock()
			}

			for value, colBitmap := range s.colBitmaps {
				mergeMu.Lock()
				if existing, ok := finalColBitmaps[value]; ok {
					existing.Or(colBitmap)
				} else {
					finalColBitmaps[value] = colBitmap
				}
				mergeMu.Unlock()
			}
		}(shard)
	}
	wg.Wait()

	totalRows := int(rowsProcessed.Load())
	log.Printf("Created bitmaps for %d values from %d rows", len(finalRowBitmaps), totalRows)

	return &BitmapStore{
		rowBitmaps: finalRowBitmaps,
		colBitmaps: finalColBitmaps,
	}, totalRows, nil
}

// bitmapShard holds bitmaps for a subset of values
type bitmapShard struct {
	rowBitmaps map[string]*roaring64.Bitmap
	colBitmaps map[string]*roaring64.Bitmap
	mu         sync.Mutex
}

// hashString computes a simple hash for consistent value-to-shard assignment
func hashString(s string) uint64 {
	var hash uint64 = 5381
	for i := 0; i < len(s); i++ {
		hash = ((hash << 5) + hash) + uint64(s[i])
	}
	return hash
}

func (bs *BitmapStore) GetRowBitmap(value string) *roaring64.Bitmap {
	if bm, ok := bs.rowBitmaps[value]; ok {
		return bm
	}
	return roaring64.NewBitmap()
}

func (bs *BitmapStore) GetColBitmap(value string) *roaring64.Bitmap {
	if bm, ok := bs.colBitmaps[value]; ok {
		return bm
	}
	return roaring64.NewBitmap()
}

func (bs *BitmapStore) FilterToRelevantTables(relevantTableIDs *roaring64.Bitmap) {
	// Parallelize filtering across values for significant speedup
	var wg sync.WaitGroup

	// Filter row bitmaps in parallel
	rowValues := make([]string, 0, len(bs.rowBitmaps))
	for value := range bs.rowBitmaps {
		rowValues = append(rowValues, value)
	}

	numWorkers := runtime.NumCPU()
	chunkSize := (len(rowValues) + numWorkers - 1) / numWorkers

	for w := 0; w < numWorkers; w++ {
		start := w * chunkSize
		end := (w + 1) * chunkSize
		if end > len(rowValues) {
			end = len(rowValues)
		}
		if start >= len(rowValues) {
			break
		}

		wg.Add(1)
		go func(values []string) {
			defer wg.Done()
			for _, value := range values {
				if rowBitmap, ok := bs.rowBitmaps[value]; ok {
					bs.rowBitmaps[value] = filterBitmapByTableIDsOptimized(rowBitmap, relevantTableIDs)
				}
			}
		}(rowValues[start:end])
	}

	wg.Wait()

	// Filter column bitmaps in parallel
	colValues := make([]string, 0, len(bs.colBitmaps))
	for value := range bs.colBitmaps {
		colValues = append(colValues, value)
	}

	chunkSize = (len(colValues) + numWorkers - 1) / numWorkers

	for w := 0; w < numWorkers; w++ {
		start := w * chunkSize
		end := (w + 1) * chunkSize
		if end > len(colValues) {
			end = len(colValues)
		}
		if start >= len(colValues) {
			break
		}

		wg.Add(1)
		go func(values []string) {
			defer wg.Done()
			for _, value := range values {
				if colBitmap, ok := bs.colBitmaps[value]; ok {
					bs.colBitmaps[value] = filterBitmapByTableIDsOptimized(colBitmap, relevantTableIDs)
				}
			}
		}(colValues[start:end])
	}

	wg.Wait()
}

// filterBitmapByTableIDsOptimized filters positions to only those with relevant tableIDs
// Uses batched checking to reduce the number of Contains() calls
func filterBitmapByTableIDsOptimized(bitmap *roaring64.Bitmap, relevantTableIDs *roaring64.Bitmap) *roaring64.Bitmap {
	// Extract unique tableIDs from positions
	tableIDSet := make(map[uint64]bool)
	it := bitmap.Iterator()
	for it.HasNext() {
		tableID := it.Next() >> 32
		tableIDSet[tableID] = true
	}

	// Batch check which tableIDs are relevant
	validTableIDs := make(map[uint64]bool, len(tableIDSet))
	for tableID := range tableIDSet {
		if relevantTableIDs.Contains(tableID) {
			validTableIDs[tableID] = true
		}
	}

	// Second pass: add positions with valid tableIDs
	filtered := roaring64.NewBitmap()
	it2 := bitmap.Iterator()
	for it2.HasNext() {
		pos := it2.Next()
		if validTableIDs[pos>>32] {
			filtered.Add(pos)
		}
	}

	return filtered
}

func (bs *BitmapStore) CalculatePairTableCount(pair [2]string) int {
	val1, val2 := pair[0], pair[1]
	row1 := bs.GetRowBitmap(val1)
	row2 := bs.GetRowBitmap(val2)

	rowIntersection := roaring64.And(row1, row2)
	if rowIntersection.GetCardinality() == 0 {
		return 0
	}

	tableBitmap := bs.positionsToTableBitmapCached(rowIntersection)
	return int(tableBitmap.GetCardinality())
}

func (bs *BitmapStore) CalculatePairTableCounts(pairs [][2]string) map[[2]string]int {
	result := make(map[[2]string]int, len(pairs))
	for _, pair := range pairs {
		result[pair] = bs.CalculatePairTableCount(pair)
	}
	return result
}

func CalculateQuadScores(listR, listS []string, bitmapStore *BitmapStore) ([]QuadCount, error) {
	pairs := generateAllPairs(listR, listS)
	pairsR := generateAllPairs(listR, listR)
	pairsS := generateAllPairs(listS, listS)

	whitelist, pairTableIDBitmaps := buildPairWhitelist(pairs, bitmapStore)
	_, pairTableIDBitmapsR := buildPairWhitelistColumn(pairsR, bitmapStore)
	_, pairTableIDBitmapsS := buildPairWhitelistColumn(pairsS, bitmapStore)

	// Use parallel processing with worker pool for significant speedup
	var mu sync.Mutex
	all_counts := make(map[Quad]int)
	var operationsCompleted atomic.Int64
	var lastReportedPercent atomic.Int64
	lastReportedPercent.Store(-1)
	startTime := time.Now()

	// Calculate total operations: sum of (n-i-1) for i from 0 to n-1 = n*(n-1)/2
	totalOperations := int64(len(whitelist)) * int64(len(whitelist)-1) / 2
	log.Printf("Total operations to process: %d (from %d whitelist pairs)", totalOperations, len(whitelist))

	// Create worker pool
	numWorkers := runtime.NumCPU()
	chunkSize := (len(whitelist) + numWorkers - 1) / numWorkers
	var wg sync.WaitGroup

	for w := 0; w < numWorkers; w++ {
		start := w * chunkSize
		end := (w + 1) * chunkSize
		if end > len(whitelist) {
			end = len(whitelist)
		}
		if start >= len(whitelist) {
			break
		}

		wg.Add(1)
		go func(startIdx, endIdx int) {
			defer wg.Done()
			localCounts := make(map[Quad]int)

			for i := startIdx; i < endIdx; i++ {
				pair1 := whitelist[i]
				r_i, s_j := pair1[0], pair1[1]

				for j := i + 1; j < len(whitelist); j++ {
					pair2 := whitelist[j]
					r_k, s_l := pair2[0], pair2[1]

					if r_i != r_k {
						pairR := [2]string{r_i, r_k}
						pairS := [2]string{s_j, s_l}

						_, okR := getPairTableBitmap(pairR, pairTableIDBitmapsR)
						_, okS := getPairTableBitmap(pairS, pairTableIDBitmapsS)
						if !okR || !okS {
							continue
						}

						quad := Quad{r_i, s_j, r_k, s_l}
						count := countTablesForQuadruple([4]string(quad),
							pairTableIDBitmaps, pairTableIDBitmapsR, pairTableIDBitmapsS)

						if count > 0 {
							localCounts[quad] = count
						}
					}

					// Track each operation (inner loop iteration)
					current := operationsCompleted.Add(1)

					// Report progress every 1% (to avoid excessive logging)
					// Use atomic CAS to ensure only one worker reports each percentage
					currentPercent := (current * 100) / totalOperations
					lastPercent := lastReportedPercent.Load()
					if currentPercent > lastPercent && lastReportedPercent.CompareAndSwap(lastPercent, currentPercent) {
						elapsed := time.Since(startTime)
						rate := float64(current) / elapsed.Seconds()
						remaining := time.Duration(float64(totalOperations-current)/rate) * time.Second
						log.Printf("Progress: %d%% (%d/%d operations, %.0f ops/sec, ETA: %v)",
							currentPercent, current, totalOperations, rate, remaining)
					}
				}
			}

			// Merge local results
			mu.Lock()
			for quad, count := range localCounts {
				all_counts[quad] = count
			}
			mu.Unlock()
		}(start, end)
	}

	wg.Wait()
	log.Printf("Completed 100%% - processed %d operations in %v", totalOperations, time.Since(startTime))

	type kv struct {
		Key Quad
		Val int
	}

	filtered := make([]kv, 0, len(all_counts))
	for k, v := range all_counts {
		if v > 0 {
			filtered = append(filtered, kv{Key: k, Val: v})
		}
	}

	sort.Slice(filtered, func(i, j int) bool { return filtered[i].Val > filtered[j].Val })

	results := make([]QuadCount, len(filtered))
	for i, kv := range filtered {
		results[i] = QuadCount{
			Quad:  kv.Key,
			Count: kv.Val,
		}
	}

	return results, nil
}

func countTablesForQuadruple(quad [4]string, pairTableIDBitmaps map[[2]string]*roaring64.Bitmap, pairTableIDBitmapsR map[[2]string]*roaring64.Bitmap, pairTableIDBitmapsS map[[2]string]*roaring64.Bitmap) int {
	a, b, c, d := quad[0], quad[1], quad[2], quad[3]

	pairAB := [2]string{a, b}
	pairCD := [2]string{c, d}

	tablesRowAB, okAB := pairTableIDBitmaps[pairAB]
	if !okAB || tablesRowAB.GetCardinality() == 0 {
		return 0
	}

	tablesRowCD, okCD := pairTableIDBitmaps[pairCD]
	if !okCD || tablesRowCD.GetCardinality() == 0 {
		return 0
	}

	// Early exit: check row intersection before looking up column bitmaps
	rowIntersection := roaring64.And(tablesRowAB, tablesRowCD)
	if rowIntersection.GetCardinality() == 0 {
		return 0 // Saves 2 more bitmap lookups + 2 ANDs
	}

	pairAC := [2]string{a, c}
	pairBD := [2]string{b, d}

	tablesColAC, okAC := getPairTableBitmap(pairAC, pairTableIDBitmapsR)
	if !okAC || tablesColAC.GetCardinality() == 0 {
		return 0
	}

	tablesColBD, okBD := getPairTableBitmap(pairBD, pairTableIDBitmapsS)
	if !okBD || tablesColBD.GetCardinality() == 0 {
		return 0
	}

	// Early exit: check column intersection before final AND
	colIntersection := roaring64.And(tablesColAC, tablesColBD)
	if colIntersection.GetCardinality() == 0 {
		return 0
	}

	// Final intersection
	final := roaring64.And(rowIntersection, colIntersection)
	return int(final.GetCardinality())
}

func generateAllPairs(list1, list2 []string) [][2]string {
	pairs := make([][2]string, 0, len(list1)*len(list2))
	for _, val1 := range list1 {
		for _, val2 := range list2 {
			pairs = append(pairs, [2]string{val1, val2})
		}
	}
	return pairs
}

func buildPairWhitelist(pairs [][2]string, bitmapStore *BitmapStore) ([][2]string, map[[2]string]*roaring64.Bitmap) {
	type result struct {
		pair        [2]string
		tableBitmap *roaring64.Bitmap
	}

	resultChan := make(chan result, len(pairs))

	// Process in parallel
	numWorkers := runtime.NumCPU()
	chunkSize := (len(pairs) + numWorkers - 1) / numWorkers
	var wg sync.WaitGroup

	for w := 0; w < numWorkers; w++ {
		start := w * chunkSize
		end := (w + 1) * chunkSize
		if end > len(pairs) {
			end = len(pairs)
		}
		if start >= len(pairs) {
			break
		}

		wg.Add(1)
		go func(pairSlice [][2]string) {
			defer wg.Done()

			for _, pair := range pairSlice {
				val1, val2 := pair[0], pair[1]
				row1 := bitmapStore.GetRowBitmap(val1)
				row2 := bitmapStore.GetRowBitmap(val2)

				overlap := roaring64.And(row1, row2)
				if overlap.GetCardinality() > 0 {
					tableIDBitmap := bitmapStore.positionsToTableBitmapCached(overlap)
					resultChan <- result{pair: pair, tableBitmap: tableIDBitmap}
				}
			}
		}(pairs[start:end])
	}

	go func() {
		wg.Wait()
		close(resultChan)
	}()

	// Collect results
	whitelist := make([][2]string, 0, len(pairs)/10)
	pairTableIDBitmaps := make(map[[2]string]*roaring64.Bitmap)

	for res := range resultChan {
		whitelist = append(whitelist, res.pair)
		pairTableIDBitmaps[res.pair] = res.tableBitmap
	}

	log.Printf("Whitelisted %d pairs\n", len(whitelist))

	return whitelist, pairTableIDBitmaps
}

func buildPairWhitelistColumn(pairs [][2]string, bitmapStore *BitmapStore) ([][2]string, map[[2]string]*roaring64.Bitmap) {
	type result struct {
		pair        [2]string
		tableBitmap *roaring64.Bitmap
	}

	resultChan := make(chan result, len(pairs))

	// Process in parallel
	numWorkers := runtime.NumCPU()
	chunkSize := (len(pairs) + numWorkers - 1) / numWorkers
	var wg sync.WaitGroup

	for w := 0; w < numWorkers; w++ {
		start := w * chunkSize
		end := (w + 1) * chunkSize
		if end > len(pairs) {
			end = len(pairs)
		}
		if start >= len(pairs) {
			break
		}

		wg.Add(1)
		go func(pairSlice [][2]string) {
			defer wg.Done()

			for _, pair := range pairSlice {
				val1, val2 := pair[0], pair[1]
				col1 := bitmapStore.GetColBitmap(val1)
				col2 := bitmapStore.GetColBitmap(val2)

				overlap := roaring64.And(col1, col2)
				if overlap.GetCardinality() > 0 {
					tableIDBitmap := bitmapStore.positionsToTableBitmapCached(overlap)
					resultChan <- result{pair: pair, tableBitmap: tableIDBitmap}
				}
			}
		}(pairs[start:end])
	}

	go func() {
		wg.Wait()
		close(resultChan)
	}()

	// Collect results
	whitelist := make([][2]string, 0, len(pairs)/10)
	pairTableIDBitmaps := make(map[[2]string]*roaring64.Bitmap)

	for res := range resultChan {
		whitelist = append(whitelist, res.pair)
		pairTableIDBitmaps[res.pair] = res.tableBitmap
	}

	log.Printf("Whitelisted %d column pairs\n", len(whitelist))

	return whitelist, pairTableIDBitmaps
}

func getPairTableBitmap(pair [2]string, pairTableIDBitmaps map[[2]string]*roaring64.Bitmap) (*roaring64.Bitmap, bool) {
	if bm, ok := pairTableIDBitmaps[pair]; ok {
		return bm, true
	}
	reversed := [2]string{pair[1], pair[0]}
	if bm, ok := pairTableIDBitmaps[reversed]; ok {
		return bm, true
	}
	return nil, false
}

func positionsToTableBitmap(bm *roaring64.Bitmap) *roaring64.Bitmap {
	result := roaring64.NewBitmap()
	it := bm.Iterator()
	for it.HasNext() {
		pos := it.Next()
		tableID := pos >> 32
		result.Add(tableID)
	}
	return result
}

// positionsToTableBitmapCached is a cached version of positionsToTableBitmap
// to avoid redundant conversions when the same bitmap is converted multiple times
func (bs *BitmapStore) positionsToTableBitmapCached(bm *roaring64.Bitmap) *roaring64.Bitmap {
	// Check cache first
	if cached, ok := bs.tableBitmapCache.Load(bm); ok {
		return cached.(*roaring64.Bitmap)
	}

	// Compute and cache
	result := positionsToTableBitmap(bm)
	bs.tableBitmapCache.Store(bm, result)
	return result
}

func ComputeRelevantTableIDsCrossPairs(listR, listS []string, bitmapStore *BitmapStore) *roaring64.Bitmap {
	pairsRS := generateAllPairs(listR, listS)
	relevantTableIDsRS := roaring64.NewBitmap()

	for _, pair := range pairsRS {
		val1, val2 := pair[0], pair[1]
		row1 := bitmapStore.GetRowBitmap(val1)
		row2 := bitmapStore.GetRowBitmap(val2)

		overlap := roaring64.And(row1, row2)
		if overlap.GetCardinality() > 0 {
			tableIDs := bitmapStore.positionsToTableBitmapCached(overlap)
			relevantTableIDsRS.Or(tableIDs)
		}
	}

	log.Printf("Computed %d relevant table IDs from R-S pairs\n", relevantTableIDsRS.GetCardinality())
	return relevantTableIDsRS
}

func ComputeRelevantTableIDsInterColumnPairs(listR, listS []string, bitmapStore *BitmapStore) *roaring64.Bitmap {
	pairsRR := generateAllPairs(listR, listR)
	relevantTableIDsRR := roaring64.NewBitmap()

	for _, pair := range pairsRR {
		val1, val2 := pair[0], pair[1]
		col1 := bitmapStore.GetColBitmap(val1)
		col2 := bitmapStore.GetColBitmap(val2)

		overlap := roaring64.And(col1, col2)
		if overlap.GetCardinality() > 0 {
			tableIDs := bitmapStore.positionsToTableBitmapCached(overlap)
			relevantTableIDsRR.Or(tableIDs)
		}
	}

	log.Printf("Computed %d relevant table IDs from R-R pairs\n", relevantTableIDsRR.GetCardinality())

	pairsSS := generateAllPairs(listS, listS)
	relevantTableIDsSS := roaring64.NewBitmap()

	for _, pair := range pairsSS {
		val1, val2 := pair[0], pair[1]
		col1 := bitmapStore.GetColBitmap(val1)
		col2 := bitmapStore.GetColBitmap(val2)

		overlap := roaring64.And(col1, col2)
		if overlap.GetCardinality() > 0 {
			tableIDs := bitmapStore.positionsToTableBitmapCached(overlap)
			relevantTableIDsSS.Or(tableIDs)
		}
	}

	log.Printf("Computed %d relevant table IDs from S-S pairs\n", relevantTableIDsSS.GetCardinality())

	final := roaring64.And(relevantTableIDsRR, relevantTableIDsSS)
	log.Printf("Computed %d relevant table IDs (intersection of R-R and S-S)\n", final.GetCardinality())
	return final
}

func CalculatePMIForQuadScores(quadCounts []QuadCount, pairTableCounts map[[2]string]int, totalTables int) ([]QuadPMI, error) {
	if totalTables <= 0 {
		return nil, fmt.Errorf("totalTables must be greater than 0")
	}

	results := make([]QuadPMI, 0, len(quadCounts))

	for _, quadCount := range quadCounts {
		quad := quadCount.Quad
		r_i := quad[0]
		s_j := quad[1]
		r_k := quad[2]
		s_l := quad[3]

		pair1 := [2]string{r_i, s_j}
		pair2 := [2]string{r_k, s_l}

		countPair1, ok1 := pairTableCounts[pair1]
		countPair2, ok2 := pairTableCounts[pair2]

		if !ok1 || !ok2 {
			continue
		}

		if countPair1 == 0 || countPair2 == 0 {
			continue
		}

		jointProb := float64(quadCount.Count) / float64(totalTables)
		marginalProb1 := float64(countPair1) / float64(totalTables)
		marginalProb2 := float64(countPair2) / float64(totalTables)

		if jointProb == 0 {
			continue
		}

		denominator := marginalProb1 * marginalProb2
		if denominator == 0 {
			log.Printf("Warning: zero denominator for quad %s (pair1 count=%d, pair2 count=%d)", quadCount.Quad.String(), countPair1, countPair2)
			continue
		}

		pmi := math.Log(jointProb / denominator)

		if math.IsNaN(pmi) || math.IsInf(pmi, 0) {
			log.Printf("Warning: invalid PMI value for quad %s (jointProb=%f, marginalProb1=%f, marginalProb2=%f)", quadCount.Quad.String(), jointProb, marginalProb1, marginalProb2)
			continue
		}

		results = append(results, QuadPMI{
			Quad: quadCount.Quad,
			PMI:  pmi,
		})
	}

	return results, nil
}
