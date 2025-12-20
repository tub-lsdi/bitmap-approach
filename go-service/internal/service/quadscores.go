package service

import (
	"bitmap-approach/internal/model"
	"encoding/json"
	"fmt"
	"log"
	"maps"
	"math"
	"runtime"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"github.com/RoaringBitmap/roaring/v2/roaring64"
)

// Quad represents a quadruple of values (ri, sj, rk, sl)
type Quad [4]string

func (q Quad) String() string {
	return fmt.Sprintf("%s,%s,%s,%s", q[0], q[1], q[2], q[3])
}

func (q Quad) MarshalJSON() ([]byte, error) {
	return json.Marshal(q.String())
}

// QuadCount represents a quad with its co-occurrence count.
type QuadCount struct {
	Quad  Quad
	Count int
}

// QuadPMI represents a quad with its PMI score.
type QuadPMI struct {
	Quad Quad
	PMI  float64
}

// BitmapStore stores bitmaps for efficient co-occurrence lookups.
// Positions are encoded as (tableID << 32) | rowID or (tableID << 32) | colID.
type BitmapStore struct {
	rowBitmaps       map[string]*roaring64.Bitmap
	colBitmaps       map[string]*roaring64.Bitmap
	tableBitmapCache sync.Map
}

// NewBitmapStore creates a BitmapStore from a slice of table rows.
func NewBitmapStore(tableRows []model.TableRow) *BitmapStore {
	rowBitmaps := make(map[string]*roaring64.Bitmap, 500)
	colBitmaps := make(map[string]*roaring64.Bitmap, 500)

	for _, tableRow := range tableRows {
		value := tableRow.Value()

		if _, ok := rowBitmaps[value]; !ok {
			rowBitmaps[value] = roaring64.NewBitmap()
			colBitmaps[value] = roaring64.NewBitmap()
		}

		posRow := (tableRow.TableID() << 32) | tableRow.RowID()
		posCol := (tableRow.TableID() << 32) | tableRow.ColID()

		rowBitmaps[value].Add(posRow)
		colBitmaps[value].Add(posCol)
	}

	log.Printf("Created bitmaps for %d values from %d rows", len(rowBitmaps), len(tableRows))

	return &BitmapStore{
		rowBitmaps: rowBitmaps,
		colBitmaps: colBitmaps,
	}
}

// NewBitmapStoreStreaming creates a BitmapStore by streaming rows
// Uses parallel sharding for better performance.
func NewBitmapStoreStreaming(streamFunc func(func(model.TableRow) error) error) (*BitmapStore, int, error) {
	numShards := runtime.NumCPU()
	shards := make([]*bitmapShard, numShards)
	for i := range shards {
		shards[i] = &bitmapShard{
			rowPositions: make(map[string][]uint64, 100),
			colPositions: make(map[string][]uint64, 100),
		}
	}


	const batchSize = 2000000  // Process 2M rows per batch
	shardChannels := make([]chan rowBatch, numShards)
	for i := range shardChannels {
		shardChannels[i] = make(chan rowBatch, 2000000)  // 2M buffer per shard
	}

	var rowsProcessed atomic.Int64
	var workerWg sync.WaitGroup

	for i := range numShards {
		workerWg.Add(1)
		go processShardWorker(shards[i], shardChannels[i], &workerWg, batchSize)
	}

	err := streamFunc(func(tableRow model.TableRow) error {
		value := tableRow.Value()
		shardIdx := hashString(value) % uint64(numShards)

		shardChannels[shardIdx] <- rowBatch{
			value:   value,
			tableID: tableRow.TableID(),
			rowID:   tableRow.RowID(),
			colID:   tableRow.ColID(),
		}

		if current := rowsProcessed.Add(1); current%10000000 == 0 {
			log.Printf("Processed %d rows...", current)
		}

		return nil
	})

	for i := range shardChannels {
		close(shardChannels[i])
	}

	workerWg.Wait()

	if err != nil {
		return nil, 0, fmt.Errorf("error streaming rows: %w", err)
	}

	finalRowBitmaps, finalColBitmaps := mergeShards(shards)
	totalRows := int(rowsProcessed.Load())

	log.Printf("Created bitmaps for %d values from %d rows", len(finalRowBitmaps), totalRows)

	return &BitmapStore{
		rowBitmaps: finalRowBitmaps,
		colBitmaps: finalColBitmaps,
	}, totalRows, nil
}

