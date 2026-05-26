package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/dabljaar/orchestrator/internal/db"
	"github.com/dabljaar/orchestrator/internal/mq"
	"github.com/dabljaar/orchestrator/internal/pipeline"
)

func main() {
	
	log.Println("Starting DabljaAR Orchestrator...")

	// 1. Initializing Configurations
	rabbitURL := os.Getenv("RABBITMQ_URL")
	if rabbitURL == "" {
		log.Fatal("FATAL: RABBITMQ_URL environment variable is not set")
	}

	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		log.Fatal("FATAL: DATABASE_URL environment variable is not set")
	}

	// 2. Initialize Infrastructure
	rabbitClient, err := mq.NewRabbitMQ(rabbitURL)
	if err != nil {
		log.Fatalf("RabbitMQ initialization failed: %v", err)
	}
	defer rabbitClient.Close() // Ensure connection is closed when main exits

	database, err := db.ConnectDB(dbURL)
	if err != nil {
		log.Fatalf("Database initialization failed: %v", err)
	}
	log.Println("Successfully connected to PostgreSQL Database!")

	// 3. Dependency Injection: Pass dependencies into the Pipeline Manager
	orchestratorManager := pipeline.NewManager(rabbitClient, database)
	// Start the manager asynchronously if needed, or register handlers
	orchestratorManager.Start()

	// 4. Graceful Shutdown & Thread Blocking
	// Block the main thread until the OS tells the service to shut down
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down DabljaAR Orchestrator gracefully...")
}
