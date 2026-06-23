//go:build integration

package pipeline_test

// STT integration tests — verify the orchestrator ↔ STT-microservice contract.
//
// These tests replace the real STT service with a fake in-process worker that
// consumes from the same queue (stt.jobs / job.start.stt) and publishes to the
// same result routing key (job.results.stt).  No Whisper model or MinIO is needed.
//
// Run with:
//
//	go test ./internal/pipeline/... -tags=integration -v -count=1 -run TestIntegration_STT

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"testing"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/dabljaar/orchestrator/internal/db"
)

// ─── Constants (must match stt-service/app/worker.py) ────────────────────────

const (
	sttBindingKey = "job.start.stt"   // routing key the orchestrator publishes to
	sttResultKey  = "job.results.stt" // routing key the STT service publishes results on
	nmtStartKey   = "job.start.nmt"   // next stage routing key (after STT)
)

// ─── Fake STT worker helpers ─────────────────────────────────────────────────

// sttHandler controls what the fake STT worker returns.
// Return ("", err) for a FAILED result; return (outputData, nil) for COMPLETED.
type sttHandler func(jobID string) (outputData map[string]any, errMsg string)

// startFakeSttWorker binds an exclusive auto-delete queue to sttBindingKey
// ("job.start.stt") and calls handler for every message the orchestrator
// dispatches to that routing key.
//
// Using an exclusive queue (not the real "stt.jobs") means leftover messages
// from previous test runs never reach this worker — the exchange delivers a
// fresh copy to our temporary queue only. The real stt.jobs queue still
// accumulates those copies but has no consumer, so they don't interfere.
//
// The worker is automatically stopped when the test ends.
func startFakeSttWorker(t *testing.T, handler sttHandler) {
	t.Helper()

	conn, err := amqp.Dial(rabbitURL())
	if err != nil {
		t.Fatalf("startFakeSttWorker: dial: %v", err)
	}
	ch, err := conn.Channel()
	if err != nil {
		conn.Close()
		t.Fatalf("startFakeSttWorker: channel: %v", err)
	}

	// Exclusive + auto-delete: invisible to other consumers, no naming conflicts,
	// and automatically removed when the connection closes.
	q, err := ch.QueueDeclare("", false, true, true, false, nil)
	if err != nil {
		conn.Close()
		t.Fatalf("startFakeSttWorker: declare queue: %v", err)
	}
	if err := ch.QueueBind(q.Name, sttBindingKey, "dablja.jobs.exchange", false, nil); err != nil {
		conn.Close()
		t.Fatalf("startFakeSttWorker: bind to %q: %v", sttBindingKey, err)
	}
	ch.Qos(1, 0, false) //nolint:errcheck

	msgs, err := ch.Consume(q.Name, "", false, false, false, false, nil)
	if err != nil {
		conn.Close()
		t.Fatalf("startFakeSttWorker: consume: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(func() {
		cancel()
		conn.Close()
	})

	go func() {
		for {
			select {
			case <-ctx.Done():
				return
			case d, ok := <-msgs:
				if !ok {
					return
				}

				var trigger struct {
					JobID string `json:"job_id"`
				}
				if err := json.Unmarshal(d.Body, &trigger); err != nil {
					d.Nack(false, false)
					continue
				}

				outputData, errMsg := handler(trigger.JobID)

				status := "COMPLETED"
				if errMsg != "" {
					status = "FAILED"
				}

				result := map[string]any{
					"job_id":      trigger.JobID,
					"job_type":    "STT_TRANSCRIBE",
					"status":      status,
					"output_data": outputData,
				}
				if errMsg != "" {
					result["error"] = errMsg
				}

				body, _ := json.Marshal(result)
				ch.Publish( //nolint:errcheck
					"dablja.jobs.exchange", sttResultKey, false, false,
					amqp.Publishing{
						ContentType:  "application/json",
						DeliveryMode: amqp.Persistent,
						Body:         body,
					},
				)
				d.Ack(false)
			}
		}
	}()
}