func processShardWorker(shard *bitmapShard, ch chan rowBatch, wg *sync.WaitGroup, batchSize int) {
	defer wg.Done()

	batch := make([]rowBatch, 0, batchSize)

	for row := range ch {
		batch = append(batch, row)

		if len(batch) >= batchSize {
			processBatch(shard, batch)
			batch = batch[:0]
		}
	}

	if len(batch) > 0 {
		processBatch(shard, batch)
	}
}

func processBatch(shard *bitmapShard, batch []rowBatch) {
	// Group by value first (outside lock for better CPU utilization)
	valueGroups := make(map[string]struct {
		rowPositions []uint64
		colPositions []uint64
	}, 1024)

	for _, row := range batch {
		posRow := (row.tableID << 32) | row.rowID
		posCol := (row.tableID << 32) | row.colID

		group := valueGroups[row.value]
		group.rowPositions = append(group.rowPositions, posRow)
		group.colPositions = append(group.colPositions, posCol)
		valueGroups[row.value] = group
	}

	shard.mu.Lock()
	defer shard.mu.Unlock()

	for value, group := range valueGroups {
		// Append all positions for this value
		shard.rowPositions[value] = append(shard.rowPositions[value], group.rowPositions...)
		shard.colPositions[value] = append(shard.colPositions[value], group.colPositions...)
	}
}

func mergeShards(shards []*bitmapShard) (map[string]*roaring64.Bitmap, map[string]*roaring64.Bitmap) {
	// Merge position slices from all shards
	log.Printf("Merging position slices from %d shards...", len(shards))
	finalRowPositions := make(map[string][]uint64, 1000)
	finalColPositions := make(map[string][]uint64, 1000)
	var mergeMu sync.Mutex
	var wg sync.WaitGroup

	for _, shard := range shards {
		wg.Add(1)
		go func(s *bitmapShard) {
			defer wg.Done()
			s.mu.Lock()
			defer s.mu.Unlock()

			for value, positions := range s.rowPositions {
				mergeMu.Lock()
				finalRowPositions[value] = append(finalRowPositions[value], positions...)
				mergeMu.Unlock()
			}

			for value, positions := range s.colPositions {
				mergeMu.Lock()
				finalColPositions[value] = append(finalColPositions[value], positions...)
				mergeMu.Unlock()
			}
		}(shard)
	}

	wg.Wait()
	log.Printf("Merged positions for %d values", len(finalRowPositions))

	// Build bitmaps in parallel
	log.Printf("Building bitmaps in parallel using all CPU cores...")
	return buildBitmapsFromPositions(finalRowPositions, finalColPositions)
}

// buildBitmapsFromPositions converts position slices to bitmaps in parallel
func buildBitmapsFromPositions(
	rowPositions map[string][]uint64,
	colPositions map[string][]uint64,
) (map[string]*roaring64.Bitmap, map[string]*roaring64.Bitmap) {

	rowBitmaps := make(map[string]*roaring64.Bitmap, len(rowPositions))
	colBitmaps := make(map[string]*roaring64.Bitmap, len(colPositions))

	var mu sync.Mutex
	var wg sync.WaitGroup

	// Get all unique values
	values := make([]string, 0, len(rowPositions))
	for value := range rowPositions {
		values = append(values, value)
	}

	// Build bitmaps in parallel - one goroutine per value
	for _, value := range values {
		wg.Add(1)
		go func(val string) {
			defer wg.Done()

			// For position slices, chunk and build in parallel
			chunkSize := 5000000 // 5M positions per chunk
			rowPos := rowPositions[val]
			colPos := colPositions[val]

			// Build row and col bitmaps in parallel
			var wg2 sync.WaitGroup
			var rowBitmap, colBitmap *roaring64.Bitmap

			wg2.Add(2)
			go func() {
				defer wg2.Done()
				if len(rowPos) <= chunkSize {
					rowBitmap = roaring64.NewBitmap()
					rowBitmap.AddMany(rowPos)
				} else {
					// Split into chunks for values
					chunks := (len(rowPos) + chunkSize - 1) / chunkSize
					chunkBitmaps := make([]*roaring64.Bitmap, chunks)
					var wg3 sync.WaitGroup
					for i := 0; i < chunks; i++ {
						wg3.Add(1)
						start := i * chunkSize
						end := min((i+1)*chunkSize, len(rowPos))
						go func(idx int, chunk []uint64) {
							defer wg3.Done()
							bm := roaring64.NewBitmap()
							bm.AddMany(chunk)
							chunkBitmaps[idx] = bm
						}(i, rowPos[start:end])
					}
					wg3.Wait()
					// Merge chunks
					rowBitmap = chunkBitmaps[0]
					for i := 1; i < len(chunkBitmaps); i++ {
						rowBitmap.Or(chunkBitmaps[i])
					}
				}
			}()

			go func() {
				defer wg2.Done()
				if len(colPos) <= chunkSize {
					colBitmap = roaring64.NewBitmap()
					colBitmap.AddMany(colPos)
				} else {
					// Split into chunks for values
					chunks := (len(colPos) + chunkSize - 1) / chunkSize
					chunkBitmaps := make([]*roaring64.Bitmap, chunks)
					var wg3 sync.WaitGroup
					for i := 0; i < chunks; i++ {
						wg3.Add(1)
						start := i * chunkSize
						end := min((i+1)*chunkSize, len(colPos))
						go func(idx int, chunk []uint64) {
							defer wg3.Done()
							bm := roaring64.NewBitmap()
							bm.AddMany(chunk)
							chunkBitmaps[idx] = bm
						}(i, colPos[start:end])
					}
					wg3.Wait()
					// Merge chunks
					colBitmap = chunkBitmaps[0]
					for i := 1; i < len(chunkBitmaps); i++ {
						colBitmap.Or(chunkBitmaps[i])
					}
				}
			}()
			wg2.Wait()

			mu.Lock()
			rowBitmaps[val] = rowBitmap
			colBitmaps[val] = colBitmap
			mu.Unlock()
		}(value)
	}

	wg.Wait()
	log.Printf("Built bitmaps for %d values in parallel", len(values))

	return rowBitmaps, colBitmaps
}

