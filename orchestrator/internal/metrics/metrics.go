package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	JobsCompleted = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "dablja_jobs_completed_total",
		Help: "Pipeline jobs completed by orchestrator stage transition and status",
	}, []string{"stage", "status"})

	StageDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "dablja_stage_duration_seconds",
		Help:    "Orchestrator message handler duration in seconds",
		Buckets: []float64{0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60},
	}, []string{"handler"})

	DLQMessages = promauto.NewCounter(prometheus.CounterOpts{
		Name: "dablja_dlq_messages_total",
		Help: "Messages nacked without requeue and routed to the DLQ",
	})
)
