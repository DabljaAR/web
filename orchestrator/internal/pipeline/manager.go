package pipeline

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/dabljaar/orchestrator/internal/db"
	"github.com/dabljaar/orchestrator/internal/mq"
	"github.com/google/uuid"
	amqp "github.com/rabbitmq/amqp091-go"
	"gorm.io/gorm"
)

// errPermanent wraps an error that should NOT be requeued — retrying will never
// succeed (e.g. job ID not in DB, malformed payload that survived the JSON check).
// The startConsumer loop checks for this type to set requeue=false on Nack,
// routing the message to the Dead Letter Queue instead of looping forever.
type errPermanent struct{ err error }

func (e errPermanent) Error() string { return e.err.Error() }
func (e errPermanent) Unwrap() error { return e.err }

// permanent wraps err as a non-retryable failure.
func permanent(err error) error { return errPermanent{err} }

// ─── Pipeline stage definitions ──────────────────────────────────────────────

// stageOrder defines the pipeline sequence per output_type (D5, §7.2).
var stageOrder = map[string][]db.JobType{
	"captionsOnly":           {db.JobTypeSTTTranscribe},
	"captionsAndTranslation": {db.JobTypeSTTTranscribe, db.JobTypeNMTTranslate},
	"translationAndTTS":      {db.JobTypeSTTTranscribe, db.JobTypeNMTTranslate, db.JobTypeTTSSynthesize},
	// fullDubbing ends at TTS while the bridged Celery path performs merge inside
	// tts_combine_results. Re-add JobTypeDubbingMerge when a dedicated merge worker exists.
	"fullDubbing": {db.JobTypeSTTTranscribe, db.JobTypeNMTTranslate, db.JobTypeTTSSynthesize},
}

// startRoute maps JobType to the RabbitMQ routing key for dispatching that stage.
var startRoute = map[db.JobType]string{
	db.JobTypeSTTTranscribe: "job.start.stt",
	db.JobTypeNMTTranslate:  "job.start.nmt",
	db.JobTypeTTSSynthesize: "job.start.tts",
	db.JobTypeDubbingMerge:  "job.start.merge",
}

// stageProgress maps a completed stage to the parent's progress percentage.
var stageProgress = map[db.JobType]float64{
	db.JobTypeSTTTranscribe: 20.0,
	db.JobTypeNMTTranslate:  45.0,
	db.JobTypeTTSSynthesize: 75.0,
	db.JobTypeDubbingMerge:  100.0,
}

// firstStageFor returns the first pipeline stage for an output_type.
func firstStageFor(outputType string) (db.JobType, bool) {
	seq, ok := stageOrder[outputType]
	if !ok || len(seq) == 0 {
		return "", false
	}
	return seq[0], true
}

// nextStage returns the stage after current, or ("", false) if pipeline is done.
func nextStage(outputType string, current db.JobType) (db.JobType, bool) {
	seq := stageOrder[outputType]
	for i, s := range seq {
		if s == current && i+1 < len(seq) {
			return seq[i+1], true
		}
	}
	return "", false
}

// getOutputType extracts output_type from input_data, defaulting to fullDubbing.
func getOutputType(inputData map[string]any) string {
	if inputData == nil {
		return "fullDubbing"
	}
	if t, ok := inputData["output_type"].(string); ok && t != "" {
		return t
	}
	return "fullDubbing"
}

// ─── Payloads ─────────────────────────────────────────────────────────────────

// WorkerResultPayload is the message body posted by AI workers to
// "dablja.jobs.exchange" with routing key "job.results.*".
type WorkerResultPayload struct {
	JobID      string         `json:"job_id"`
	JobType    string         `json:"job_type"`
	Status     string         `json:"status"`
	OutputData map[string]any `json:"output_data"`
	Error      string         `json:"error,omitempty"`
}

// newJobPayload is the message body posted by the FastAPI server when a new
// FULL_DUBBING_PIPELINE job is created.
type newJobPayload struct {
	JobID string `json:"job_id"`
}

