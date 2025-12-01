package config

import (
	"os"

	"github.com/joho/godotenv"
)

func Load() error {
	return godotenv.Load()
}

func VerticaConfig() (host, port, database, username, password string) {
	host = os.Getenv("VERTICA_HOST")
	port = os.Getenv("VERTICA_PORT")
	database = os.Getenv("VERTICA_DATABASE")
	username = os.Getenv("VERTICA_USERNAME")
	password = os.Getenv("VERTICA_PASSWORD")
	return host, port, database, username, password
}

func ServerPort() string {
	port := os.Getenv("SERVER_PORT")
	if port == "" {
		return "8080"
	}
	return port
}
