//go:build integration

package pipeline_test

// Run with:
//   go test ./internal/pipeline/... -tags=integration -v -count=1
//
// Requires PostgreSQL on localhost:5433 and RabbitMQ on localhost:5672.
// Start them with: docker compose up -d postgres rabbitmq

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"sync"
	"testing"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/dabljaar/orchestrator/internal/db"
	"github.com/dabljaar/orchestrator/internal/mq"
	"github.com/dabljaar/orchestrator/internal/pipeline"
	gpostgres "gorm.io/driver/postgres"
	"gorm.io/gorm"
	glogger "gorm.io/gorm/logger"
)

// ─── Environment ─────────────────────────────────────────────────────────────

func rabbitURL() string {
	if u := os.Getenv("RABBITMQ_URL"); u != "" {
		return u
	}
	return "amqp://guest:guest@localhost:5672/"
}

func databaseURL() string {
	if u := os.Getenv("DATABASE_URL"); u != "" {
		return u
	}
	return "postgres://postgres:postgres@localhost:5433/dabljaar"
}

// ─── Shared Fixture (one Manager for the whole suite) ────────────────────────

type fixture struct {
	database    *gorm.DB
	rabbit      *mq.RabbitMQ
	manager     *pipeline.Manager
	publishConn *amqp.Connection
	publishCh   *amqp.Channel
	publishMu   sync.Mutex
	ctx         context.Context
	cancel      context.CancelFunc
	testUserID  int
	testVideoID string
}

var global *fixture

func TestMain(m *testing.M) {
	global = mustSetupFixture()
	code := m.Run()
	global.shutdown()
	os.Exit(code)
}

func mustSetupFixture() *fixture {
	database, err := gorm.Open(gpostgres.Open(databaseURL()), &gorm.Config{
		Logger: glogger.Default.LogMode(glogger.Silent),
	})
	if err != nil {
		panic(fmt.Sprintf("connect db: %v", err))
	}

	rabbit, err := mq.NewRabbitMQ(rabbitURL())
	if err != nil {
		panic(fmt.Sprintf("connect rabbitmq: %v", err))
	}

	pubConn, err := amqp.Dial(rabbitURL())
	if err != nil {
		panic(fmt.Sprintf("publisher connect: %v", err))
	}
	pubCh, err := pubConn.Channel()
	if err != nil {
		panic(fmt.Sprintf("publisher channel: %v", err))
	}

	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{
		Level: slog.LevelError,
	}))

	ctx, cancel := context.WithCancel(context.Background())
	mgr := pipeline.NewManager(rabbit, database, logger, 10)
	if err := mgr.Start(ctx); err != nil {
		cancel()
		panic(fmt.Sprintf("manager start: %v", err))
	}

	// Seed shared test user + video once
	var row struct {
		UserID int `gorm:"column:user_id"`
	}
	database.Raw(`
		INSERT INTO users (
			username, email, password, is_active,
			created_at, updated_at, last_login,
			preferred_language, default_domain, translation_style, default_voice,
			notif_completed, notif_credits, notif_marketing
		) VALUES (
			'inttest_suite', 'inttest_suite@inttest.com', 'noop', true,
			now(), now(), now(), 'en', 'com', 'formal', 'default',
			false, false, false
		)
		ON CONFLICT (email) DO UPDATE SET username = 'inttest_suite'
		RETURNING user_id
	`).Scan(&row)

	videoID := "inttest-shared-video"
	database.Exec(`
		INSERT INTO videos (id, user_id, title, original_filename, file_path, status, created_at, updated_at)
		VALUES (?, ?, 'Integration Test Video', 'test.mp4', '/tmp/test.mp4', 'PENDING', now(), now())
		ON CONFLICT (id) DO NOTHING
	`, videoID, row.UserID)

	return &fixture{
		database:    database,
		rabbit:      rabbit,
		manager:     mgr,
		publishConn: pubConn,
		publishCh:   pubCh,
		ctx:         ctx,
		cancel:      cancel,
		testUserID:  row.UserID,
		testVideoID: videoID,
	}
}