// ─── Manager ──────────────────────────────────────────────────────────────────

// Manager owns the RabbitMQ consumers and drives the dubbing pipeline
// state machine. It is safe to use from multiple goroutines.
type Manager struct {
	rabbit *mq.RabbitMQ
	db     *gorm.DB
	logger *slog.Logger

	// workerPoolSize caps the number of messages processed concurrently.
	// This prevents the orchestrator from opening thousands of DB connections
	// if a burst of messages arrives at once.
	workerPoolSize int

	// sem acts as a semaphore: only workerPoolSize goroutines may handle
	// messages simultaneously. Think of it as a ticket booth — workers
	// must hold a ticket to proceed and return it when done.
	sem chan struct{}

	// wg tracks all goroutines spawned by the Manager so Wait() can
	// block until every message in flight has been processed.
	wg sync.WaitGroup
}

// NewManager constructs a Manager with the given dependencies and worker pool size.
// workerPoolSize caps how many messages are handled concurrently.
func NewManager(rmq *mq.RabbitMQ, database *gorm.DB, logger *slog.Logger, workerPoolSize int) *Manager {
	if workerPoolSize < 1 {
		workerPoolSize = 1
	}
	return &Manager{
		rabbit:         rmq,
		db:             database,
		logger:         logger,
		workerPoolSize: workerPoolSize,
		sem:            make(chan struct{}, workerPoolSize),
	}
}

// Start declares all required exchanges/queues and begins consuming messages.
// It returns an error immediately if any infrastructure setup fails, so the
// caller can abort startup cleanly rather than running with a broken setup.
func (m *Manager) Start(ctx context.Context) error {
	ch := m.rabbit.Channel

	// ── Declare exchanges ──────────────────────────────────────────────────
	// durable=true means the exchange survives a RabbitMQ restart.
	if err := ch.ExchangeDeclare(
		"dablja.jobs.exchange", "topic",
		true, false, false, false, nil,
	); err != nil {
		return fmt.Errorf("declare main exchange: %w", err)
	}

	// Dead-Letter Exchange (DLX): messages that fail repeatedly are routed
	// here instead of being silently dropped.
	if err := ch.ExchangeDeclare(
		"dablja.jobs.dlx", "direct",
		true, false, false, false, nil,
	); err != nil {
		return fmt.Errorf("declare dead-letter exchange: %w", err)
	}

	// ── QoS / prefetch ────────────────────────────────────────────────────
	// Tell RabbitMQ to deliver at most 1 unacknowledged message per
	// consumer. Without this, RabbitMQ would dump all queued messages into
	// this process at once, overwhelming the worker pool.
	if err := ch.Qos(1, 0, false); err != nil {
		return fmt.Errorf("set QoS prefetch: %w", err)
	}

	// ── Queue arguments (applied to all work queues) ───────────────────────
	// x-dead-letter-exchange: where rejected/expired messages go.
	dlqArgs := amqp.Table{
		"x-dead-letter-exchange": "dablja.jobs.dlx",
	}

	// ── Start consumers ───────────────────────────────────────────────────
	if err := m.startConsumer(ctx, ch,
		"orchestrator.results", "job.results.*",
		dlqArgs, m.handleResult,
	); err != nil {
		return fmt.Errorf("start results consumer: %w", err)
	}

	if err := m.startConsumer(ctx, ch,
		"orchestrator.new_jobs", "job.created",
		dlqArgs, m.handleNewJob,
	); err != nil {
		return fmt.Errorf("start new_jobs consumer: %w", err)
	}

	// ── Dead Letter Queue ─────────────────────────────────────────────────
	// Poison messages land here for inspection/alerting rather than being
	// lost forever.
	dlq, err := ch.QueueDeclare("orchestrator.dlq", true, false, false, false, nil)
	if err != nil {
		return fmt.Errorf("declare DLQ: %w", err)
	}
	m.logger.Info("Dead Letter Queue ready", "queue", dlq.Name)

	m.logger.Info("Pipeline Manager started",
		"worker_pool_size", m.workerPoolSize,
	)
	return nil
}

