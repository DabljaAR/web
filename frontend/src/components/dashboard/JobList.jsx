import React from 'react';
import PropTypes from 'prop-types';
import JobItem from './JobItem';

const JobList = ({
  recentJobs,
  t,
  language,
  handlePreview,
  handleDownload,
  handleDelete,
  handleRetry,
  handleDetails,
  handlePreviewAudio,
  handleDownloadAudio,
  handlePreviewTranscript,
  handlePreviewTranslation,
  handleViewFullHistory
}) => {
  return (
    <div className="card">
      <h2 className="card-title">
        <span>📋</span>
        <span>{t('dashboard.recentJobs')}</span>
      </h2>

      <div className="recent-jobs">
        {recentJobs.map((job) => (
          <JobItem
            key={job.id}
            job={job}
            t={t}
            language={language}
            onPreview={handlePreview}
            onDownload={handleDownload}
            onDelete={handleDelete}
            onRetry={handleRetry}
            onDetails={handleDetails}
            onPreviewAudio={handlePreviewAudio}
            onDownloadAudio={handleDownloadAudio}
            onPreviewTranscript={handlePreviewTranscript}
            onPreviewTranslation={handlePreviewTranslation}
          />
        ))}
      </div>

      <button
        className="btn btn-primary"
        style={{ marginTop: '24px' }}
        onClick={handleViewFullHistory}
      >
        {t('dashboard.viewFullHistory')}
      </button>
    </div>
  );
};

JobList.propTypes = {
  recentJobs: PropTypes.arrayOf(PropTypes.object).isRequired,
  t: PropTypes.func.isRequired,
  language: PropTypes.string,
  handlePreview: PropTypes.func.isRequired,
  handleDownload: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  handleRetry: PropTypes.func.isRequired,
  handleDetails: PropTypes.func.isRequired,
  handlePreviewAudio: PropTypes.func.isRequired,
  handleDownloadAudio: PropTypes.func.isRequired,
  handlePreviewTranscript: PropTypes.func.isRequired,
  handlePreviewTranslation: PropTypes.func.isRequired,
  handleViewFullHistory: PropTypes.func.isRequired,
};

export default JobList;
