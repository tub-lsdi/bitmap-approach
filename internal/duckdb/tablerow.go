package duckdb

import "bitmap-approach/internal/model"

type tableRow struct {
	tableID uint64
	rowID   uint64
	colID   uint64
	value   string
}

func (tr *tableRow) TableID() uint64 {
	return tr.tableID
}

func (tr *tableRow) RowID() uint64 {
	return tr.rowID
}

func (tr *tableRow) ColID() uint64 {
	return tr.colID
}

func (tr *tableRow) Value() string {
	return tr.value
}

func NewTableRow(tableID, rowID, colID uint64, value string) model.TableRow {
	return &tableRow{
		tableID: tableID,
		rowID:   rowID,
		colID:   colID,
		value:   value,
	}
}
