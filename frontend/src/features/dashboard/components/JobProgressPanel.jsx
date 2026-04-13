import React, { useState, useEffect } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { jobService } from '../../../services/jobService';

import LoadingSpinner from '../../../components/common/LoadingSpinner';

/**
 * JobProgressPanel — shows real-time job progress for a given video.
 * Intended to be embedded inside the Dashboard or a modal.
 *
 * Props:
 *   videoId  — the video UUID to display jobs for
 *   onClose  — optional callback to dismiss the panel
 */
const JobProgressPanel = ({ videoId, onClose }) => {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!videoId) return;

    let cancelled = false;

    const fetchJobs = async () => {
      try {
        const data = await jobService.getJobsForVideo(videoId);
        if (!cancelled) setJobs(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error('Failed to fetch jobs for video', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchJobs();
    const interval = setInterval(fetchJobs, 3000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [videoId]);

  const statusColor = (status) => {
    switch (status) {
      case 'COMPLETED': return '#22c55e';
      case 'FAILED': return '#ef4444';
      case 'PROCESSING': return '#3b82f6';
      case 'QUEUED': return '#a3a3a3';
      case 'RETRYING': return '#f59e0b';
      case 'CANCELLED': return '#6b7280';
      default: return '#a3a3a3';
    }
  };

  if (loading) {
    return <div style={{ padding: '1rem', textAlign: 'center' }}><LoadingSpinner size="small" /></div>;
  }

  if (jobs.length === 0) {
    return <div style={{ padding: '1rem', textAlign: 'center', color: '#999' }}>No jobs found for this video.</div>;
  }

  return (
    <div style={{ padding: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={{ margin: 0, fontSize: '1rem' }}>Job Progress</h3>
        {onClose && (
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.2rem' }}>✕</button>
        )}
      </div>

      {jobs.map((job) => (
        <div
          key={job.id}
          style={{
            border: '1px solid #e5e7eb',
            borderRadius: '8px',
            padding: '0.75rem',
            marginBottom: '0.5rem',
            background: '#fafafa',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
            <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{job.job_type}</span>
            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 600,
                color: statusColor(job.status),
              }}
            >
              {job.status}
            </span>
          </div>

          {/* Progress bar */}
          <div style={{ background: '#e5e7eb', borderRadius: '4px', height: '6px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${job.progress || 0}%`,
                height: '100%',
                background: statusColor(job.status),
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.25rem', fontSize: '0.75rem', color: '#6b7280' }}>
            <span>{Math.round(job.progress || 0)}%</span>
            {job.error_message && <span style={{ color: '#ef4444' }}>{job.error_message}</span>}
          </div>
        </div>
      ))}
    </div>
  );
};

export default JobProgressPanel;
