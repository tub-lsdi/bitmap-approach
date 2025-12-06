package config

import (
	"os"
	"path/filepath"
)

func DuckDBPath() string {
	dbPath := os.Getenv("DUCKDB_PATH")
	if dbPath == "" {
		// Default to corpus.db in project root
		return "corpus.db"
	}
	// Convert to absolute path if relative
	if !filepath.IsAbs(dbPath) {
		absPath, err := filepath.Abs(dbPath)
		if err == nil {
			return absPath
		}
	}
	return dbPath
}

func ServerPort() string {
	port := os.Getenv("SERVER_PORT")
	if port == "" {
		return "8080"
	}
	return port
}
