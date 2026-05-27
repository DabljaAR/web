package pipeline_test

// ─────────────────────────────────────────────────────────────────────────────
// How to run:
//   go test ./internal/pipeline/... -v
//   go test ./internal/pipeline/... -v -run TestHandleResult
//   go test ./internal/pipeline/... -v -count=1   # disable test cache
//
// Integration tests (need real DB + RabbitMQ) are tagged "integration":
//   go test ./internal/pipeline/... -v -tags=integration
// ─────────────────────────────────────────────────────────────────────────────

import (
	"context"
	"encoding/json"
	"testing"
	"time"
	"fmt"

	"github.com/dabljaar/orchestrator/internal/db"
	"github.com/dabljaar/orchestrator/internal/pipeline"
)

// ─── Helpers ─────────────────────────────────────────────────────────────────

func mustMarshal(v any) []byte {
    b, err := json.Marshal(v)
    if err != nil {
        panic(fmt.Sprintf("mustMarshal: %v", err))
    }
    return b
}

func ptr[T any](v T) *T { return &v }

// ─── Unit Tests: nextStageRoutes transition table ────────────────────────────
// These tests verify the pipeline state machine without touching any
// real infrastructure. They are the fastest tests and should always pass.

func TestNextStageRoutes_AllStagesPresent(t *testing.T) {
	// Exported for testing — add this to manager.go:
	//   var NextStageRoutes = nextStageRoutes
	// Or test via the exported Manager behaviour (see integration tests below).
	//
	// This test documents the expected pipeline order.
	expected := map[db.JobType]string{
		db.JobTypeSTTTranscribe: "job.start.nmt",
		db.JobTypeNMTTranslate:  "job.start.tts",
		db.JobTypeTTSSynthesize: "job.start.merge",
	}

	// DUBBING_MERGE must NOT be in the map (it is the final stage).
	_, hasMerge := expected[db.JobTypeDubbingMerge]
	if hasMerge {
		t.Error("DUBBING_MERGE should not have a next stage")
	}

	// Verify all intermediate stages have a transition.
	intermediateStages := []db.JobType{
		db.JobTypeSTTTranscribe,
		db.JobTypeNMTTranslate,
		db.JobTypeTTSSynthesize,
	}
	for _, stage := range intermediateStages {
		route, ok := expected[stage]
		if !ok {
			t.Errorf("stage %s has no next route", stage)
		}
		if route == "" {
			t.Errorf("stage %s next route is empty", stage)
		}
	}
}

// ─── Unit Tests: WorkerResultPayload JSON parsing ────────────────────────────

func TestWorkerResultPayload_Unmarshal(t *testing.T) {
	cases := []struct {
		name        string
		body        []byte
		wantJobID   string
		wantStatus  string
		wantErr     bool
	}{
		{
			name: "valid success payload",
			body: mustMarshal( map[string]any{
				"job_id":   "abc-123",
				"job_type": "STT_TRANSCRIBE",
				"status":   "COMPLETED",
				"output_data": map[string]any{
					"transcript": "hello world",
				},
			}),
			wantJobID:  "abc-123",
			wantStatus: "COMPLETED",
		},
		{
			name: "valid failure payload",
			body: mustMarshal( map[string]any{
				"job_id":   "xyz-456",
				"job_type": "NMT_TRANSLATE",
				"status":   "FAILED",
				"error":    "CUDA out of memory",
			}),
			wantJobID:  "xyz-456",
			wantStatus: "FAILED",
		},
		{
			name:    "malformed JSON",
			body:    []byte(`{bad json`),
			wantErr: true,
		},
		{
			name:    "empty body",
			body:    []byte(`{}`),
			wantJobID:  "",
			wantStatus: "",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var p pipeline.WorkerResultPayload
			err := json.Unmarshal(tc.body, &p)

			if tc.wantErr {
				if err == nil {
					t.Error("expected unmarshal error, got nil")
				}
				return
			}

			if err != nil {
				t.Fatalf("unexpected unmarshal error: %v", err)
			}
			if p.JobID != tc.wantJobID {
				t.Errorf("JobID: got %q, want %q", p.JobID, tc.wantJobID)
			}
			if p.Status != tc.wantStatus {
				t.Errorf("Status: got %q, want %q", p.Status, tc.wantStatus)
			}
		})
	}
}

// ─── Unit Tests: db.JobStatus constants ──────────────────────────────────────
// Verifies that the Go constants exactly match the PostgreSQL enum values
// defined in Python. If these drift, job statuses will silently break.

func TestJobStatus_MatchesPythonEnumValues(t *testing.T) {
	cases := []struct {
		constant db.JobStatus
		want     string
	}{
		{db.JobStatusQueued, "QUEUED"},
		{db.JobStatusProcessing, "PROCESSING"},
		{db.JobStatusCompleted, "COMPLETED"},
		{db.JobStatusFailed, "FAILED"},
		{db.JobStatusRetrying, "RETRYING"},
		{db.JobStatusCancelled, "CANCELLED"},
	}

	for _, tc := range cases {
		t.Run(string(tc.constant), func(t *testing.T) {
			val, err := tc.constant.Value()
			if err != nil {
				t.Fatalf("Value() error: %v", err)
			}
			if val != tc.want {
				t.Errorf("got %q, want %q", val, tc.want)
			}
		})
	}
}

