import React, { memo } from 'react';
import type { RecentJob } from '../../types/job';
import { formatDateLongDMY } from '../../utils/formatters';

interface HistoryItemProps {
  item: RecentJob;
  t: (key: string) => string;
  language?: string;
  onPreview: (item: RecentJob) => void;
  onDownload: (item: RecentJob) => void;
  onDelete: (id: string) => void;
  onViewTasks: (id: string, name: string) => void;
  onRedub: (id: string, name: string) => void;
  onPreviewTranscript: (item: RecentJob) => void;
  onPreviewTranslation: (item: RecentJob) => void;
}

const HistoryItem: React.FC<HistoryItemProps> = memo(({ 
  item, 
  t, 
  language,
  onPreview, 
  onDownload, 
  onDelete,
  onViewTasks,
  onRedub,
  onPreviewTranscript,
  onPreviewTranslation
}) => {
  const getStatusClass = (status: string) => {
    switch (status) {
      case 'completed': return 'completed';
      case 'processing':
      case 'queued':
      case 'pending': return 'processing';
      case 'failed': return 'failed';
      default: return '';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return '✅';
      case 'processing':
      case 'queued':
      case 'pending': return '⏳';
      case 'failed': return '❌';
      default: return '❓';
    }
  };

  // Be defensive: some API shapes may omit name/title/original filename.
  const displayName = (typeof (item as any)?.name === 'string' && (item as any).name.trim())
    ? (item as any).name
    : (t('history.untitled') || 'Untitled');

  const nameForMatch = typeof displayName === 'string' ? displayName : '';
  const isVideo = item.mediaType === 'VIDEO' || (!item.mediaType && /\.(mp4|mov|avi|mkv)$/i.test(nameForMatch));
  const isAudio = item.mediaType === 'AUDIO' || (!item.mediaType && /\.(mp3|wav|m4a)$/i.test(nameForMatch));

  const resolvedLocale = language === 'ar'
    ? 'ar-EG-u-nu-latn'
    : (language === 'en' ? 'en-US' : (language || (typeof navigator !== 'undefined' ? navigator.language : 'en-US')));

  const dateText = item.date && !Number.isNaN(new Date(item.date).getTime())
    ? formatDateLongDMY(item.date, resolvedLocale)
    : (t('history.noDate') || 'N/A');

  const typeTextRaw = isVideo
    ? (t('originalVideos.video') || 'Video')
    : isAudio
      ? (t('originalVideos.audio') || 'Audio')
      : (t('originalVideos.text') || 'Text');
  const typeText = language === 'en'
    ? `${typeTextRaw}`.slice(0, 1).toUpperCase() + `${typeTextRaw}`.slice(1).toLowerCase()
    : typeTextRaw;

  return (
    <div className="history-item">
      <div className="item-content">
        <div className="item-thumbnail">
          {item.thumbnailUrl ? (
            <img src={item.thumbnailUrl} alt={displayName} className="item-thumb-img" />
          ) : (
            <div className="item-type-icon">
              {isVideo ? '🎬' : isAudio ? '🎵' : '📄'}
            </div>
          )}
        </div>
        
        <div className="item-details">
          <div className="item-header">
            <h3 className="item-title" title={displayName}>{displayName}</h3>
            <span className={`item-status ${getStatusClass(item.status)}`}>
              <span>{getStatusIcon(item.status)}</span>
              <span>{t(`history.status${item.status.charAt(0).toUpperCase() + item.status.slice(1)}`) || item.status}</span>
            </span>
          </div>

          <div className="item-info">
            <span className="item-date">{dateText}</span>{' '}
           <br />
            <span className="item-type-inline">{typeText}</span>
          </div>

          <div className="item-actions">
            {/* Common Actions */}
            <button className="btn btn-secondary" onClick={() => onViewTasks(item.id, displayName)}>
              <span>📋</span> {t('history.tasks') || 'Tasks'}
            </button>

            {item.status === 'completed' && (
              <>
                <button className="btn btn-secondary" onClick={() => onPreview(item)}>
                  <span>👁️</span> {t('history.preview')}
                </button>
                <button className="btn btn-secondary" onClick={() => onDownload(item)}>
                  <span>⬇️</span> {t('history.download')}
                </button>
                <button className="btn btn-secondary" onClick={() => onRedub(item.id, displayName)}>
                  <span>🔄</span> {t('history.redub')}
                </button>
                
                {/* Secondary Actions (Transcript/Translation) */}
                {(item.transcriptUrl || item.translationUrl) && (
                  <div className="more-actions">
                    {item.transcriptUrl && (
                      <button className="btn btn-link" onClick={() => onPreviewTranscript(item)}>
                        {t('history.transcript') || 'Transcript'}
                      </button>
                    )}
                    {item.translationUrl && (
                      <button className="btn btn-link" onClick={() => onPreviewTranslation(item)}>
                        {t('history.translation') || 'Translation'}
                      </button>
                    )}
                  </div>
                )}
              </>
            )}

            <div className="spacer"></div>
            
            <button className="btn btn-danger btn-icon" onClick={() => onDelete(item.id)}>
              🗑️
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});

export default HistoryItem;
