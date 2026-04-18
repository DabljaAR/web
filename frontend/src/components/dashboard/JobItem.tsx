import React, { useState, useRef, useEffect, memo } from 'react';
import type { RecentJob } from '../../types/job';
import { formatDate } from '../../utils/formatters';

interface JobItemProps {
  job: RecentJob;
  t: (key: string) => string;
  language?: string;
  onPreview: (id: string) => void;
  onDownload: (id: string) => void;
  onDelete: (id: string) => void;
  onRetry: (id: string) => void;
  onDetails: (id: string) => void;
  onPreviewAudio: (id: string) => void;
  onDownloadAudio: (id: string) => void;
  onPreviewTranscript: (id: string) => void;
  onPreviewTranslation: (id: string) => void;
}

// Sub-component for Job Item to handle menu state locally
const JobItem: React.FC<JobItemProps> = memo(({ 
  job, 
  t, 
  language,
  onPreview, 
  onDownload, 
  onDelete, 
  onRetry, 
  onDetails, 
  onPreviewAudio, 
  onDownloadAudio, 
  onPreviewTranscript, 
  onPreviewTranslation 
}) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const toggleMenu = (e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpen(!menuOpen);
  };

  const displayName = (typeof (job as any)?.name === 'string' && (job as any).name.trim())
    ? (job as any).name
    : (t('history.untitled') || 'Untitled');

  const resolvedLocale = language === 'ar'
    ? 'ar'
    : (language === 'en' ? 'en-US' : (language || (typeof navigator !== 'undefined' ? navigator.language : 'en-US')));

  const formattedDate = formatDate(job.date ?? '', resolvedLocale);
  const showDate = Boolean(job.date) && formattedDate !== '—';

  const nameForMatch = typeof displayName === 'string' ? displayName : '';
  const isVideo = job.mediaType === 'VIDEO' || (!job.mediaType && /\.(mp4|mov|avi|mkv)$/i.test(nameForMatch));
  const isAudio = job.mediaType === 'AUDIO' || (!job.mediaType && /\.(mp3|wav|m4a)$/i.test(nameForMatch));

  // Determine Icon/Thumbnail
  let thumbnailContent: React.ReactNode;
  if (job.thumbnailUrl) {
    thumbnailContent = (
      <img 
        src={job.thumbnailUrl} 
        alt={displayName} 
        className="job-thumbnail-img" 
        onError={(e) => { 
          (e.target as HTMLImageElement).style.display = 'none'; 
          if ((e.target as HTMLImageElement).nextSibling) {
            ((e.target as HTMLImageElement).nextSibling as HTMLElement).style.display = 'flex';
          }
        }} 
      />
    );
  }

  // Fallback icon
  const fallbackIcon = (
    <div className="job-type-icon">
      {isVideo ? '🎬' : isAudio ? '🎵' : '📄'}
    </div>
  );

  return (
    <div className="job-item-container">
      {/* Thumbnail / Icon */}
      <div className="job-thumbnail-wrapper" onClick={() => onPreview(job.id)}>
        {thumbnailContent}
        {!job.thumbnailUrl && fallbackIcon}

        {/* Play Overlay for previewable content */}
        {(isVideo || isAudio) && job.status === 'completed' && (
          <div className="thumbnail-overlay">
            <span className="play-icon-overlay">▶</span>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="job-info-content">
        <div className="job-title" title={displayName}>{displayName}</div>
        <div className="job-meta">
          <span className={`status-badge ${job.status}`}>
            {t(`dashboard.${job.status}`) || job.status}
          </span>
          {showDate && (
            <>
              <span className="job-date-sep" aria-hidden="true">•</span>
              <span className="job-date">{formattedDate}</span>
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="job-actions-container" ref={menuRef}>
        <button 
          className="btn-icon-menu" 
          onClick={toggleMenu} 
          title="Options"
          aria-label={t('common.options') || 'Options'}
        >
          {/* Kebab Icon (Vertical Dots) */}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="1"></circle>
            <circle cx="12" cy="5" r="1"></circle>
            <circle cx="12" cy="19" r="1"></circle>
          </svg>
        </button>

        {menuOpen && (
          <div className="action-menu-dropdown">
            {job.status === 'completed' ? (
              <>
                <button className="action-menu-item" onClick={() => { onPreview(job.id); setMenuOpen(false); }}>
                  <span>👁️</span> {t('dashboard.preview')}
                </button>
                <button className="action-menu-item" onClick={() => { onDownload(job.id); setMenuOpen(false); }}>
                  <span>⬇️</span> {t('dashboard.download')}
                </button>
                {/* Audio Option */}
                {job.audioUrl && (
                  <>
                    <button className="action-menu-item" onClick={() => { onPreviewAudio(job.id); setMenuOpen(false); }}>
                      <span>🎵</span> {t('dashboard.previewAudio') || 'Preview Audio'}
                    </button>
                    <button className="action-menu-item" onClick={() => { onDownloadAudio(job.id); setMenuOpen(false); }}>
                      <span>⬇️</span> {t('dashboard.downloadAudio') || 'Download Audio'}
                    </button>
                  </>
                )}
                {/* Transcript Option */}
                {job.transcriptUrl && (
                  <button className="action-menu-item" onClick={() => { onPreviewTranscript(job.id); setMenuOpen(false); }}>
                    <span>📄</span> {t('dashboard.previewTranscript') || 'Preview Transcript'}
                  </button>
                )}
                {/* Translation Option */}
                {job.translationUrl && (
                  <button className="action-menu-item" onClick={() => { onPreviewTranslation(job.id); setMenuOpen(false); }}>
                    <span>🌍</span> {t('dashboard.previewTranslation') || 'Preview Translation'}
                  </button>
                )}
              </>
            ) : (
              <>
                <button className="action-menu-item" onClick={() => { onRetry(job.id); setMenuOpen(false); }}>
                  <span>🔄</span> {t('dashboard.retry')}
                </button>
                <button className="action-menu-item" onClick={() => { onDetails(job.id); setMenuOpen(false); }}>
                  <span>ℹ️</span> {t('dashboard.details')}
                </button>
              </>
            )}
            <div style={{ height: '1px', background: '#eee', margin: '4px 0' }}></div>
            <button 
              className="action-menu-item danger" 
              onClick={() => { onDelete(job.id); setMenuOpen(false); }}
              aria-label={t('dashboard.delete') || 'Delete'}
            >
              <span>🗑️</span> {t('dashboard.delete')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
});

export default JobItem;
