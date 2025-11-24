package config

import (
	"os"
	"strconv"

	"github.com/joho/godotenv"
)

func Load() error {
	return godotenv.Load()
}

func DuckDBPath() string {
	return os.Getenv("DUCKDB_PATH")
}

func VerticaConfig() (host, port, database, username, password string) {
	host = os.Getenv("VERTICA_HOST")
	port = os.Getenv("VERTICA_PORT")
	database = os.Getenv("VERTICA_DATABASE")
	username = os.Getenv("VERTICA_USERNAME")
	password = os.Getenv("VERTICA_PASSWORD")
	return host, port, database, username, password
}

func VerticaRowLimit() int {
	limitStr := os.Getenv("VERTICA_ROW_LIMIT")
	if limitStr == "" {
		return 1000000
	}
	limit, err := strconv.Atoi(limitStr)
	if err != nil || limit <= 0 {
		return 1000000
	}
	return limit
}