// Wait blocks until all in-flight message handlers finish OR the context
// deadline is exceeded (whichever comes first). Call this during shutdown.
func (m *Manager) Wait(ctx context.Context) {
	done := make(chan struct{})
	go func() {
		m.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		m.logger.Info("All goroutines finished cleanly")
	case <-ctx.Done():
		m.logger.Warn("Graceful shutdown timeout: some goroutines may still be running")
	}
}

// ─── Internal helpers ──────────────────────────────────────────────────────────

// startConsumer declares a queue, binds it, and launches a consumer goroutine.
// The handler function is called for each message. On handler success the
// message is Ack'd; on failure it is Nack'd (requeued for retry).
func (m *Manager) startConsumer(
	ctx context.Context,
	ch *amqp.Channel,
	queueName, bindingKey string,
	args amqp.Table,
	handler func(context.Context, []byte) error,
) error {
	q, err := ch.QueueDeclare(queueName, true, false, false, false, args)
	if err != nil {
		return fmt.Errorf("declare queue %q: %w", queueName, err)
	}

	if err := ch.QueueBind(q.Name, bindingKey, "dablja.jobs.exchange", false, nil); err != nil {
		return fmt.Errorf("bind queue %q to %q: %w", queueName, bindingKey, err)
	}

	msgs, err := ch.Consume(q.Name, "", false /*auto-ack off*/, false, false, false, nil)
	if err != nil {
		return fmt.Errorf("consume from %q: %w", queueName, err)
	}

	m.wg.Add(1)
	go func() {
		defer m.wg.Done()
		m.logger.Info("Consumer ready", "queue", queueName, "binding", bindingKey)

		for {
			select {
			case <-ctx.Done():
				// Root context cancelled (shutdown): stop accepting messages.
				m.logger.Info("Consumer stopping", "queue", queueName)
				return

			case delivery, ok := <-msgs:
				if !ok {
					// Channel was closed by RabbitMQ (e.g., connection drop).
					m.logger.Warn("Message channel closed", "queue", queueName)
					return
				}

				// Block here if the worker pool is full. This is backpressure:
				// messages stay in RabbitMQ (safe) rather than piling up in RAM.
				m.sem <- struct{}{}

				m.wg.Add(1)
				go func(d amqp.Delivery) {
					defer m.wg.Done()
					defer func() { <-m.sem }() // release pool slot

					start := time.Now()
					err := handler(ctx, d.Body)
					elapsed := time.Since(start)

					if err != nil {
						requeue := !errors.As(err, &errPermanent{})
						m.logger.Error("Message handler failed — nacking",
							"queue", queueName,
							"error", err,
							"requeue", requeue,
							"elapsed_ms", elapsed.Milliseconds(),
						)
						// requeue=false sends to the Dead Letter Queue; the message
						// will not spin in a retry loop. Use errPermanent for errors
						// where retrying can never succeed (job missing, bad ID, etc.).
						d.Nack(false, requeue)
						return
					}

					m.logger.Debug("Message handled successfully",
						"queue", queueName,
						"elapsed_ms", elapsed.Milliseconds(),
					)
					d.Ack(false)
				}(delivery)
			}
		}
	}()

	return nil
}

// ─── Message Handlers ─────────────────────────────────────────────────────────

