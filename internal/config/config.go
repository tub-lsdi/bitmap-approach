package config

import (
	"fmt"
	"os"

	"github.com/joho/godotenv"
)

func Load() error {
	return godotenv.Load()
}

func DuckDBPath() (string, error) {
	path := os.Getenv("DUCKDB_PATH")
	if path == "" {
		return "", fmt.Errorf("DUCKDB_PATH environment variable is not set")
	}
	return path, nil
}
