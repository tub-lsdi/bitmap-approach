package main

import (
	"bitmap-approach/internal/config"
	"bitmap-approach/internal/handler"
	"bitmap-approach/internal/utils"
	"log"
	"time"

	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()

	// Wrap the handler with a 1-hour timeout
	r.POST("/calculate-quad-scores", utils.WithTimeout(1*time.Hour, handler.CalculateQuadScores))

	port := config.ServerPort()
	log.Printf("Starting server on port %s", port)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
