package main

import (
	"flag"
	"log"
	"net/http"
	"time"

	"example.com/simple_web_server/handlers"
	"example.com/simple_web_server/utils"
)

var (
	port    = flag.String("port", "8080", "Server port")
	timeout = flag.Duration("timeout", 30*time.Second, "Request timeout")
)
func main() {
	flag.Parse()

	// Initialize utilities
	logger := utils.NewLogger("server")
	logger.Info("Starting server on port " + *port)

	// Set up routes
	mux := http.NewServeMux()

	// Register handlers
	mux.HandleFunc("/", handlers.HomeHandler)
	mux.HandleFunc("/api/health", handlers.HealthHandler)
	mux.HandleFunc("/api/users", handlers.UsersHandler)
	mux.HandleFunc("/api/items", handlers.ItemsHandler)

	// Create server with timeout
	server := &http.Server{
		Addr:         ":" + *port,
		Handler:      mux,
		ReadTimeout:  *timeout,
		WriteTimeout: *timeout,
		IdleTimeout:  *timeout * 2,
	}

	// Middleware wrapper
	wrappedHandler := utils.LoggingMiddleware(
		utils.RecoveryMiddleware(mux),
	)
	server.Handler = wrappedHandler

	// Start server
	logger.Info("Server listening on http://localhost:" + *port)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("Server error: %v", err)
	}
}

// Line 55
// Line 56
// Line 57
// Line 58
// Line 59
// Line 60
// Line 61
// Line 62
// Line 63
// Line 64
// Line 65
// Line 66
// Line 67
// Line 68
// Line 69
// Line 70
// Line 71
func init() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)
	log.Println("Initializing application...")
}