type bitmapShard struct {
	// Store raw positions instead of bitmaps during streaming
	// Building bitmaps incrementally on huge datasets (100M+ positions) becomes slow
	// due to internal bitmap maintenance. Accumulate positions in slices (O(1)),
	// then build bitmaps at end in parallel
	rowPositions map[string][]uint64
	colPositions map[string][]uint64
	mu           sync.Mutex
}

type rowBatch struct {
	value   string
	tableID uint64
	rowID   uint64
	colID   uint64
}

func hashString(s string) uint64 {
	var hash uint64 = 5381
	for i := 0; i < len(s); i++ {
		hash = ((hash << 5) + hash) + uint64(s[i])
	}
	return hash
}

// GetRowBitmap returns the bitmap of row positions for a value.
func (bs *BitmapStore) GetRowBitmap(value string) *roaring64.Bitmap {
	if bm, ok := bs.rowBitmaps[value]; ok {
		return bm
	}
	return roaring64.NewBitmap()
}

// GetColBitmap returns the bitmap of column positions for a value.
func (bs *BitmapStore) GetColBitmap(value string) *roaring64.Bitmap {
	if bm, ok := bs.colBitmaps[value]; ok {
		return bm
	}
	return roaring64.NewBitmap()
}

// FilterToRelevantTables filters bitmaps to only include relevant tables.
func (bs *BitmapStore) FilterToRelevantTables(relevantTableIDs *roaring64.Bitmap) {
	numWorkers := runtime.NumCPU()
	var wg sync.WaitGroup

	filterBitmaps := func(bitmaps map[string]*roaring64.Bitmap, mu *sync.Mutex) {
		values := make([]string, 0, len(bitmaps))
		for value := range bitmaps {
			values = append(values, value)
		}

		chunkSize := (len(values) + numWorkers - 1) / numWorkers

		for w := range numWorkers {
			start := w * chunkSize
			end := min((w+1)*chunkSize, len(values))
			if start >= len(values) {
				break
			}

			wg.Add(1)
			go func(vals []string) {
				defer wg.Done()
				for _, value := range vals {
					mu.Lock()
					bitmap, ok := bitmaps[value]
					mu.Unlock()

					if ok {
						filtered := filterBitmapByTableIDs(bitmap, relevantTableIDs)
						mu.Lock()
						bitmaps[value] = filtered
						mu.Unlock()
					}
				}
			}(values[start:end])
		}
	}

	var rowMu, colMu sync.Mutex
	filterBitmaps(bs.rowBitmaps, &rowMu)
	wg.Wait()
	filterBitmaps(bs.colBitmaps, &colMu)
	wg.Wait()
}

