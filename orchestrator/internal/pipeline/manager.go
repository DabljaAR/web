package pipeline

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/dabljaar/orchestrator/internal/db"
	"github.com/dabljaar/orchestrator/internal/mq"
	amqp "github.com/rabbitmq/amqp091-go"
	"gorm.io/gorm"
)

// workerPoolSize caps the number of messages processed concurrently.
// This prevents the orchestrator from opening thousands of DB connections
// if a burst of messages arrives at once.
const workerPoolSize = 10

// nextStageRoutes is the pipeline state-machine transition table.
// It maps a completed job type to the routing key for the next stage.
// Using a map instead of a switch statement makes it easy to extend the
// pipeline without touching handler logic.
var nextStageRoutes = map[db.JobType]string{
	db.JobTypeSTTTranscribe: "job.start.nmt",
	db.JobTypeNMTTranslate:  "job.start.tts",
	db.JobTypeTTSSynthesize: "job.start.merge",
	// JobTypeDubbingMerge is the final stage — no next route.
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

	// sem acts as a semaphore: only workerPoolSize goroutines may handle
	// messages simultaneously. Think of it as a ticket booth — workers
	// must hold a ticket to proceed and return it when done.
	sem chan struct{}

	// wg tracks all goroutines spawned by the Manager so Wait() can
	// block until every message in flight has been processed.
	wg sync.WaitGroup
}

// NewManager constructs a Manager with the given dependencies.
func NewManager(rmq *mq.RabbitMQ, database *gorm.DB, logger *slog.Logger) *Manager {
	return &Manager{
		rabbit: rmq,
		db:     database,
		logger: logger,
		sem:    make(chan struct{}, workerPoolSize),
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
		"worker_pool_size", workerPoolSize,
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
						m.logger.Error("Message handler failed — nacking",
							"queue", queueName,
							"error", err,
							"elapsed_ms", elapsed.Milliseconds(),
						)
						// Nack with requeue=true so RabbitMQ retries the message.
						// For permanent failures (e.g., bad JSON that will never
						// parse), set requeue=false so the message goes to the DLQ
						// instead of causing an infinite loop.
						d.Nack(false, true)
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
// event. It marks the pipeline as started and triggers the first stage (STT).
func (m *Manager) handleNewJob(ctx context.Context, body []byte) error {
	var payload newJobPayload
	if err := json.Unmarshal(body, &payload); err != nil {
		// Bad JSON will never get better; log and return nil so the message
		// is Ack'd and moved on (or change to a dedicated dead-letter Nack).
		m.logger.Error("handleNewJob: bad JSON — discarding message", "error", err)
		return nil // returning nil = Ack = move to DLQ via policy, not infinite retry
	}

	log := m.logger.With("job_id", payload.JobID, "handler", "handleNewJob")
	log.Info("Orchestrator received new job")

	var job db.Job
	if err := m.db.WithContext(ctx).Where("id = ?", payload.JobID).First(&job).Error; err != nil {
		return fmt.Errorf("job %s not found: %w", payload.JobID, err)
	}

	now := time.Now().UTC()
	job.Status = db.JobStatusProcessing
	job.StartedAt = &now

	if err := m.db.WithContext(ctx).Save(&job).Error; err != nil {
		return fmt.Errorf("save job %s: %w", payload.JobID, err)
	}

	log.Info("Pipeline starting — dispatching STT stage")
	if err := m.publishNextJob("job.start.stt", job.ID); err != nil {
		return fmt.Errorf("publish STT trigger for job %s: %w", job.ID, err)
	}

	return nil
}

// handleResult is invoked when an AI worker publishes a "job.results.*" event.
// It updates the job record in the database and advances the pipeline to the
// next stage (or marks the parent job complete/failed).
func (m *Manager) handleResult(ctx context.Context, body []byte) error {
	var payload WorkerResultPayload
	if err := json.Unmarshal(body, &payload); err != nil {
		m.logger.Error("handleResult: bad JSON — discarding message", "error", err)
		return nil // malformed — discard rather than infinite-retry
	}

	log := m.logger.With(
		"job_id", payload.JobID,
		"job_type", payload.JobType,
		"status", payload.Status,
	)
	log.Info("Worker result received")

	var job db.Job
	if err := m.db.WithContext(ctx).Where("id = ?", payload.JobID).First(&job).Error; err != nil {
		return fmt.Errorf("job %s not found: %w", payload.JobID, err)
	}

	// ── Persist result ─────────────────────────────────────────────────────
	now := time.Now().UTC()
	job.Status = db.JobStatus(payload.Status)
	if payload.OutputData != nil {
		job.OutputData = payload.OutputData
	}
	if payload.Error != "" {
		errCopy := payload.Error
		job.ErrorMessage = &errCopy
	}
	if job.Status == db.JobStatusCompleted || job.Status == db.JobStatusFailed {
		job.CompletedAt = &now
	}

	if err := m.db.WithContext(ctx).Save(&job).Error; err != nil {
		return fmt.Errorf("save job %s: %w", payload.JobID, err)
	}

	// ── State machine ──────────────────────────────────────────────────────
	switch job.Status {
	case db.JobStatusCompleted:
		if nextRoute, hasNext := nextStageRoutes[job.JobType]; hasNext {
			log.Info("Advancing pipeline to next stage", "next_route", nextRoute)
			if err := m.publishNextJob(nextRoute, job.ID); err != nil {
				return fmt.Errorf("publish next stage for job %s: %w", job.ID, err)
			}
		} else if job.JobType == db.JobTypeDubbingMerge {
			log.Info("All pipeline stages complete")
			m.markParentJob(ctx, job, db.JobStatusCompleted, "", 100.0, &now)
		}

	case db.JobStatusFailed:
		log.Error("Stage failed — propagating failure to parent", "error", payload.Error)
		m.markParentJob(ctx, job, db.JobStatusFailed, payload.Error, job.Progress, &now)
	}

	return nil
}

// markParentJob updates the FULL_DUBBING_PIPELINE parent record.
func (m *Manager) markParentJob(
	ctx context.Context,
	child db.Job,
	status db.JobStatus,
	errMsg string,
	progress float64,
	completedAt *time.Time,
) {
	if child.ParentJobID == nil {
		return
	}

	updates := map[string]any{
		"status":       status,
		"progress":     progress,
		"completed_at": completedAt,
	}
	if errMsg != "" {
		updates["error_message"] = errMsg
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