import PropTypes from 'prop-types';
import LoadingSpinner from '../common/LoadingSpinner';

const ProcessingQueue = ({
  processingJobs,
  isLoading,
  fetchJobs,
  t
}) => {
  return (
    <div className="card progress-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 className="card-title" style={{ marginBottom: 0 }}>
          <span>⏳</span>
          <span>{t('dashboard.currentQueue')}</span>
        </h2>
        <button
          onClick={fetchJobs}
          className="btn btn-secondary"
          style={{ padding: '8px 16px', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <span>↻</span>
          <span>{t('dashboard.refresh')}</span>
        </button>
      </div>

      {isLoading ? (
        <div style={{ padding: '20px', display: 'flex', justifyContent: 'center' }}><LoadingSpinner size="small" /></div>
      ) : processingJobs.length > 0 ? (
        processingJobs.map((job) => (
          <div key={job.id} className="job-item">
            <div className="job-header">
              <span className="job-name">{job.name}</span>
              <span className="job-status">
                {t('dashboard.processing')}
              </span>
            </div>
            <div className="progress-bar-container">
              <div
                className="progress-bar-fill"
                style={{ width: `${Math.min(100, Math.max(0, job.progress || 0))}%` }}
              />
            </div>
            <div className="job-time">
              <span>{t('dashboard.estTime')}</span> {job.estTime}
            </div>
          </div>
        ))
      ) : (
        <p style={{ color: 'var(--text-light)', textAlign: 'center', padding: '20px' }}>
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
    estTime: PropTypes.string,
  })).isRequired,
  isLoading: PropTypes.bool.isRequired,
  fetchJobs: PropTypes.func.isRequired,
  t: PropTypes.func.isRequired,
};

export default ProcessingQueue;
