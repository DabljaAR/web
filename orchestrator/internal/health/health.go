package health

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"gorm.io/gorm"
)

// Connector is a minimal interface so the health package does not need to
// import the full mq package (avoids circular dependencies and is easier to
// test with a mock).
type Connector interface {
	IsConnected() bool
}

// Response is the JSON body returned by /health and /readiness.
type Response struct {
	Status    string            `json:"status"`    // "ok" | "degraded" | "not ready"
	Timestamp time.Time         `json:"timestamp"` // UTC time of the check
	Checks    map[string]string `json:"checks"`    // per-dependency status
}

// Server is a lightweight HTTP server exposing health and readiness endpoints.
type Server struct {
	port    string
	rabbit  Connector
	db      *gorm.DB
	logger  *slog.Logger
	httpSrv *http.Server
}

// NewServer constructs a Server. rabbit must implement Connector.
func NewServer(port string, rabbit Connector, database *gorm.DB, logger *slog.Logger) *Server {
	s := &Server{
		port:   port,
		rabbit: rabbit,
		db:     database,
		logger: logger,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", s.handleHealth)
	mux.HandleFunc("/readiness", s.handleReadiness)

	s.httpSrv = &http.Server{
		Addr:         ":" + port,
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
	}

	return s
}

// ListenAndServe starts the HTTP server. Blocks until the server closes.
func (s *Server) ListenAndServe() error {
	s.logger.Info("Health server listening", "port", s.port)
	return s.httpSrv.ListenAndServe()
}

// Shutdown gracefully stops the HTTP server.
func (s *Server) Shutdown(ctx context.Context) error {
	return s.httpSrv.Shutdown(ctx)
}

// handleHealth reports the current health of each dependency.
// Returns 200 if all dependencies are healthy, 503 if any are degraded.
// Kubernetes liveness probes should call this endpoint.
func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	resp := Response{
		Status:    "ok",
		Timestamp: time.Now().UTC(),
		Checks:    make(map[string]string),
	}

	// ── Check PostgreSQL ──────────────────────────────────────────────────
	if sqlDB, err := s.db.DB(); err != nil || sqlDB.Ping() != nil {
		resp.Checks["database"] = "unhealthy"
		resp.Status = "degraded"
	} else {
		resp.Checks["database"] = "healthy"
	}

	// ── Check RabbitMQ ────────────────────────────────────────────────────
	if !s.rabbit.IsConnected() {
		resp.Checks["rabbitmq"] = "unhealthy"
		resp.Status = "degraded"
	} else {
		resp.Checks["rabbitmq"] = "healthy"
	}

	status := http.StatusOK
	if resp.Status != "ok" {
		status = http.StatusServiceUnavailable
	}

	writeJSON(w, status, resp)
}

// handleReadiness reports whether the service is ready to process messages.
// Returns 200 only when ALL dependencies are reachable.
// Kubernetes readiness probes should call this endpoint.
func (s *Server) handleReadiness(w http.ResponseWriter, r *http.Request) {
	sqlDB, dbErr := s.db.DB()
	dbOK := dbErr == nil && sqlDB.Ping() == nil
	rabbitOK := s.rabbit.IsConnected()

	if !dbOK || !rabbitOK {
		writeJSON(w, http.StatusServiceUnavailable, Response{
			Status:    "not ready",
			Timestamp: time.Now().UTC(),
			Checks: map[string]string{
				"database": boolStatus(dbOK),
				"rabbitmq": boolStatus(rabbitOK),
			},
		})
		return
	}

	writeJSON(w, http.StatusOK, Response{
		Status:    "ready",
		Timestamp: time.Now().UTC(),
		Checks: map[string]string{
			"database": "healthy",
			"rabbitmq": "healthy",
		},
	})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func boolStatus(ok bool) string {
	if ok {
		return "healthy"
	}
	return "unhealthy"
}