// handleNewJob is invoked when the FastAPI backend publishes a "job.created"
// event with the PARENT job_id (§15 contract). It resolves output_type, marks
// the parent PROCESSING, creates the first child job (STT), and dispatches.
func (m *Manager) handleNewJob(ctx context.Context, body []byte) error {
	var payload newJobPayload
	if err := json.Unmarshal(body, &payload); err != nil {
		m.logger.Error("handleNewJob: bad JSON — discarding message", "error", err)
		return nil
	}

	parentID := payload.JobID
	log := m.logger.With("parent_job_id", parentID, "handler", "handleNewJob")
	log.Info("Orchestrator received new job")

	var parent db.Job
	if err := m.db.WithContext(ctx).Where("id = ?", parentID).First(&parent).Error; err != nil {
		return permanent(fmt.Errorf("parent job %s not found: %w", parentID, err))
	}

	now := time.Now().UTC()

	// Mark parent PROCESSING
	m.db.WithContext(ctx).Model(&parent).Updates(map[string]any{
		"status":     db.JobStatusProcessing,
		"started_at": &now,
		"updated_at": now,
	})

	// Resolve first stage from output_type
	outputType := getOutputType(parent.InputData)
	firstStage, ok := firstStageFor(outputType)
	if !ok {
		// uploadOnly or unknown — mark parent COMPLETED immediately
		log.Info("No pipeline stages for output_type — marking parent COMPLETED", "output_type", outputType)
		m.db.WithContext(ctx).Model(&parent).Updates(map[string]any{
			"status":       db.JobStatusCompleted,
			"progress":     100.0,
			"completed_at": &now,
			"updated_at":   now,
		})
		return nil
	}

	// Duplicate prevention: if a child already exists for this parent+stage,
	// don't create another one. Instead, re-publish if the existing child is
	// still in a non-terminal state (the original dispatch may have been lost).
	var existing db.Job
	dupErr := m.db.WithContext(ctx).
		Where("parent_job_id = ? AND job_type = ?", parentID, firstStage).
		First(&existing).Error

	if dupErr == nil {
		// Child already exists — decide based on its status
		switch existing.Status {
		case db.JobStatusQueued, db.JobStatusProcessing, db.JobStatusRetrying:
			log.Info("Child already exists — re-publishing dispatch", "child_job_id", existing.ID, "stage", firstStage, "status", existing.Status)
			route, ok := startRoute[firstStage]
			if !ok {
				return permanent(fmt.Errorf("no start route for stage %s", firstStage))
			}
			if err := m.publishNextJob(route, existing.ID); err != nil {
				return fmt.Errorf("re-publish %s for child %s: %w", route, existing.ID, err)
			}
			return nil

		case db.JobStatusCompleted:
			log.Info("Child already completed — skipping", "child_job_id", existing.ID, "stage", firstStage)
			return nil

		case db.JobStatusFailed:
			log.Info("Child previously failed — creating new child for retry", "old_child_id", existing.ID, "stage", firstStage)

		case db.JobStatusCancelled:
			log.Info("Child was cancelled — skipping", "child_job_id", existing.ID)
			return nil
		}
	}

	// Create first child job (STT_TRANSCRIBE) linked to parent
	childID := uuid.NewString()
	child := db.Job{
		ID:           childID,
		VideoID:      parent.VideoID,
		UserID:       parent.UserID,
		JobType:      firstStage,
		Status:       db.JobStatusQueued,
		ParentJobID:  &parentID,
		InputData:    parent.InputData,
		RetryCount:   0,
		MaxRetries:   3,
		CreatedAt:    now,
		UpdatedAt:    now,
	}
	if err := m.db.WithContext(ctx).Create(&child).Error; err != nil {
		return fmt.Errorf("create STT child for parent %s: %w", parentID, err)
	}

	route, ok := startRoute[firstStage]
	if !ok {
		return permanent(fmt.Errorf("no start route for stage %s", firstStage))
	}

	log.Info("Dispatching first stage", "child_job_id", childID, "stage", firstStage, "route", route)
	if err := m.publishNextJob(route, childID); err != nil {
		return fmt.Errorf("publish %s for child %s: %w", route, childID, err)
	}

	return nil
}

