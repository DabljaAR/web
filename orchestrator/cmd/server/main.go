package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/dabljaar/orchestrator/internal/db"
	"github.com/dabljaar/orchestrator/internal/mq"
)

func main() {
	log.Println("Starting DabljaAR Orchestrator...")

	// 1. Initialize RabbitMQ Connection
	rabbitURL := os.Getenv("RABBITMQ_URL")
	if rabbitURL == "" {
		rabbitURL = "amqp://guest:guest@localhost:5672/"
	}

	rabbitClient, err := mq.NewRabbitMQ(rabbitURL)
	if err != nil {
		log.Fatalf("RabbitMQ initialization failed: %v", err)
	}
	defer rabbitClient.Close()

	// 2. Initialize Database Connection
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://postgres:postgres@localhost:5433/dabljaar"
	}

	database, err := db.ConnectDB(dbURL)
	if err != nil {
		log.Fatalf("Database initialization failed: %v", err)
	}
	_=database
	log.Println("Successfully connected to PostgreSQL Database!")

	// 3. Keep application running pending signals
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down DabljaAR Orchestrator...")
}
