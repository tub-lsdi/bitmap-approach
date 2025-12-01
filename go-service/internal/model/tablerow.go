package model

type TableRow interface {
	TableID() uint64
	RowID() uint64
	ColID() uint64
	Value() string
}
