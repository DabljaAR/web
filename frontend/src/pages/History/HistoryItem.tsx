import React, { memo } from 'react';
import type { RecentJob } from '../../types/job';

interface HistoryItemProps {
  item: RecentJob;
  t: (key: string) => string;
  onPreview: (item: RecentJob) => void;
  onDownload: (item: RecentJob) => void;
  onDelete: (id: string) => void;
  onViewTasks: (id: string, name: string) => void;
  onRedub: (id: string, name: string) => void;
  onPreviewAudio: (id: string) => void;
  onDownloadAudio: (id: string) => void;
  onPreviewTranscript: (item: RecentJob) => void;
  onPreviewTranslation: (item: RecentJob) => void;
}

const HistoryItem: React.FC<HistoryItemProps> = memo(({ 
  item, 
  t, 
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

  const isVideo = item.mediaType === 'VIDEO' || (!item.mediaType && item.name.match(/\.(mp4|mov|avi|mkv)$/i));
  const isAudio = item.mediaType === 'AUDIO' || (!item.mediaType && item.name.match(/\.(mp3|wav|m4a)$/i));

  return (
    <div className="history-item">
      <div className="item-content">
        <div className="item-thumbnail">
          {item.thumbnailUrl ? (
            <img src={item.thumbnailUrl} alt={item.name} className="item-thumb-img" />
          ) : (
            <div className="item-type-icon">
              {isVideo ? '🎬' : isAudio ? '🎵' : '📄'}
            </div>
          )}
        </div>
        
        <div className="item-details">
          <div className="item-header">
            <h3 className="item-title" title={item.name}>{item.name}</h3>
            <span className={`item-status ${getStatusClass(item.status)}`}>
              <span>{getStatusIcon(item.status)}</span>
              <span>{t(`history.status${item.status.charAt(0).toUpperCase() + item.status.slice(1)}`) || item.status}</span>
            </span>
          </div>

          <div className="item-info">
            <span>{item.date ? new Date(item.date).toLocaleDateString() : 'N/A'}</span>
            {item.mediaType && <span className="item-type-badge">{item.mediaType}</span>}
          </div>

          <div className="item-actions">
            {/* Common Actions */}
            <button className="btn btn-secondary" onClick={() => onViewTasks(item.id, item.name)}>
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
                <button className="btn btn-secondary" onClick={() => onRedub(item.id, item.name)}>
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
