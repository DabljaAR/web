package health_test

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/dabljaar/orchestrator/internal/health"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

type mockConnector struct{ ok bool }

func (m *mockConnector) IsConnected() bool { return m.ok }

type mockPipeline struct{ ready bool }

func (m *mockPipeline) IsReady() bool { return m.ready }

func openTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	return db
}

func closedDB(t *testing.T) *gorm.DB {
	t.Helper()
	db := openTestDB(t)
	sqlDB, err := db.DB()
	if err != nil {
		t.Fatalf("db handle: %v", err)
	}
	if err := sqlDB.Close(); err != nil {
		t.Fatalf("close db: %v", err)
	}
	return db
}

func serveHealth(t *testing.T, rabbit health.Connector, db *gorm.DB, pipeline health.PipelineReady, path string) *httptest.ResponseRecorder {
	t.Helper()
	s := health.NewServer("0", rabbit, db, pipeline, slog.Default())
	ts := httptest.NewServer(s.Handler())
	t.Cleanup(ts.Close)

	resp, err := http.Get(ts.URL + path)
	if err != nil {
		t.Fatalf("GET %s: %v", path, err)
	}
	t.Cleanup(func() { resp.Body.Close() })

	rec := httptest.NewRecorder()
	rec.Code = resp.StatusCode
	rec.Header().Set("Content-Type", resp.Header.Get("Content-Type"))
	body, _ := io.ReadAll(resp.Body)
	rec.Body.Write(body)
	return rec
}

func TestHealth_LivenessAlwaysOK(t *testing.T) {
	rec := serveHealth(t, &mockConnector{ok: false}, closedDB(t), &mockPipeline{ready: false}, "/health")

	if rec.Code != http.StatusOK {
		t.Errorf("status: got %d, want %d", rec.Code, http.StatusOK)
	}

	var resp health.LivenessResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Status != "healthy" {
		t.Errorf("status field: got %q, want %q", resp.Status, "healthy")
	}
	if resp.Service != "orchestrator" {
		t.Errorf("service: got %q, want orchestrator", resp.Service)
	}
}

func TestReadiness_OKWhenAllHealthy(t *testing.T) {
	rec := serveHealth(t, &mockConnector{ok: true}, openTestDB(t), &mockPipeline{ready: true}, "/readiness")

	if rec.Code != http.StatusOK {
		t.Errorf("status: got %d, want %d", rec.Code, http.StatusOK)
	}

	var resp health.ReadinessResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Status != "ready" {
		t.Errorf("status: got %q, want ready", resp.Status)
	}
	for _, check := range []string{"database", "rabbitmq", "pipeline"} {
		if resp.Checks[check] != "healthy" {
			t.Errorf("%s: got %q, want healthy", check, resp.Checks[check])
		}
	}
}

func TestReadiness_NotReadyWhenRabbitDown(t *testing.T) {
	rec := serveHealth(t, &mockConnector{ok: false}, openTestDB(t), &mockPipeline{ready: true}, "/readiness")

	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("status: got %d, want 503", rec.Code)
	}
	var resp health.ReadinessResponse
	json.NewDecoder(rec.Body).Decode(&resp)
	if resp.Checks["rabbitmq"] != "unhealthy" {
		t.Errorf("rabbitmq: got %q, want unhealthy", resp.Checks["rabbitmq"])
	}
}

func TestReadiness_NotReadyWhenDBDown(t *testing.T) {
	rec := serveHealth(t, &mockConnector{ok: true}, closedDB(t), &mockPipeline{ready: true}, "/readiness")

	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("status: got %d, want 503", rec.Code)
	}
	var resp health.ReadinessResponse
	json.NewDecoder(rec.Body).Decode(&resp)
	if resp.Checks["database"] != "unhealthy" {
		t.Errorf("database: got %q, want unhealthy", resp.Checks["database"])
	}
}

func TestReadiness_NotReadyWhenPipelineNotReady(t *testing.T) {
	rec := serveHealth(t, &mockConnector{ok: true}, openTestDB(t), &mockPipeline{ready: false}, "/readiness")

	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("status: got %d, want 503", rec.Code)
	}
	var resp health.ReadinessResponse
	json.NewDecoder(rec.Body).Decode(&resp)
	if resp.Checks["pipeline"] != "unhealthy" {
		t.Errorf("pipeline: got %q, want unhealthy", resp.Checks["pipeline"])
	}
}

func TestReadiness_NotReadyWhenPipelineNil(t *testing.T) {
	rec := serveHealth(t, &mockConnector{ok: true}, openTestDB(t), nil, "/readiness")

	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("status: got %d, want 503", rec.Code)
	}
}