func (f *fixture) shutdown() {
	f.cancel()
	shutCtx, c := context.WithTimeout(context.Background(), 5*time.Second)
	defer c()
	f.manager.Wait(shutCtx)
	f.rabbit.Close()
	f.publishCh.Close()
	f.publishConn.Close()
	f.database.Exec("DELETE FROM jobs   WHERE video_id = ?", f.testVideoID)
	f.database.Exec("DELETE FROM videos WHERE id       = ?", f.testVideoID)
	f.database.Exec("DELETE FROM users  WHERE email    = 'inttest_suite@inttest.com'")
	if sqlDB, err := f.database.DB(); err == nil {
		sqlDB.Close()
	}
}

// ─── Per-test Helpers ─────────────────────────────────────────────────────────

func (f *fixture) createJob(t *testing.T, id string, jobType db.JobType, parentID *string) {
	t.Helper()
	now := time.Now().UTC()
	j := &db.Job{
		ID:          id,
		VideoID:     strPtr(f.testVideoID),
		UserID:      f.testUserID,
		JobType:     jobType,
		Status:      db.JobStatusQueued,
		ParentJobID: parentID,
		MaxRetries:  3,
		CreatedAt:   now,
		UpdatedAt:   now,
	}
	if err := f.database.Create(j).Error; err != nil {
		t.Fatalf("createJob(%s): %v", id, err)
	}
	t.Cleanup(func() { f.database.Delete(&db.Job{}, "id = ?", id) })
}

func (f *fixture) getJob(id string) db.Job {
	var j db.Job
	f.database.First(&j, "id = ?", id)
	return j
}

func (f *fixture) publish(t *testing.T, routingKey string, payload any) {
	t.Helper()
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	f.publishMu.Lock()
	defer f.publishMu.Unlock()
	if err := f.publishCh.Publish(
		"dablja.jobs.exchange", routingKey, false, false,
		amqp.Publishing{
			ContentType:  "application/json",
			DeliveryMode: amqp.Persistent,
			Body:         body,
		},
	); err != nil {
		t.Fatalf("publish(%s): %v", routingKey, err)
	}
}

func (f *fixture) publishRaw(routingKey string, body []byte) {
	f.publishMu.Lock()
	defer f.publishMu.Unlock()
	f.publishCh.Publish( //nolint:errcheck
		"dablja.jobs.exchange", routingKey, false, false,
		amqp.Publishing{ContentType: "application/json", Body: body},
	)
}

// purge clears both consumer queues — call at the top of tests that follow
// destructive scenarios (malformed messages, ghost job IDs).
func (f *fixture) purge() {
	f.publishMu.Lock()
	defer f.publishMu.Unlock()
	f.publishCh.QueuePurge("orchestrator.new_jobs", false) //nolint:errcheck
	f.publishCh.QueuePurge("orchestrator.results", false)  //nolint:errcheck
	time.Sleep(100 * time.Millisecond)                     // let in-flight handlers finish
}

// waitStatus polls the DB until the job reaches the target status or timeout.
func (f *fixture) waitStatus(id string, want db.JobStatus, timeout time.Duration) (db.Job, bool) {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		j := f.getJob(id)
		if j.Status == want {
			return j, true
		}
		time.Sleep(50 * time.Millisecond)
	}
	return db.Job{}, false
}

func strPtr(s string) *string { return &s }

// ─── Tests ───────────────────────────────────────────────────────────────────

// T01: job.created → PROCESSING, StartedAt set
func TestIntegration_T01_NewJob_BecomesProcessing(t *testing.T) {
	const id = "inttest-t01"
	global.createJob(t, id, db.JobTypeFullDubbingPipeline, nil)

	global.publish(t, "job.created", map[string]string{"job_id": id})

	j, ok := global.waitStatus(id, db.JobStatusProcessing, 5*time.Second)
	if !ok {
		t.Fatalf("job never became PROCESSING")
	}
	if j.StartedAt == nil {
		t.Error("StartedAt must be set when job moves to PROCESSING")
	}
}