func filterBitmapByTableIDs(bitmap *roaring64.Bitmap, relevantTableIDs *roaring64.Bitmap) *roaring64.Bitmap {
	tableIDSet := make(map[uint64]bool)
	it := bitmap.Iterator()
	for it.HasNext() {
		tableIDSet[it.Next()>>32] = true
	}

	validTableIDs := make(map[uint64]bool, len(tableIDSet))
	for tableID := range tableIDSet {
		if relevantTableIDs.Contains(tableID) {
			validTableIDs[tableID] = true
		}
	}

	filtered := roaring64.NewBitmap()
	it = bitmap.Iterator()
	for it.HasNext() {
		pos := it.Next()
		if validTableIDs[pos>>32] {
			filtered.Add(pos)
		}
	}

	return filtered
}

// CalculatePairTableCount returns the number of tables where two values co-occur in the same row.
func (bs *BitmapStore) CalculatePairTableCount(pair [2]string) int {
	row1 := bs.GetRowBitmap(pair[0])
	row2 := bs.GetRowBitmap(pair[1])

	rowIntersection := roaring64.And(row1, row2)
	if rowIntersection.GetCardinality() == 0 {
		return 0
	}

	tableBitmap := bs.positionsToTableBitmapCached(rowIntersection)
	return int(tableBitmap.GetCardinality())
}

// CalculatePairTableCounts calculates counts for multiple pairs in batch.
func (bs *BitmapStore) CalculatePairTableCounts(pairs [][2]string) map[[2]string]int {
	result := make(map[[2]string]int, len(pairs))
	for _, pair := range pairs {
		result[pair] = bs.CalculatePairTableCount(pair)
	}
	return result
}

// CalculateQuadScores calculates co-occurrence counts for all valid quadruples.
func CalculateQuadScores(listR, listS []string, bitmapStore *BitmapStore) ([]QuadCount, error) {
	pairs := generateAllPairs(listR, listS)
	pairsR := generateAllPairs(listR, listR)
	pairsS := generateAllPairs(listS, listS)

	whitelist, pairTableIDBitmaps := buildPairWhitelist(pairs, bitmapStore)
	_, pairTableIDBitmapsR := buildPairWhitelistColumn(pairsR, bitmapStore)
	_, pairTableIDBitmapsS := buildPairWhitelistColumn(pairsS, bitmapStore)

	var mu sync.Mutex
	allCounts := make(map[Quad]int)
	var operationsCompleted atomic.Int64
	var lastReportedPercent atomic.Int64
	lastReportedPercent.Store(-1)
	startTime := time.Now()

	totalOperations := int64(len(whitelist)) * int64(len(whitelist)-1) / 2
	log.Printf("Processing %d operations from %d whitelist pairs", totalOperations, len(whitelist))

	numWorkers := runtime.NumCPU()
	chunkSize := (len(whitelist) + numWorkers - 1) / numWorkers
	var wg sync.WaitGroup

	for w := range numWorkers {
		start := w * chunkSize
		end := min((w+1)*chunkSize, len(whitelist))
		if start >= len(whitelist) {
			break
		}

		wg.Add(1)
		go func(startIdx, endIdx int) {
			defer wg.Done()
			localCounts := make(map[Quad]int)

			for i := startIdx; i < endIdx; i++ {
				pair1 := whitelist[i]
				ri, sj := pair1[0], pair1[1]

				for j := i + 1; j < len(whitelist); j++ {
					pair2 := whitelist[j]
					rk, sl := pair2[0], pair2[1]

					if ri != rk {
						pairR := [2]string{ri, rk}
						pairS := [2]string{sj, sl}

						_, okR := getPairTableBitmap(pairR, pairTableIDBitmapsR)
						_, okS := getPairTableBitmap(pairS, pairTableIDBitmapsS)
						if !okR || !okS {
							continue
						}

						quad := Quad{ri, sj, rk, sl}
						count := countTablesForQuadruple([4]string(quad),
							pairTableIDBitmaps, pairTableIDBitmapsR, pairTableIDBitmapsS)

						if count > 0 {
							localCounts[quad] = count
						}
					}

					current := operationsCompleted.Add(1)
					reportProgress(current, totalOperations, startTime, &lastReportedPercent)
				}
			}

			mu.Lock()
			maps.Copy(allCounts, localCounts)
			mu.Unlock()
		}(start, end)
	}

	wg.Wait()
	log.Printf("Completed: processed %d operations in %v", totalOperations, time.Since(startTime))

	return sortQuadCounts(allCounts), nil
}

