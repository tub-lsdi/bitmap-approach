package service

import (
	"bitmap-approach/internal/model"
	"fmt"
	"log"
	"sort"

	"github.com/RoaringBitmap/roaring/v2/roaring64"
)

type QuadScore struct {
	Quad  string
	Count int
}

func CalculateQuadScores(listR, listS []string, tableRows []model.TableRow) ([]QuadScore, error) {
	pairs := generateAllPairs(listR, listS)
	pairsR := generateAllPairs(listR, listR)
	pairsS := generateAllPairs(listS, listS)

	rowBitmaps, colBitmaps := createBitmaps(tableRows)

	whitelist := buildPairWhitelist(pairs, rowBitmaps)
	blacklistR := buildPairBlacklistColumn(pairsR, colBitmaps)
	blacklistS := buildPairBlacklistColumn(pairsS, colBitmaps)

	all_counts := make(map[string]int)

	for i, pair1 := range whitelist {
		r_i, s_j := pair1[0], pair1[1]
		for j := i + 1; j < len(whitelist); j++ {
			pair2 := whitelist[j]
			r_k, s_l := pair2[0], pair2[1]
			if r_i != r_k {
				pairR1 := [2]string{r_i, r_k}
				pairR2 := [2]string{r_k, r_i}
				pairS1 := [2]string{s_j, s_l}
				pairS2 := [2]string{s_l, s_j}
				if blacklistR[pairR1] || blacklistR[pairR2] || blacklistS[pairS1] || blacklistS[pairS2] {
					continue
				}
				quad := [4]string{r_i, s_j, r_k, s_l}
				count := countTablesForQuadruple(quad, rowBitmaps, colBitmaps)
				all_counts[fmt.Sprintf("%s,%s,%s,%s", r_i, s_j, r_k, s_l)] = count
			}
		}
		if i%100 == 0 {
			log.Printf("Processed %d outer pairs\n", i)
		}
	}

	type kv struct {
		Key string
		Val int
	}

	filtered := make([]kv, 0, len(all_counts))
	for k, v := range all_counts {
		if v > 0 {
			filtered = append(filtered, kv{Key: k, Val: v})
		}
	}

	sort.Slice(filtered, func(i, j int) bool { return filtered[i].Val > filtered[j].Val })

	results := make([]QuadScore, len(filtered))
	for i, kv := range filtered {
		results[i] = QuadScore{
			Quad:  kv.Key,
			Count: kv.Val,
		}
	}

	return results, nil
}

func createBitmaps(tableRows []model.TableRow) (map[string]*roaring64.Bitmap, map[string]*roaring64.Bitmap) {
	rowBitmaps := make(map[string]*roaring64.Bitmap)
	colBitmaps := make(map[string]*roaring64.Bitmap)

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
	return rowBitmaps, colBitmaps
}

func countTablesForQuadruple(quad [4]string, rowBitmaps, colBitmaps map[string]*roaring64.Bitmap) int {
	a, b, c, d := quad[0], quad[1], quad[2], quad[3]

	rowA := getBitmap(rowBitmaps, a)
	rowB := getBitmap(rowBitmaps, b)
	rowC := getBitmap(rowBitmaps, c)
	rowD := getBitmap(rowBitmaps, d)

	colA := getBitmap(colBitmaps, a)
	colB := getBitmap(colBitmaps, b)
	colC := getBitmap(colBitmaps, c)
	colD := getBitmap(colBitmaps, d)

	rowAB := roaring64.And(rowA, rowB)
	if rowAB.GetCardinality() == 0 {
		return 0
	}
	rowCD := roaring64.And(rowC, rowD)
	if rowCD.GetCardinality() == 0 {
		return 0
	}
	colAC := roaring64.And(colA, colC)
	if colAC.GetCardinality() == 0 {
		return 0
	}
	colBD := roaring64.And(colB, colD)
	if colBD.GetCardinality() == 0 {
		return 0
	}

	tablesRowAB := positionsToTableBitmap(rowAB)
	tablesRowCD := positionsToTableBitmap(rowCD)
	tablesColAC := positionsToTableBitmap(colAC)
	tablesColBD := positionsToTableBitmap(colBD)

	final := roaring64.And(
		roaring64.And(tablesRowAB, tablesRowCD),
		roaring64.And(tablesColAC, tablesColBD),
	)

	return int(final.GetCardinality())
}

func getBitmap(bitmaps map[string]*roaring64.Bitmap, value string) *roaring64.Bitmap {
	if bm, ok := bitmaps[value]; ok {
		return bm
	}
	return roaring64.NewBitmap()
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

func buildPairWhitelist(pairs [][2]string, rowBitmaps map[string]*roaring64.Bitmap) [][2]string {
	whitelist := make([][2]string, 0)

	for _, pair := range pairs {
		val1, val2 := pair[0], pair[1]
		row1 := getBitmap(rowBitmaps, val1)
		row2 := getBitmap(rowBitmaps, val2)

		overlap := roaring64.And(row1, row2)
		if overlap.GetCardinality() > 0 {
			whitelist = append(whitelist, pair)
		}
	}

	return whitelist
}

func buildPairBlacklistColumn(pairs [][2]string, colBitmaps map[string]*roaring64.Bitmap) map[[2]string]bool {
	blacklist := make(map[[2]string]bool)

	for _, pair := range pairs {
		val1, val2 := pair[0], pair[1]
		col1 := getBitmap(colBitmaps, val1)
		col2 := getBitmap(colBitmaps, val2)

		overlap := roaring64.And(col1, col2)
		if overlap.GetCardinality() == 0 {
			blacklist[pair] = true
		}
	}

	return blacklist
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
