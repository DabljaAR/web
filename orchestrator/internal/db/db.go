package db

import (
	"database/sql/driver"
	"fmt"
	"time"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

// ─── Enums ────────────────────────────────────────────────────────────────────
// These mirror the Python SQLAlchemy enums exactly.
// Scan/Value implement the sql.Scanner and driver.Valuer interfaces so GORM
// can read and write them to/from PostgreSQL enum columns.

// JobType identifies what kind of work a job represents.
type JobType string

const (
	JobTypeVideoProcess        JobType = "VIDEO_PROCESS"
	JobTypeVideoHLS            JobType = "VIDEO_HLS"
	JobTypeSTTTranscribe       JobType = "STT_TRANSCRIBE"
	JobTypeNMTTranslate        JobType = "NMT_TRANSLATE"
	JobTypeTTSSynthesize       JobType = "TTS_SYNTHESIZE"
	JobTypeDubbingMerge        JobType = "DUBBING_MERGE"
	JobTypeFullDubbingPipeline JobType = "FULL_DUBBING_PIPELINE"
)

// Scan reads a JobType from the database (satisfies sql.Scanner).
func (e *JobType) Scan(value interface{}) error {
	s, ok := value.(string)
	if !ok {
		return fmt.Errorf("JobType.Scan: expected string, got %T", value)
	}
	*e = JobType(s)
	return nil
}

// Value writes a JobType to the database (satisfies driver.Valuer).
func (e JobType) Value() (driver.Value, error) {
	return string(e), nil
}

// JobStatus is the lifecycle state of a job.
type JobStatus string

const (
	JobStatusQueued     JobStatus = "QUEUED"
	JobStatusProcessing JobStatus = "PROCESSING"
	JobStatusCompleted  JobStatus = "COMPLETED"
	JobStatusFailed     JobStatus = "FAILED"
	JobStatusRetrying   JobStatus = "RETRYING"
	JobStatusCancelled  JobStatus = "CANCELLED"
)

// Scan reads a JobStatus from the database.
func (e *JobStatus) Scan(value interface{}) error {
	s, ok := value.(string)
	if !ok {
		return fmt.Errorf("JobStatus.Scan: expected string, got %T", value)
	}
	*e = JobStatus(s)
	return nil
}

// Value writes a JobStatus to the database.
func (e JobStatus) Value() (driver.Value, error) {
	return string(e), nil
}

// ─── Model ────────────────────────────────────────────────────────────────────

// Job mirrors the `jobs` table managed by Python's Alembic migrations.
// The Go service only reads and updates rows — it never creates or migrates.
type Job struct {
	ID           string         `gorm:"primaryKey;type:varchar(36)"`
	VideoID      *string        `gorm:"type:varchar(36);index"`
	UserID       int            `gorm:"index;not null"`
	JobType      JobType        `gorm:"type:jobtype;not null"`
	Status       JobStatus      `gorm:"type:jobstatus;not null;default:'QUEUED'"`
	Progress     float64        `gorm:"default:0.0;not null"`
	CeleryTaskID *string        `gorm:"type:varchar(255)"`
	ParentJobID  *string        `gorm:"type:varchar(36);index"`
	InputData    map[string]any `gorm:"type:jsonb;serializer:json"`
	OutputData   map[string]any `gorm:"type:jsonb;serializer:json"`
	ErrorMessage *string        `gorm:"type:text"`
	RetryCount   int            `gorm:"default:0;not null"`
	MaxRetries   int            `gorm:"default:3;not null"`
	CreatedAt    time.Time      `gorm:"not null"`
	UpdatedAt    time.Time      `gorm:"not null"`
	StartedAt    *time.Time
	CompletedAt  *time.Time
}

// TableName tells GORM the exact table name to use.
// Without this, GORM defaults to "jobs" anyway (plural of "Job"),
// but being explicit prevents surprises if the struct is ever renamed.
func (Job) TableName() string {
	return "jobs"
}

// ─── Connection ───────────────────────────────────────────────────────────────

// ConnectDB opens a connection pool to PostgreSQL and verifies it with a ping.
func ConnectDB(dsn string) (*gorm.DB, error) {
	database, err := gorm.Open(postgres.Open(dsn), &gorm.Config{
		// NowFunc ensures timestamps use UTC consistently.
		NowFunc: func() time.Time { return time.Now().UTC() },
	})
	if err != nil {
		return nil, fmt.Errorf("open database: %w", err)
	}

	// Verify the connection is actually alive.
	sqlDB, err := database.DB()
	if err != nil {
		return nil, fmt.Errorf("get underlying sql.DB: %w", err)
	}
	if err := sqlDB.Ping(); err != nil {
		return nil, fmt.Errorf("ping database: %w", err)
	}

	return database, nil
}