// handleResult is invoked when an AI worker publishes a "job.results.*" event.
// It updates the child job, then either creates the next child and dispatches
// (COMPLETED), propagates failure to the parent (FAILED), or marks the pipeline
// complete when no more stages remain. Never mutates job_type on existing rows.
func (m *Manager) handleResult(ctx context.Context, body []byte) error {
	var payload WorkerResultPayload
	if err := json.Unmarshal(body, &payload); err != nil {
		m.logger.Error("handleResult: bad JSON — discarding message", "error", err)
		return nil
	}

	childID := payload.JobID
	log := m.logger.With(
		"child_job_id", childID,
		"job_type", payload.JobType,
		"status", payload.Status,
	)
	log.Info("Worker result received")

	var child db.Job
	if err := m.db.WithContext(ctx).Where("id = ?", childID).First(&child).Error; err != nil {
		return permanent(fmt.Errorf("child job %s not found: %w", childID, err))
	}

	now := time.Now().UTC()
	resultStatus := db.JobStatus(payload.Status)

	// Targeted update: status + output only — never job_type
	updates := map[string]any{
		"status":     resultStatus,
		"updated_at": now,
	}
	if payload.OutputData != nil {
		updates["output_data"] = payload.OutputData
	}
	if payload.Error != "" {
		errCopy := payload.Error
		updates["error_message"] = &errCopy
	}
	if resultStatus == db.JobStatusCompleted || resultStatus == db.JobStatusFailed {
		updates["completed_at"] = &now
		updates["progress"] = 100.0
	}
	m.db.WithContext(ctx).Model(&child).Updates(updates)

	// ── State machine ──────────────────────────────────────────────────────
	switch resultStatus {
	case db.JobStatusFailed:
		log.Error("Stage failed — propagating to parent", "error", payload.Error)
		m.updateParent(ctx, child, db.JobStatusFailed, payload.Error, &now)

	case db.JobStatusCompleted:
		// Load parent for cancel check and output_type
		if child.ParentJobID == nil {
			log.Warn("Child has no parent_job_id — cannot advance pipeline")
			return nil
		}

		var parent db.Job
		if err := m.db.WithContext(ctx).Where("id = ?", *child.ParentJobID).First(&parent).Error; err != nil {
			// Parent gone — still update child progress, but can't advance
			m.logger.Warn("Parent job not found for child", "child_id", childID, "parent_id", *child.ParentJobID, "error", err)
			return nil
		}

		// D8: cancel check — if parent was cancelled, stop advancing
		if parent.Status == db.JobStatusCancelled {
			log.Info("Parent is CANCELLED — stopping pipeline")
			m.db.WithContext(ctx).Model(&parent).Updates(map[string]any{
				"status": db.JobStatusCancelled, "updated_at": now,
			})
			return nil
		}

		// Update parent progress for completed stage
		if prog, hasProg := stageProgress[child.JobType]; hasProg {
			m.db.WithContext(ctx).Model(&parent).Updates(map[string]any{
				"progress": prog, "updated_at": now,
			})
		}

		// Resolve next stage from output_type
		outputType := getOutputType(parent.InputData)
		next, hasNext := nextStage(outputType, child.JobType)

		if !hasNext {
			log.Info("All pipeline stages complete")
			m.db.WithContext(ctx).Model(&parent).Updates(map[string]any{
				"status":       db.JobStatusCompleted,
				"progress":     100.0,
				"completed_at": &now,
				"updated_at":   now,
			})
			return nil
		}

		// Duplicate prevention: if a next-stage child already exists for this
		// parent, don't create another one. Re-publish if still non-terminal.
		var existingNext db.Job
		dupErr := m.db.WithContext(ctx).
			Where("parent_job_id = ? AND job_type = ?", *child.ParentJobID, next).
			First(&existingNext).Error

		if dupErr == nil {
			switch existingNext.Status {
			case db.JobStatusQueued:
				log.Info("Next child already queued — re-publishing dispatch", "next_child_id", existingNext.ID, "stage", next)
				route, ok := startRoute[next]
				if !ok {
					return permanent(fmt.Errorf("no start route for stage %s", next))
				}
				if err := m.publishNextJob(route, existingNext.ID); err != nil {
					return fmt.Errorf("re-publish %s for next child %s: %w", route, existingNext.ID, err)
				}
				return nil

			case db.JobStatusProcessing, db.JobStatusRetrying:
				log.Info("Next child already processing — skipping", "next_child_id", existingNext.ID, "stage", next, "status", existingNext.Status)
				return nil

			case db.JobStatusCompleted:
				log.Info("Next child already completed — skipping", "next_child_id", existingNext.ID, "stage", next)
				return nil

			case db.JobStatusFailed:
				log.Info("Next child previously failed — creating new child for retry", "old_child_id", existingNext.ID, "stage", next)

			case db.JobStatusCancelled:
				log.Info("Next child was cancelled — skipping", "next_child_id", existingNext.ID)
				return nil
			}
		}

		// Create next child job
		nextChildID := uuid.NewString()
		nextChild := db.Job{
			ID:           nextChildID,
			VideoID:      child.VideoID,
			UserID:       child.UserID,
			JobType:      next,
			Status:       db.JobStatusQueued,
			ParentJobID:  child.ParentJobID,
			InputData:    child.InputData,
			RetryCount:   0,
			MaxRetries:   3,
			CreatedAt:    now,
			UpdatedAt:    now,
		}
		if err := m.db.WithContext(ctx).Create(&nextChild).Error; err != nil {
			return fmt.Errorf("create next child for parent %s: %w", *child.ParentJobID, err)
		}

		route, ok := startRoute[next]
		if !ok {
			return permanent(fmt.Errorf("no start route for stage %s", next))
		}

		log.Info("Advancing pipeline to next stage",
			"next_child_id", nextChildID,
			"next_stage", next,
			"route", route,
		)
		if err := m.publishNextJob(route, nextChildID); err != nil {
			return fmt.Errorf("publish %s for next child %s: %w", route, nextChildID, err)
		}

	default:
		// RETRYING or CANCELLED — no state-machine action
		log.Debug("No state-machine action for status", "status", resultStatus)
	}

	return nil
}

