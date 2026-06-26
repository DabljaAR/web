import PropTypes from 'prop-types';
import LoadingSpinner from '../common/LoadingSpinner';

const STAGE_LABELS = ['STT', 'NMT', 'TTS', 'Merge'];
const STAGE_COLORS = {
  completed: 'var(--accent-blue)',
  processing: 'var(--accent-cyan)',
  failed: '#ef4444',
  queued: '#e5e7eb',
  cancelled: '#9ca3af',
};

const ProcessingQueue = ({
  processingJobs,
  isLoading,
  fetchJobs,
  t
}) => {
  const renderStageBar = (job) => {
    const stages = job.stages || [];

    // If no stage data, fall back to simple bar
    if (stages.length === 0) {
      return (
        <div className="progress-bar-container">
          <div
            className="progress-bar-fill"
            style={{ width: `${Math.min(100, Math.max(0, job.progress || 0))}%` }}
          />
        </div>
      );
    }

    const totalStages = stages.length;

    return (
      <div className="stage-progress-wrapper">
        <div className="stage-progress-bar">
          {stages.map((stage, idx) => {
            const status = stage.status;
            const isProcessing = status === 'processing';
            const isCompleted = status === 'completed';
            const isFailed = status === 'failed';

            let bgColor = STAGE_COLORS.queued;
            if (isCompleted) bgColor = STAGE_COLORS.completed;
            else if (isFailed) bgColor = STAGE_COLORS.failed;
            else if (isProcessing) bgColor = STAGE_COLORS.processing;
            else if (status === 'cancelled') bgColor = STAGE_COLORS.cancelled;

            return (
              <div
                key={stage.type || idx}
                className={`stage-segment ${isProcessing ? 'stage-active' : ''} ${isCompleted ? 'stage-done' : ''} ${isFailed ? 'stage-failed' : ''}`}
                style={{
                  width: `${100 / totalStages}%`,
                  backgroundColor: bgColor,
                }}
                title={`${stage.label}: ${status}${stage.segment_count ? ` (${stage.segment_count} segments)` : ''}`}
              />
            );
          })}
        </div>
        <div className="stage-labels">
          {stages.map((stage, idx) => {
            const isProcessing = stage.status === 'processing';
            const isCompleted = stage.status === 'completed';
            const isFailed = stage.status === 'failed';

            let cls = 'stage-label';
            if (isProcessing) cls += ' stage-label-active';
            else if (isCompleted) cls += ' stage-label-done';
            else if (isFailed) cls += ' stage-label-failed';

            return (
              <div
                key={stage.type || idx}
                className={cls}
                style={{ width: `${100 / stages.length}%` }}
              >
                <span className="stage-dot" />
                <span className="stage-name">{stage.label}</span>
                {stage.segment_count != null && (
                  <span className="stage-segments">{stage.segment_count}</span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="card progress-container">
      <div className="progress-header">
        <h2 className="card-title" style={{ marginBottom: 0 }}>
          <span>⏳</span>
          <span>{t('dashboard.currentQueue')}</span>
        </h2>
        <button
          onClick={fetchJobs}
          className="btn btn-secondary btn-refresh"
        >
          <span>↻</span>
          <span>{t('dashboard.refresh')}</span>
        </button>
      </div>

      {isLoading ? (
        <div style={{ padding: '20px', display: 'flex', justifyContent: 'center' }}>
          <LoadingSpinner size="small" />
        </div>
      ) : processingJobs.length > 0 ? (
        processingJobs.map((job) => (
          <div key={job.id} className="job-item">
            <div className="job-header">
              <div className="job-title-row">
                <span className="job-name">{job.name}</span>
                {job.totalSegments > 0 && (
                  <span className="job-segment-badge">
                    {job.totalSegments} segments
                  </span>
                )}
              </div>
              <span className="job-status">
                {job.progress}%
              </span>
            </div>
            {renderStageBar(job)}
            <div className="job-time">
              <span className="est-label">{t('dashboard.estTime')}</span>
              <span className="est-value">{job.estTime}</span>
            </div>
          </div>
        ))
      ) : (
        <p className="no-jobs-msg">
          {t('dashboard.noProcessingJobs')}
        </p>
      )}
    </div>
  );
};

ProcessingQueue.propTypes = {
  processingJobs: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
    name: PropTypes.string.isRequired,
    status: PropTypes.string,
    progress: PropTypes.number,
    estTime: PropTypes.string,
    type: PropTypes.string,
    totalSegments: PropTypes.number,
    stages: PropTypes.arrayOf(PropTypes.shape({
      type: PropTypes.string,
      label: PropTypes.string,
      order: PropTypes.number,
      status: PropTypes.string,
      progress: PropTypes.number,
      segment_count: PropTypes.number,
      error: PropTypes.string,
    })),
  })).isRequired,
  isLoading: PropTypes.bool.isRequired,
  fetchJobs: PropTypes.func.isRequired,
  t: PropTypes.func.isRequired,
};

export default ProcessingQueue;
