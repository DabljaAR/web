package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/dabljaar/orchestrator/internal/db"
	"github.com/dabljaar/orchestrator/internal/health"
	"github.com/dabljaar/orchestrator/internal/mq"
	"github.com/dabljaar/orchestrator/internal/pipeline"
)

func main() {
	// ─── 1. Structured Logging ────────────────────────────────────────────────
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelDebug,
	}))
	slog.SetDefault(logger)

	logger.Info("Starting DabljaAR Orchestrator")

	// ─── 2. Load Config ───────────────────────────────────────────────────────
	rabbitURL := os.Getenv("RABBITMQ_URL")
	if rabbitURL == "" {
		logger.Error("RABBITMQ_URL environment variable is not set")
		os.Exit(1)
	}

	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		logger.Error("DATABASE_URL environment variable is not set")
		os.Exit(1)
	}

	healthPort := os.Getenv("HEALTH_PORT")
	if healthPort == "" {
		healthPort = "8081"
	}

	// ─── 3. Initialize Infrastructure ────────────────────────────────────────
	rabbitClient, err := mq.NewRabbitMQ(rabbitURL)
	if err != nil {
		logger.Error("RabbitMQ initialization failed", "error", err)
		os.Exit(1)
	}
	defer rabbitClient.Close()

	database, err := db.ConnectDB(dbURL)
	if err != nil {
		logger.Error("Database initialization failed", "error", err)
		os.Exit(1)
	}
	logger.Info("Connected to PostgreSQL")

	// Ensure the underlying connection pool is closed on exit.
	defer func() {
		if sqlDB, err := database.DB(); err == nil {
			sqlDB.Close()
		}
	}()

	// ─── 4. Root Context (drives graceful shutdown of all goroutines) ─────────
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// ─── 5. Start Pipeline Manager ────────────────────────────────────────────
	manager := pipeline.NewManager(rabbitClient, database, logger)
	if err := manager.Start(ctx); err != nil {
		logger.Error("Pipeline manager failed to start", "error", err)
		os.Exit(1)
	}

	// ─── 6. Start Health / Readiness HTTP Server ──────────────────────────────
	healthSrv := health.NewServer(healthPort, rabbitClient, database, logger)
	go func() {
		if err := healthSrv.ListenAndServe(); err != nil {
			logger.Error("Health server error", "error", err)
		}
	}()

	// ─── 7. Block Until OS Signal ─────────────────────────────────────────────
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	sig := <-quit

	logger.Info("Shutdown signal received", "signal", sig.String())

	// Cancel root context → consumers stop accepting new messages.
	cancel()

	// Give active message handlers up to 30 seconds to finish.
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer shutdownCancel()

	manager.Wait(shutdownCtx)
	logger.Info("DabljaAR Orchestrator stopped gracefully")
}
