package main

import (
	"bitmap-approach/internal/config"
	"bitmap-approach/internal/handler"
	"log"

	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()

	r.POST("/calculate-quad-scores", handler.CalculateQuadScores)
	r.POST("/row-pmis", handler.CalculateRowPMIs)

	port := config.ServerPort()
	log.Printf("Starting server on port %s", port)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
