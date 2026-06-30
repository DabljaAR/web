package health

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"gorm.io/gorm"
)

const serviceName = "orchestrator"

// Connector is a minimal interface so the health package does not need to
// import the full mq package (avoids circular dependencies and is easier to
// test with a mock).
type Connector interface {
	IsConnected() bool
}

// PipelineReady reports whether pipeline consumers are started and accepting work.
type PipelineReady interface {
	IsReady() bool
}

// LivenessResponse is returned by GET /health (process alive).
type LivenessResponse struct {
	Status  string `json:"status"`
	Service string `json:"service"`
	Version string `json:"version,omitempty"`
}

// ReadinessResponse is returned by GET /readiness (deps + pipeline ready).
type ReadinessResponse struct {
	Status  string            `json:"status"`
	Service string            `json:"service"`
	Checks  map[string]string `json:"checks"`
}

// Server is a lightweight HTTP server exposing health and readiness endpoints.
type Server struct {
	port     string
	rabbit   Connector
	db       *gorm.DB
	pipeline PipelineReady
	logger   *slog.Logger
	httpSrv  *http.Server
}

// NewServer constructs a Server. pipeline may be nil (treated as not ready).
func NewServer(
	port string,
	rabbit Connector,
	database *gorm.DB,
	pipeline PipelineReady,
	logger *slog.Logger,
) *Server {
	s := &Server{
		port:     port,
		rabbit:   rabbit,
		db:       database,
		pipeline: pipeline,
		logger:   logger,
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

// Handler returns the HTTP handler (useful for httptest).
func (s *Server) Handler() http.Handler {
	return s.httpSrv.Handler
}

// handleHealth is the liveness probe: process is up if this handler responds.
func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, LivenessResponse{
		Status:  "healthy",
		Service: serviceName,
	})
}

// handleReadiness reports whether the service can process pipeline messages.
func (s *Server) handleReadiness(w http.ResponseWriter, _ *http.Request) {
	checks := map[string]string{
		"database": boolStatus(dbOK(s.db)),
		"rabbitmq": boolStatus(s.rabbit != nil && s.rabbit.IsConnected()),
		"pipeline": boolStatus(pipelineOK(s.pipeline)),
	}

	ready := checks["database"] == "healthy" &&
		checks["rabbitmq"] == "healthy" &&
		checks["pipeline"] == "healthy"

	status := http.StatusOK
	respStatus := "ready"
	if !ready {
		status = http.StatusServiceUnavailable
		respStatus = "not ready"
	}

	writeJSON(w, status, ReadinessResponse{
		Status:  respStatus,
		Service: serviceName,
		Checks:  checks,
	})
}

func dbOK(database *gorm.DB) bool {
	if database == nil {
		return false
	}
	sqlDB, err := database.DB()
	if err != nil {
		return false
	}
	return sqlDB.Ping() == nil
}

func pipelineOK(p PipelineReady) bool {
	return p != nil && p.IsReady()
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