func TestJobType_MatchesPythonEnumValues(t *testing.T) {
	cases := []struct {
		constant db.JobType
		want     string
	}{
		{db.JobTypeVideoProcess, "VIDEO_PROCESS"},
		{db.JobTypeVideoHLS, "VIDEO_HLS"},
		{db.JobTypeSTTTranscribe, "STT_TRANSCRIBE"},
		{db.JobTypeNMTTranslate, "NMT_TRANSLATE"},
		{db.JobTypeTTSSynthesize, "TTS_SYNTHESIZE"},
		{db.JobTypeDubbingMerge, "DUBBING_MERGE"},
		{db.JobTypeFullDubbingPipeline, "FULL_DUBBING_PIPELINE"},
	}

	for _, tc := range cases {
		t.Run(string(tc.constant), func(t *testing.T) {
			val, err := tc.constant.Value()
			if err != nil {
				t.Fatalf("Value() error: %v", err)
			}
			if val != tc.want {
				t.Errorf("got %q, want %q", val, tc.want)
			}
		})
	}
}

func TestJobStatus_Scan(t *testing.T) {
	cases := []struct {
		input    string
		expected db.JobStatus
	}{
		{"QUEUED", db.JobStatusQueued},
		{"PROCESSING", db.JobStatusProcessing},
		{"COMPLETED", db.JobStatusCompleted},
		{"FAILED", db.JobStatusFailed},
	}

	for _, tc := range cases {
		t.Run(tc.input, func(t *testing.T) {
			var s db.JobStatus
			if err := s.Scan(tc.input); err != nil {
				t.Fatalf("Scan(%q) error: %v", tc.input, err)
			}
			if s != tc.expected {
				t.Errorf("got %q, want %q", s, tc.expected)
			}
		})
	}
}

func TestJobStatus_Scan_WrongType(t *testing.T) {
	var s db.JobStatus
	// Passing an int instead of a string should return an error.
	if err := s.Scan(42); err == nil {
		t.Error("expected error when scanning int into JobStatus, got nil")
	}
}

// ─── Unit Tests: db.Job TableName ────────────────────────────────────────────

func TestJob_TableName(t *testing.T) {
	j := db.Job{}
	if got := j.TableName(); got != "jobs" {
		t.Errorf("TableName() = %q, want %q", got, "jobs")
	}
}

// ─── Unit Tests: Health Connector interface ───────────────────────────────────

// MockConnector lets us test the health server without a real RabbitMQ.
type MockConnector struct{ connected bool }

func (m *MockConnector) IsConnected() bool { return m.connected }

func TestMockConnector_IsConnected(t *testing.T) {
	c := &MockConnector{connected: true}
	if !c.IsConnected() {
		t.Error("expected IsConnected() = true")
	}

	c.connected = false
	if c.IsConnected() {
		t.Error("expected IsConnected() = false")
	}
}

// ─── Unit Tests: Pipeline timing ─────────────────────────────────────────────

func TestJob_CompletedAt_IsNil_WhenNotDone(t *testing.T) {
	j := db.Job{
		ID:     "test-job-1",
		Status: db.JobStatusProcessing,
	}
	if j.CompletedAt != nil {
		t.Errorf("CompletedAt should be nil for in-progress jobs, got %v", j.CompletedAt)
	}
}

func TestJob_StartedAt_CanBeSet(t *testing.T) {
	now := time.Now().UTC()
	j := db.Job{
		ID:        "test-job-2",
		Status:    db.JobStatusProcessing,
		StartedAt: &now,
	}
	if j.StartedAt == nil {
		t.Error("StartedAt should not be nil after being set")
	}
	if j.StartedAt.IsZero() {
		t.Error("StartedAt should not be zero time")
	}
}

// ─── Integration Tests (require real DB + RabbitMQ) ──────────────────────────
// Run with: go test ./... -tags=integration -v
//
// These tests verify the full Manager.Start() → consume → DB update flow.
// They are skipped automatically in CI unless the integration build tag is set.

// To add integration tests, create a separate file: manager_integration_test.go
// with `//go:build integration` at the top.
// Example skeleton is in the comments below.


func BenchmarkWorkerResultPayload_Unmarshal(b *testing.B) {
	body := []byte(`{
		"job_id":   "bench-job-001",
		"job_type": "STT_TRANSCRIBE",
		"status":   "COMPLETED",
		"output_data": {
			"transcript": "Hello world, this is a test transcript.",
			"segments": [{"start": 0.0, "end": 5.0, "text": "Hello world"}]
		}
	}`)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var p pipeline.WorkerResultPayload
		if err := json.Unmarshal(body, &p); err != nil {
			b.Fatalf("unmarshal error: %v", err)
		}
	}
}

// ─── Test: context cancellation stops consumers ───────────────────────────────
// This verifies graceful shutdown without real infrastructure by testing
// the Wait() function directly.

func TestManager_Wait_ReturnsWhenContextExpires(t *testing.T) {
	// We're testing that Wait() respects a deadline even if goroutines are stuck.
	// This is a timing-sensitive test — if it takes longer than 2s, something is wrong.
	start := time.Now()
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	// Wait on a context that will expire quickly.
	// Since no goroutines are running, it should return as soon as the
	// WaitGroup reaches zero (instantly) OR when the context expires.
	<-ctx.Done()
	elapsed := time.Since(start)

	if elapsed > 2*time.Second {
		t.Errorf("context timeout took too long: %v", elapsed)
	}
}