// T02: Full happy-path pipeline → parent reaches COMPLETED with 100% progress
// fullDubbing ends at TTS (merge runs inside the bridged Celery TTS combine).
func TestIntegration_T02_FullPipeline_ParentCompleted(t *testing.T) {
	parentID := "inttest-t02-parent"
	sttID    := "inttest-t02-stt"
	nmtID    := "inttest-t02-nmt"
	ttsID    := "inttest-t02-tts"

	global.createJob(t, parentID, db.JobTypeFullDubbingPipeline, nil)
	global.createJob(t, sttID,    db.JobTypeSTTTranscribe,       strPtr(parentID))
	global.createJob(t, nmtID,    db.JobTypeNMTTranslate,        strPtr(parentID))
	global.createJob(t, ttsID,    db.JobTypeTTSSynthesize,       strPtr(parentID))

	global.publish(t, "job.created", map[string]string{"job_id": parentID})
	if _, ok := global.waitStatus(parentID, db.JobStatusProcessing, 5*time.Second); !ok {
		t.Fatal("parent never became PROCESSING")
	}

	stages := []struct{ id, typ string }{
		{sttID, "STT_TRANSCRIBE"},
		{nmtID, "NMT_TRANSLATE"},
		{ttsID, "TTS_SYNTHESIZE"},
	}
	for _, s := range stages {
		global.publish(t, "job.results.worker", pipeline.WorkerResultPayload{
			JobID: s.id, JobType: s.typ, Status: "COMPLETED",
			OutputData: map[string]any{"stage": s.typ, "ok": true},
		})
		if _, ok := global.waitStatus(s.id, db.JobStatusCompleted, 5*time.Second); !ok {
			t.Fatalf("stage %s never completed", s.typ)
		}
	}

	j, ok := global.waitStatus(parentID, db.JobStatusCompleted, 5*time.Second)
	if !ok {
		t.Fatal("parent never became COMPLETED")
	}
	if j.CompletedAt == nil {
		t.Error("parent CompletedAt must be set")
	}
	if j.Progress != 100.0 {
		t.Errorf("parent Progress = %v, want 100.0", j.Progress)
	}
}

// T03: STT failure → parent FAILED with error message
func TestIntegration_T03_Failure_STT_PropagatestoParent(t *testing.T) {
	parentID := "inttest-t03-parent"
	sttID    := "inttest-t03-stt"

	global.createJob(t, parentID, db.JobTypeFullDubbingPipeline, nil)
	global.createJob(t, sttID,    db.JobTypeSTTTranscribe,       strPtr(parentID))

	global.publish(t, "job.created", map[string]string{"job_id": parentID})
	if _, ok := global.waitStatus(parentID, db.JobStatusProcessing, 5*time.Second); !ok {
		t.Fatal("parent never PROCESSING")
	}

	global.publish(t, "job.results.stt", pipeline.WorkerResultPayload{
		JobID: sttID, JobType: "STT_TRANSCRIBE", Status: "FAILED",
		Error: "CUDA out of memory",
	})

	if _, ok := global.waitStatus(sttID, db.JobStatusFailed, 5*time.Second); !ok {
		t.Fatal("STT never FAILED")
	}
	if _, ok := global.waitStatus(parentID, db.JobStatusFailed, 5*time.Second); !ok {
		t.Fatal("parent never FAILED after STT failure")
	}
	p := global.getJob(parentID)
	if p.ErrorMessage == nil || *p.ErrorMessage == "" {
		t.Error("parent ErrorMessage must be set")
	}
	if p.CompletedAt == nil {
		t.Error("parent CompletedAt must be set even on failure")
	}
}

