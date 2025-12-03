package utils

import (
	"context"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

// WithTimeout wraps a Gin handler with a timeout mechanism
func WithTimeout(timeout time.Duration, handlerFunc gin.HandlerFunc) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Create a context with timeout
		ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
		defer cancel()

		// Replace the request context with our timeout context
		c.Request = c.Request.WithContext(ctx)

		// Channel to signal handler completion
		done := make(chan struct{})
		
		// Use sync.Once to ensure we only write response once
		var once sync.Once
		var handlerPanic interface{}

		// Run the handler in a goroutine
		go func() {
			defer func() {
				if r := recover(); r != nil {
					handlerPanic = r
				}
				close(done)
			}()
			handlerFunc(c)
		}()

		// Wait for either completion or timeout
		select {
		case <-done:
			// Handler completed
			if handlerPanic != nil {
				// Re-panic if handler panicked
				panic(handlerPanic)
			}
			return
		case <-ctx.Done():
			// Timeout occurred
			once.Do(func() {
				if ctx.Err() == context.DeadlineExceeded {
					log.Printf("Request timeout exceeded: %v", timeout)
					c.JSON(http.StatusRequestTimeout, gin.H{
						"error":   "Request timeout exceeded",
						"timeout": timeout.String(),
						"message": "The operation took longer than the allowed time limit of 1 hour",
					})
					c.Abort()
				}
			})
			return
		}
	}
}