func reportProgress(current, total int64, startTime time.Time, lastReportedPercent *atomic.Int64) {
	currentPercent := (current * 100) / total
	lastPercent := lastReportedPercent.Load()
	if currentPercent > lastPercent && lastReportedPercent.CompareAndSwap(lastPercent, currentPercent) {
		elapsed := time.Since(startTime)
		rate := float64(current) / elapsed.Seconds()
		remaining := time.Duration(float64(total-current)/rate) * time.Second
		log.Printf("Progress: %d%% (%d/%d ops, %.0f ops/sec, ETA: %v)",
			currentPercent, current, total, rate, remaining)
	}
}

func sortQuadCounts(counts map[Quad]int) []QuadCount {
	type kv struct {
		Key Quad
		Val int
	}

	filtered := make([]kv, 0, len(counts))
	for k, v := range counts {
		if v > 0 {
			filtered = append(filtered, kv{Key: k, Val: v})
		}
	}

	sort.Slice(filtered, func(i, j int) bool {
		return filtered[i].Val > filtered[j].Val
	})

	results := make([]QuadCount, len(filtered))
	for i, kv := range filtered {
		results[i] = QuadCount{Quad: kv.Key, Count: kv.Val}
	}

	return results
}

// Counts tables where (ri,sj) and (rk,sl) co-occur in same rows,
// and (ri,rk) and (sj,sl) co-occur in same columns.
func countTablesForQuadruple(
	quad [4]string,
	pairTableIDBitmaps map[[2]string]*roaring64.Bitmap,
	pairTableIDBitmapsR map[[2]string]*roaring64.Bitmap,
	pairTableIDBitmapsS map[[2]string]*roaring64.Bitmap,
) int {
	a, b, c, d := quad[0], quad[1], quad[2], quad[3]

	tablesRowAB, okAB := pairTableIDBitmaps[[2]string{a, b}]
	if !okAB || tablesRowAB.GetCardinality() == 0 {
		return 0
	}

	tablesRowCD, okCD := pairTableIDBitmaps[[2]string{c, d}]
	if !okCD || tablesRowCD.GetCardinality() == 0 {
		return 0
	}

	rowIntersection := roaring64.And(tablesRowAB, tablesRowCD)
	if rowIntersection.GetCardinality() == 0 {
		return 0
	}

	tablesColAC, okAC := getPairTableBitmap([2]string{a, c}, pairTableIDBitmapsR)
	if !okAC || tablesColAC.GetCardinality() == 0 {
		return 0
	}

	tablesColBD, okBD := getPairTableBitmap([2]string{b, d}, pairTableIDBitmapsS)
	if !okBD || tablesColBD.GetCardinality() == 0 {
		return 0
	}

	colIntersection := roaring64.And(tablesColAC, tablesColBD)
	if colIntersection.GetCardinality() == 0 {
		return 0
	}

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
	return buildPairWhitelistGeneric(pairs, bitmapStore, true)
}

func buildPairWhitelistColumn(pairs [][2]string, bitmapStore *BitmapStore) ([][2]string, map[[2]string]*roaring64.Bitmap) {
	return buildPairWhitelistGeneric(pairs, bitmapStore, false)
}

