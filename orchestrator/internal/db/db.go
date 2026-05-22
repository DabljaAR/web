package db

import (
	"database/sql/driver"
	"fmt"
	"time"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

// JobType corresponds to the app/jobs/models.py Enum
type JobType string

const (
	JobTypeVideoProcess       JobType = "VIDEO_PROCESS"
	JobTypeVideoHLS           JobType = "VIDEO_HLS"
	JobTypeSTTTranscribe      JobType = "STT_TRANSCRIBE"
	JobTypeNMTTranslate       JobType = "NMT_TRANSLATE"
	JobTypeTTSSynthesize      JobType = "TTS_SYNTHESIZE"
	JobTypeDubbingMerge       JobType = "DUBBING_MERGE"
	JobTypeFullDubbingPipeline JobType = "FULL_DUBBING_PIPELINE"
)

func (e *JobType) Scan(value interface{}) error {
	*e = JobType(value.(string))
	return nil
}
func (e JobType) Value() (driver.Value, error) {
	return string(e), nil
}

// JobStatus corresponds to the app/jobs/models.py Enum
type JobStatus string

const (
	JobStatusQueued     JobStatus = "QUEUED"
	JobStatusProcessing JobStatus = "PROCESSING"
	JobStatusCompleted  JobStatus = "COMPLETED"
	JobStatusFailed     JobStatus = "FAILED"
	JobStatusRetrying   JobStatus = "RETRYING"
	JobStatusCancelled  JobStatus = "CANCELLED"
)

func (e *JobStatus) Scan(value interface{}) error {
	*e = JobStatus(value.(string))
	return nil
}
func (e JobStatus) Value() (driver.Value, error) {
	return string(e), nil
}

// Job struct mimics the SQLAlchemy model for jobs
type Job struct {
	ID            string         `gorm:"primaryKey;type:varchar(36)"`
	VideoID       *string        `gorm:"type:varchar(36);index"`
	UserID        int            `gorm:"index;not null"`
	JobType       JobType        `gorm:"type:jobtype;not null"`
	Status        JobStatus      `gorm:"type:jobstatus;not null;default:'QUEUED'"`
	Progress      float64        `gorm:"default:0.0;not null"`
	CeleryTaskID  *string        `gorm:"type:varchar(255)"`
	ParentJobID   *string        `gorm:"type:varchar(36)"`
	InputData     map[string]any `gorm:"type:jsonb;serializer:json"`
	OutputData    map[string]any `gorm:"type:jsonb;serializer:json"`
	ErrorMessage  *string        `gorm:"type:text"`
	RetryCount    int            `gorm:"default:0;not null"`
	MaxRetries    int            `gorm:"default:3;not null"`
	CreatedAt     time.Time      `gorm:"not null"`
	UpdatedAt     time.Time      `gorm:"not null"`
	StartedAt     *time.Time
	CompletedAt   *time.Time
}

func ConnectDB(dsn string) (*gorm.DB, error) {
	db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{})
	if err != nil {
		return nil, fmt.Errorf("failed to connect to database: %w", err)
	}

	return db, nil
}
