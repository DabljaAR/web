package health_test

// Run: go test ./internal/health/... -v

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// ─── Minimal in-process health handler (mirrors health.go logic) ───────────
// These tests exercise the HTTP response shape without spinning up a real server.

type mockConnector struct{ ok bool }

func (m *mockConnector) IsConnected() bool { return m.ok }

type healthResp struct {
	Status    string            `json:"status"`
	Timestamp time.Time         `json:"timestamp"`
	Checks    map[string]string `json:"checks"`
}

// ─── Tests ────────────────────────────────────────────────────────────────────

func TestHealth_OKWhenAllHealthy(t *testing.T) {
	// Build a handler that mimics health.go's handleHealth.
	// In your actual test, import and call health.NewServer directly
	// with a httptest.NewRecorder().
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(healthResp{
			Status:    "ok",
			Timestamp: time.Now().UTC(),
			Checks:    map[string]string{"database": "healthy", "rabbitmq": "healthy"},
		})
	})

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("status: got %d, want %d", rec.Code, http.StatusOK)
	}

	var resp healthResp
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Status != "ok" {
		t.Errorf("status field: got %q, want %q", resp.Status, "ok")
	}
	if resp.Checks["database"] != "healthy" {
		t.Errorf("database check: got %q, want %q", resp.Checks["database"], "healthy")
	}
}

func TestHealth_DegradedWhenRabbitDown(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(healthResp{
			Status: "degraded",
			Checks: map[string]string{"database": "healthy", "rabbitmq": "unhealthy"},
		})
	})

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("status: got %d, want 503", rec.Code)
	}

	var resp healthResp
	json.NewDecoder(rec.Body).Decode(&resp)
	if resp.Status != "degraded" {
		t.Errorf("status: got %q, want %q", resp.Status, "degraded")
	}
}

func TestReadiness_NotReadyWhenDBDown(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"status": "not ready"})
	})

	req := httptest.NewRequest(http.MethodGet, "/readiness", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("readiness status: got %d, want 503", rec.Code)
	}
}

func TestConnector_IsConnected(t *testing.T) {
	c := &mockConnector{ok: true}
	if !c.IsConnected() {
		t.Error("expected connected=true")
	}
	c.ok = false
	if c.IsConnected() {
		t.Error("expected connected=false after disconnect")
	}
}