func buildPairWhitelistGeneric(pairs [][2]string, bitmapStore *BitmapStore, useRowBitmaps bool) ([][2]string, map[[2]string]*roaring64.Bitmap) {
	type result struct {
		pair        [2]string
		tableBitmap *roaring64.Bitmap
	}

	resultChan := make(chan result, len(pairs))
	numWorkers := runtime.NumCPU()
	chunkSize := (len(pairs) + numWorkers - 1) / numWorkers
	var wg sync.WaitGroup

	for w := range numWorkers {
		start := w * chunkSize
		end := min((w+1)*chunkSize, len(pairs))
		if start >= len(pairs) {
			break
		}

		wg.Add(1)
		go func(pairSlice [][2]string) {
			defer wg.Done()

			for _, pair := range pairSlice {
				var bitmap1, bitmap2 *roaring64.Bitmap
				if useRowBitmaps {
					bitmap1 = bitmapStore.GetRowBitmap(pair[0])
					bitmap2 = bitmapStore.GetRowBitmap(pair[1])
				} else {
					bitmap1 = bitmapStore.GetColBitmap(pair[0])
					bitmap2 = bitmapStore.GetColBitmap(pair[1])
				}

				overlap := roaring64.And(bitmap1, bitmap2)
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

	whitelist := make([][2]string, 0, len(pairs)/10)
	pairTableIDBitmaps := make(map[[2]string]*roaring64.Bitmap)

	for res := range resultChan {
		whitelist = append(whitelist, res.pair)
		pairTableIDBitmaps[res.pair] = res.tableBitmap
	}

	whitelistType := "row"
	if !useRowBitmaps {
		whitelistType = "column"
	}
	log.Printf("Whitelisted %d %s pairs", len(whitelist), whitelistType)

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
		result.Add(it.Next() >> 32)
	}
	return result
}

func (bs *BitmapStore) positionsToTableBitmapCached(bm *roaring64.Bitmap) *roaring64.Bitmap {
	if cached, ok := bs.tableBitmapCache.Load(bm); ok {
		return cached.(*roaring64.Bitmap)
	}

	result := positionsToTableBitmap(bm)
	bs.tableBitmapCache.Store(bm, result)
	return result
}

// ComputeRelevantTableIDsCrossPairs finds tables where R and S values co-occur in rows.
func ComputeRelevantTableIDsCrossPairs(listR, listS []string, bitmapStore *BitmapStore) *roaring64.Bitmap {
	pairsRS := generateAllPairs(listR, listS)
	relevantTableIDs := roaring64.NewBitmap()

	for _, pair := range pairsRS {
		row1 := bitmapStore.GetRowBitmap(pair[0])
		row2 := bitmapStore.GetRowBitmap(pair[1])

		overlap := roaring64.And(row1, row2)
		if overlap.GetCardinality() > 0 {
			tableIDs := bitmapStore.positionsToTableBitmapCached(overlap)
			relevantTableIDs.Or(tableIDs)
		}
	}

	log.Printf("Computed %d relevant table IDs from R-S pairs", relevantTableIDs.GetCardinality())
	return relevantTableIDs
}

// ComputeRelevantTableIDsInterColumnPairs finds tables where R-R and S-S values co-occur in columns.
func ComputeRelevantTableIDsInterColumnPairs(listR, listS []string, bitmapStore *BitmapStore) *roaring64.Bitmap {
	relevantTableIDsRR := computeColumnCooccurrence(generateAllPairs(listR, listR), bitmapStore)
	log.Printf("Computed %d relevant table IDs from R-R pairs", relevantTableIDsRR.GetCardinality())

	relevantTableIDsSS := computeColumnCooccurrence(generateAllPairs(listS, listS), bitmapStore)
	log.Printf("Computed %d relevant table IDs from S-S pairs", relevantTableIDsSS.GetCardinality())

	final := roaring64.And(relevantTableIDsRR, relevantTableIDsSS)
	log.Printf("Computed %d relevant table IDs (intersection)", final.GetCardinality())
	return final
}

func computeColumnCooccurrence(pairs [][2]string, bitmapStore *BitmapStore) *roaring64.Bitmap {
	relevantTableIDs := roaring64.NewBitmap()

	for _, pair := range pairs {
		col1 := bitmapStore.GetColBitmap(pair[0])
		col2 := bitmapStore.GetColBitmap(pair[1])

		overlap := roaring64.And(col1, col2)
		if overlap.GetCardinality() > 0 {
			tableIDs := bitmapStore.positionsToTableBitmapCached(overlap)
			relevantTableIDs.Or(tableIDs)
		}
	}

	return relevantTableIDs
}

// CalculatePMIForQuadScores calculates PMI scores for quadruples.
func CalculatePMIForQuadScores(quadCounts []QuadCount, pairTableCounts map[[2]string]int, totalTables int) ([]QuadPMI, error) {
	if totalTables <= 0 {
		return nil, fmt.Errorf("totalTables must be greater than 0")
	}

	results := make([]QuadPMI, 0, len(quadCounts))

	for _, quadCount := range quadCounts {
		quad := quadCount.Quad
		pair1 := [2]string{quad[0], quad[1]}
		pair2 := [2]string{quad[2], quad[3]}

		countPair1, ok1 := pairTableCounts[pair1]
		countPair2, ok2 := pairTableCounts[pair2]

		if !ok1 || !ok2 || countPair1 == 0 || countPair2 == 0 {
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
			log.Printf("Warning: zero denominator for quad %s", quadCount.Quad.String())
			continue
		}

		pmi := math.Log(jointProb / denominator)

		if math.IsNaN(pmi) || math.IsInf(pmi, 0) {
			log.Printf("Warning: invalid PMI value for quad %s", quadCount.Quad.String())
			continue
		}

		// Filter out negative PMI
		if pmi <= 0 {
			continue
		}

		results = append(results, QuadPMI{Quad: quadCount.Quad, PMI: pmi})
	}

	return results, nil
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
