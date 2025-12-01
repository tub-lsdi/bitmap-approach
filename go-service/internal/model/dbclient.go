package model

type DBClient interface {
	FetchRelevantTableIDs(pairs [][2]string) ([]uint64, error)
	LoadTableRows(tableIDs []uint64, values []string, limit int) ([]TableRow, error)
	Close() error
}