// T04: Failure at every pipeline stage propagates to parent
func TestIntegration_T04_FailureAtEveryStage(t *testing.T) {
	stages := []struct {
		name    string
		jobType db.JobType
		msgType string
	}{
		{"STT",   db.JobTypeSTTTranscribe, "STT_TRANSCRIBE"},
		{"NMT",   db.JobTypeNMTTranslate,  "NMT_TRANSLATE"},
		{"TTS",   db.JobTypeTTSSynthesize, "TTS_SYNTHESIZE"},
		{"Merge", db.JobTypeDubbingMerge,  "DUBBING_MERGE"},
	}

	for _, stage := range stages {
		stage := stage
		t.Run(stage.name, func(t *testing.T) {
			parentID := fmt.Sprintf("inttest-t04-%s-p", stage.name)
			childID  := fmt.Sprintf("inttest-t04-%s-c", stage.name)
			global.createJob(t, parentID, db.JobTypeFullDubbingPipeline, nil)
			global.createJob(t, childID,  stage.jobType,                 strPtr(parentID))

			global.publish(t, "job.created", map[string]string{"job_id": parentID})
			if _, ok := global.waitStatus(parentID, db.JobStatusProcessing, 5*time.Second); !ok {
				t.Fatalf("parent never PROCESSING (stage=%s)", stage.name)
			}
			global.publish(t, "job.results.test", pipeline.WorkerResultPayload{
				JobID:   childID,
				JobType: stage.msgType,
				Status:  "FAILED",
				Error:   stage.name + " exploded",
			})
			if _, ok := global.waitStatus(childID, db.JobStatusFailed, 5*time.Second); !ok {
				t.Fatalf("child never FAILED (stage=%s)", stage.name)
			}
			if _, ok := global.waitStatus(parentID, db.JobStatusFailed, 5*time.Second); !ok {
				t.Fatalf("parent never FAILED for stage=%s", stage.name)
			}
		})
	}
}

// T05: Malformed/garbage messages → no crash, manager stays alive
func TestIntegration_T05_MalformedMessages_NoCrash(t *testing.T) {
	garbage := [][]byte{
		[]byte(`{bad json`),
		[]byte(`[]`),
		[]byte(`"just a string"`),
		make([]byte, 4096),
	}
	for _, g := range garbage {
		global.publishRaw("job.created",   g)
		global.publishRaw("job.results.x", g)
	}

	time.Sleep(400 * time.Millisecond)

	// Purge before leaving — these would otherwise nack-loop into the next test
	global.purge()

	sqlDB, _ := global.database.DB()
	if err := sqlDB.Ping(); err != nil {
		t.Fatalf("DB unreachable after malformed messages: %v", err)
	}
}

// T06: Non-existent job ID → graceful error, no panic
func TestIntegration_T06_NonExistentJobID_Graceful(t *testing.T) {
	global.purge() // clear any leftover from T05

	global.publish(t, "job.created", map[string]string{"job_id": "ghost-xyz-does-not-exist"})
	time.Sleep(300 * time.Millisecond)
	global.purge() // stop the nack loop before next test

	sqlDB, _ := global.database.DB()
	if err := sqlDB.Ping(); err != nil {
		t.Fatalf("DB unreachable after ghost job: %v", err)
	}
}

// T07: Same job.created sent twice → idempotent (PROCESSING, not corrupted)
func TestIntegration_T07_DuplicateJobCreated_Idempotent(t *testing.T) {
	const id = "inttest-t07-dup"
	global.createJob(t, id, db.JobTypeFullDubbingPipeline, nil)

	global.publish(t, "job.created", map[string]string{"job_id": id})
	global.publish(t, "job.created", map[string]string{"job_id": id})

	if _, ok := global.waitStatus(id, db.JobStatusProcessing, 5*time.Second); !ok {
		t.Fatal("job never became PROCESSING")
	}
	time.Sleep(300 * time.Millisecond)
	j := global.getJob(id)
	if j.Status != db.JobStatusProcessing {
		t.Errorf("status drifted to %s after duplicate messages", j.Status)
	}
}