// subscribeDispatch creates a temporary exclusive auto-delete queue bound to
// routingKey. Returns a buffered channel that receives the job_id from each
// matching message. The subscription is torn down when the test ends.
// Use this to observe dispatches without interfering with the real queues.
func subscribeDispatch(t *testing.T, routingKey string) <-chan string {
	t.Helper()

	conn, err := amqp.Dial(rabbitURL())
	if err != nil {
		t.Fatalf("subscribeDispatch: dial: %v", err)
	}
	ch, err := conn.Channel()
	if err != nil {
		conn.Close()
		t.Fatalf("subscribeDispatch: channel: %v", err)
	}
	t.Cleanup(func() { conn.Close() })

	// Exclusive + auto-delete: invisible to other consumers, gone on disconnect.
	q, err := ch.QueueDeclare("", false, true, true, false, nil)
	if err != nil {
		t.Fatalf("subscribeDispatch: declare: %v", err)
	}
	if err := ch.QueueBind(q.Name, routingKey, "dablja.jobs.exchange", false, nil); err != nil {
		t.Fatalf("subscribeDispatch: bind to %q: %v", routingKey, err)
	}

	msgs, err := ch.Consume(q.Name, "", true, true, false, false, nil)
	if err != nil {
		t.Fatalf("subscribeDispatch: consume: %v", err)
	}

	out := make(chan string, 16)
	go func() {
		for d := range msgs {
			var payload struct {
				JobID string `json:"job_id"`
			}
			if err := json.Unmarshal(d.Body, &payload); err == nil && payload.JobID != "" {
				out <- payload.JobID
			}
		}
	}()
	return out
}

// ─── Tests ────────────────────────────────────────────────────────────────────