// updateParent pushes a status/error change up to the parent FULL_DUBBING_PIPELINE row.
func (m *Manager) updateParent(
	ctx context.Context,
	child db.Job,
	status db.JobStatus,
	errMsg string,
	completedAt *time.Time,
) {
	if child.ParentJobID == nil {
		return
	}

	updates := map[string]any{
		"status":     status,
		"updated_at": time.Now().UTC(),
	}
	if errMsg != "" {
		updates["error_message"] = errMsg
	}
	if completedAt != nil {
		updates["completed_at"] = completedAt
	}

	result := m.db.WithContext(ctx).Model(&db.Job{}).
		Where("id = ?", *child.ParentJobID).
		Updates(updates)

	if result.Error != nil {
		m.logger.Error("Failed to update parent job",
			"parent_job_id", *child.ParentJobID,
			"error", result.Error,
		)
	} else {
		m.logger.Info("Parent job updated",
			"parent_job_id", *child.ParentJobID,
			"status", status,
		)
	}
}

// publishNextJob sends a trigger message to the exchange with the given
// routing key. Messages are marked persistent so they survive a broker restart.
func (m *Manager) publishNextJob(routingKey, jobID string) error {
	body, err := json.Marshal(map[string]string{"job_id": jobID})
	if err != nil {
		return fmt.Errorf("marshal publish payload: %w", err)
	}

	return m.rabbit.Channel.Publish(
		"dablja.jobs.exchange",
		routingKey,
		false, // mandatory
		false, // immediate
		amqp.Publishing{
			ContentType:  "application/json",
			DeliveryMode: amqp.Persistent, // survive broker restart
			Body:         body,
		},
	)
}