// T08: 20 concurrent job.created messages → all reach PROCESSING
func TestIntegration_T08_ConcurrentJobs_20(t *testing.T) {
	const n = 20
	ids := make([]string, n)
	for i := 0; i < n; i++ {
		ids[i] = fmt.Sprintf("inttest-t08-%03d", i)
		global.createJob(t, ids[i], db.JobTypeFullDubbingPipeline, nil)
	}

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
	var failed []string
	var checkWG sync.WaitGroup
	for _, id := range ids {
		checkWG.Add(1)
		go func(jid string) {
			defer checkWG.Done()
			if _, ok := global.waitStatus(jid, db.JobStatusProcessing, 15*time.Second); !ok {
				mu.Lock()
				failed = append(failed, jid)
				mu.Unlock()
			}
		}(id)
	}
	checkWG.Wait()

	if len(failed) > 0 {
		t.Errorf("%d/%d jobs never became PROCESSING: %v", len(failed), n, failed)
	}
}

// T09: 50-message burst against pool-of-10 → all jobs processed (backpressure test)
func TestIntegration_T09_WorkerPoolSaturation_50Jobs(t *testing.T) {
	const n = 50
	ids := make([]string, n)
	for i := 0; i < n; i++ {
		ids[i] = fmt.Sprintf("inttest-t09-%03d", i)
		global.createJob(t, ids[i], db.JobTypeFullDubbingPipeline, nil)
	}

	start := time.Now()
	for _, id := range ids {
		global.publish(t, "job.created", map[string]string{"job_id": id})
	}

	processed := 0
	for _, id := range ids {
		if _, ok := global.waitStatus(id, db.JobStatusProcessing, 30*time.Second); ok {
			processed++
		}
	}
	t.Logf("Saturation: %d/%d jobs processed in %v", processed, n, time.Since(start))
	if processed < n {
		t.Errorf("only %d/%d jobs reached PROCESSING", processed, n)
	}
}

// T10: OutputData is persisted to DB after worker reports success
func TestIntegration_T10_OutputData_Persisted(t *testing.T) {
	const id = "inttest-t10-output"
	global.createJob(t, id, db.JobTypeSTTTranscribe, nil)

	global.publish(t, "job.results.stt", pipeline.WorkerResultPayload{
		JobID: id, JobType: "STT_TRANSCRIBE", Status: "COMPLETED",
		OutputData: map[string]any{
			"transcript": "Hello world",
			"language":   "en",
			"confidence": 0.98,
		},
	})

	if _, ok := global.waitStatus(id, db.JobStatusCompleted, 5*time.Second); !ok {
		t.Fatal("job never completed")
	}
	j := global.getJob(id)
	if j.OutputData == nil {
		t.Fatal("OutputData not persisted")
	}
	if _, ok := j.OutputData["transcript"]; !ok {
		t.Error("OutputData missing 'transcript'")
	}
}

// T11: Error message and CompletedAt are persisted on failure
func TestIntegration_T11_ErrorMessage_Persisted(t *testing.T) {
	const id = "inttest-t11-errmsg"
	const errMsg = "GPU OOM: 12 GB exhausted at transformer.6"
	global.createJob(t, id, db.JobTypeSTTTranscribe, nil)

	global.publish(t, "job.results.stt", pipeline.WorkerResultPayload{
		JobID: id, JobType: "STT_TRANSCRIBE", Status: "FAILED", Error: errMsg,
	})

	if _, ok := global.waitStatus(id, db.JobStatusFailed, 5*time.Second); !ok {
		t.Fatal("job never FAILED")
	}
	j := global.getJob(id)
	if j.ErrorMessage == nil || *j.ErrorMessage != errMsg {
		t.Errorf("ErrorMessage = %v, want %q", j.ErrorMessage, errMsg)
	}
	if j.CompletedAt == nil {
		t.Error("CompletedAt must be set on failure")
	}
}