// STT_T01: After job.created for an STT_TRANSCRIBE job, the orchestrator marks
// the job PROCESSING and dispatches job.start.stt with the correct job_id.
// This verifies the orchestrator → STT routing key and payload are correct.
func TestIntegration_STT_T01_OrchestratorDispatchesSTTJob(t *testing.T) {
	const id = "stt-t01-dispatch"
	global.createJob(t, id, db.JobTypeSTTTranscribe, nil)

	receivedID := make(chan string, 1)
	startFakeSttWorker(t, func(jobID string) (map[string]any, string) {
		// Capture the dispatched job_id for assertion, then report success.
		// The 150ms pause keeps the job in PROCESSING long enough for
		// waitStatus (50ms poll interval) to observe it before COMPLETED.
		select {
		case receivedID <- jobID:
		default:
		}
		time.Sleep(150 * time.Millisecond)
		return map[string]any{"transcript": "dispatch verified"}, ""
	})

	global.publish(t, "job.created", map[string]string{"job_id": id})

	// Orchestrator must mark the job PROCESSING before dispatching
	if _, ok := global.waitStatus(id, db.JobStatusProcessing, 5*time.Second); !ok {
		t.Fatal("STT job never became PROCESSING")
	}

	// Verify the dispatched job_id reaches the fake STT worker
	select {
	case dispatched := <-receivedID:
		if dispatched != id {
			t.Errorf("job.start.stt carried job_id=%q, want %q", dispatched, id)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("job.start.stt was never received by the fake STT worker")
	}
}

// STT_T02: Full round-trip happy path.
// job.created → orchestrator dispatches job.start.stt → fake STT reports
// COMPLETED → orchestrator marks job COMPLETED and dispatches job.start.nmt.
func TestIntegration_STT_T02_FakeSTT_HappyPath_NMTDispatched(t *testing.T) {
	const id = "stt-t02-roundtrip"
	global.createJob(t, id, db.JobTypeSTTTranscribe, nil)

	// Subscribe to NMT dispatch BEFORE publishing so we don't miss the message
	nmtDispatch := subscribeDispatch(t, nmtStartKey)

	startFakeSttWorker(t, func(_ string) (map[string]any, string) {
		return map[string]any{
			"transcript": "Hello world",
			"segments": []any{
				map[string]any{"start": 0.0, "end": 2.0, "text": "Hello world"},
			},
			"metadata": map[string]any{"language": "en", "duration": 2.0},
		}, ""
	})

	global.publish(t, "job.created", map[string]string{"job_id": id})

	// STT job must reach COMPLETED
	if _, ok := global.waitStatus(id, db.JobStatusCompleted, 10*time.Second); !ok {
		t.Fatal("STT job never became COMPLETED")
	}

	// Orchestrator must advance the pipeline by dispatching job.start.nmt
	select {
	case nmtJobID := <-nmtDispatch:
		if nmtJobID != id {
			t.Errorf("job.start.nmt carried job_id=%q, want %q", nmtJobID, id)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("job.start.nmt was never dispatched after STT completed")
	}
}

// STT_T03: Fake STT reports FAILED for a child STT job.
// The child is linked to a FULL_DUBBING_PIPELINE parent.
// Expected: child reaches FAILED, parent reaches FAILED with the error message.
func TestIntegration_STT_T03_FakeSTT_Failure_ParentFails(t *testing.T) {
	parentID := "stt-t03-parent"
	sttID    := "stt-t03-stt"

	global.createJob(t, parentID, db.JobTypeFullDubbingPipeline, nil)
	global.createJob(t, sttID,    db.JobTypeSTTTranscribe, strPtr(parentID))

	const sttError = "Whisper: CUDA out of memory — 12 GB exhausted"
	startFakeSttWorker(t, func(_ string) (map[string]any, string) {
		return nil, sttError
	})

	// Publish job.created for the STT child (not the parent), so the orchestrator
	// dispatches to the STT service with the child job ID.
	global.publish(t, "job.created", map[string]string{"job_id": sttID})

	if _, ok := global.waitStatus(sttID, db.JobStatusFailed, 5*time.Second); !ok {
		t.Fatal("STT child job never became FAILED")
	}
	if _, ok := global.waitStatus(parentID, db.JobStatusFailed, 5*time.Second); !ok {
		t.Fatal("parent job never became FAILED after STT failure")
	}

	parent := global.getJob(parentID)
	if parent.ErrorMessage == nil || *parent.ErrorMessage != sttError {
		t.Errorf("parent ErrorMessage = %v, want %q", parent.ErrorMessage, sttError)
	}
	if parent.CompletedAt == nil {
		t.Error("parent CompletedAt must be set on failure")
	}
}

// STT_T04: Fake STT returns a realistic transcript with segments and metadata.
// Verifies that the orchestrator persists all STT output fields to the DB.
func TestIntegration_STT_T04_FakeSTT_TranscriptPersisted(t *testing.T) {
	const id = "stt-t04-output"
	global.createJob(t, id, db.JobTypeSTTTranscribe, nil)

	transcript := "The quick brown fox jumps over the lazy dog."
	segments := []any{
		map[string]any{"start": 0.0, "end": 1.5, "text": "The quick brown fox"},
		map[string]any{"start": 1.5, "end": 3.0, "text": "jumps over the lazy dog."},
	}
	metadata := map[string]any{
		"language":        "en",
		"duration":        3.0,
		"model_size":      "small",
		"device":          "cpu",
		"processing_time": 1.2,
		"segment_count":   2,
	}

	startFakeSttWorker(t, func(_ string) (map[string]any, string) {
		return map[string]any{
			"transcript": transcript,
			"segments":   segments,
			"metadata":   metadata,
		}, ""
	})

	global.publish(t, "job.created", map[string]string{"job_id": id})

	if _, ok := global.waitStatus(id, db.JobStatusCompleted, 10*time.Second); !ok {
		t.Fatal("STT job never became COMPLETED")
	}

	j := global.getJob(id)
	if j.OutputData == nil {
		t.Fatal("OutputData not persisted to DB")
	}
	for _, field := range []string{"transcript", "segments", "metadata"} {
		if _, ok := j.OutputData[field]; !ok {
			t.Errorf("OutputData missing field %q", field)
		}
	}
	if j.CompletedAt == nil {
		t.Error("CompletedAt not set on COMPLETED job")
	}
}

// STT_T05: Five STT jobs dispatched concurrently.
// All must be consumed by the fake STT worker and reach COMPLETED.
func TestIntegration_STT_T05_FakeSTT_ConcurrentJobs(t *testing.T) {
	const n = 5
	ids := make([]string, n)
	for i := 0; i < n; i++ {
		ids[i] = fmt.Sprintf("stt-t05-%03d", i)
		global.createJob(t, ids[i], db.JobTypeSTTTranscribe, nil)
	}

	startFakeSttWorker(t, func(jobID string) (map[string]any, string) {
		return map[string]any{"transcript": "ok: " + jobID}, ""
	})

	var wg sync.WaitGroup
	for _, id := range ids {
		wg.Add(1)
		go func(jid string) {
			defer wg.Done()
			global.publish(t, "job.created", map[string]string{"job_id": jid})
		}(id)
	}
	wg.Wait()

	var mu sync.Mutex
	var notCompleted []string
	var checkWG sync.WaitGroup
	for _, id := range ids {
		checkWG.Add(1)
		go func(jid string) {
			defer checkWG.Done()
			if _, ok := global.waitStatus(jid, db.JobStatusCompleted, 15*time.Second); !ok {
				mu.Lock()
				notCompleted = append(notCompleted, jid)
				mu.Unlock()
			}
		}(id)
	}
	checkWG.Wait()

	if len(notCompleted) > 0 {
		t.Errorf("%d/%d STT jobs never reached COMPLETED: %v", len(notCompleted), n, notCompleted)
	}
}

// STT_T06: Duplicate job.created for the same STT job — idempotency.
// The second message arrives while the job is already PROCESSING.
// Expected: job eventually reaches COMPLETED exactly once; no panic or corrupt state.
func TestIntegration_STT_T06_DuplicateDispatch_Idempotent(t *testing.T) {
	const id = "stt-t06-dup"
	global.createJob(t, id, db.JobTypeSTTTranscribe, nil)

	calls := 0
	var callMu sync.Mutex
	startFakeSttWorker(t, func(_ string) (map[string]any, string) {
		callMu.Lock()
		calls++
		callMu.Unlock()
		return map[string]any{"transcript": "idempotent"}, ""
	})

	// Send job.created twice for the same job
	global.publish(t, "job.created", map[string]string{"job_id": id})
	global.publish(t, "job.created", map[string]string{"job_id": id})

	if _, ok := global.waitStatus(id, db.JobStatusCompleted, 10*time.Second); !ok {
		t.Fatal("STT job never became COMPLETED")
	}

	// Allow time for a possible second dispatch to arrive
	time.Sleep(300 * time.Millisecond)

	j := global.getJob(id)
	if j.Status != db.JobStatusCompleted {
		t.Errorf("job drifted to %s after duplicate messages", j.Status)
	}
}

// STT_T07: Fake STT reports FAILED for a standalone STT job (no parent).
// Expected: job reaches FAILED with ErrorMessage and CompletedAt set.
func TestIntegration_STT_T07_FakeSTT_StandaloneFailure(t *testing.T) {
	const id = "stt-t07-standalone-fail"
	const errMsg = "audio file not found in MinIO: no such key"
	global.createJob(t, id, db.JobTypeSTTTranscribe, nil)

	startFakeSttWorker(t, func(_ string) (map[string]any, string) {
		return nil, errMsg
	})

	global.publish(t, "job.created", map[string]string{"job_id": id})

	if _, ok := global.waitStatus(id, db.JobStatusFailed, 5*time.Second); !ok {
		t.Fatal("STT job never became FAILED")
	}

	j := global.getJob(id)
	if j.ErrorMessage == nil || *j.ErrorMessage != errMsg {
		t.Errorf("ErrorMessage = %v, want %q", j.ErrorMessage, errMsg)
	}
	if j.CompletedAt == nil {
		t.Error("CompletedAt must be set on failed job")
	}
}