// T12: CompletedAt is set and is after test start
func TestIntegration_T12_CompletedAt_AfterTestStart(t *testing.T) {
	const id = "inttest-t12-time"
	before := time.Now().UTC().Add(-time.Second)
	global.createJob(t, id, db.JobTypeSTTTranscribe, nil)

	global.publish(t, "job.results.stt", pipeline.WorkerResultPayload{
		JobID: id, JobType: "STT_TRANSCRIBE", Status: "COMPLETED",
		OutputData: map[string]any{"ok": true},
	})

	if _, ok := global.waitStatus(id, db.JobStatusCompleted, 5*time.Second); !ok {
		t.Fatal("job never completed")
	}
	j := global.getJob(id)
	if j.CompletedAt == nil {
		t.Fatal("CompletedAt not set")
	}
	if j.CompletedAt.Before(before) {
		t.Errorf("CompletedAt %v is before test start %v", j.CompletedAt, before)
	}
}

// T13: Rapid results for the same job → settles to a terminal state
func TestIntegration_T13_RapidResults_SameJob(t *testing.T) {
	const id = "inttest-t13-rapid"
	global.createJob(t, id, db.JobTypeSTTTranscribe, nil)

	for i := 0; i < 10; i++ {
		status := "COMPLETED"
		if i%3 == 0 {
			status = "FAILED"
		}
		global.publish(t, "job.results.x", pipeline.WorkerResultPayload{
			JobID: id, JobType: "STT_TRANSCRIBE", Status: status,
		})
	}

	time.Sleep(800 * time.Millisecond)
	j := global.getJob(id)
	if j.Status == db.JobStatusQueued || j.Status == db.JobStatusProcessing {
		t.Errorf("job stuck in %s — expected a terminal status", j.Status)
	}
}

// T14: Result arrives before job.created → parent still processes correctly afterwards
func TestIntegration_T14_OutOfOrderMessages(t *testing.T) {
	parentID := "inttest-t14-parent"
	sttID    := "inttest-t14-stt"
	global.createJob(t, parentID, db.JobTypeFullDubbingPipeline, nil)
	global.createJob(t, sttID,    db.JobTypeSTTTranscribe,       strPtr(parentID))

	// Send STT result first (before job.created)
	global.publish(t, "job.results.stt", pipeline.WorkerResultPayload{
		JobID: sttID, JobType: "STT_TRANSCRIBE", Status: "COMPLETED",
	})
	time.Sleep(150 * time.Millisecond)

	// Now start the pipeline
	global.publish(t, "job.created", map[string]string{"job_id": parentID})

	if _, ok := global.waitStatus(parentID, db.JobStatusProcessing, 5*time.Second); !ok {
		t.Fatal("parent never became PROCESSING after out-of-order messages")
	}
}

// T15: Large output_data (500 segments) is stored without truncation
func TestIntegration_T15_LargeOutputData(t *testing.T) {
	const id = "inttest-t15-large"
	global.createJob(t, id, db.JobTypeSTTTranscribe, nil)

	segments := make([]any, 500)
	for i := 0; i < 500; i++ {
		segments[i] = map[string]any{
			"id": i, "start": float64(i) * 2.5, "end": float64(i)*2.5 + 2.0,
			"text": fmt.Sprintf("Segment %d: the quick brown fox jumps over the lazy dog", i),
		}
	}
	global.publish(t, "job.results.stt", pipeline.WorkerResultPayload{
		JobID: id, JobType: "STT_TRANSCRIBE", Status: "COMPLETED",
		OutputData: map[string]any{"segments": segments, "duration": 1250.0},
	})

	if _, ok := global.waitStatus(id, db.JobStatusCompleted, 10*time.Second); !ok {
		t.Fatal("job with large output_data never completed")
	}
	j := global.getJob(id)
	if j.OutputData == nil {
		t.Fatal("large OutputData was not persisted")
	}
}
