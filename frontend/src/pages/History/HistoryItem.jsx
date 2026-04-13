import React from 'react';

const HistoryItem = ({ 
  item, 
  t, 
  getStatusClass, 
  getStatusIcon, 
  getStatusText, 
  setTasksModalVideo, 
  setTasksModalOpen, 
  handlePreviewTextComparison, 
  handlePreview, 
  handleDownload, 
  handleRedub, 
  handleDelete 
}) => {
  return (
    <div className="history-item">
      <div className="item-content">
        <div className="item-thumbnail">
          {item.thumbnail ? (
            <img src={item.thumbnail} alt={item.title} style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '4px' }} />
          ) : (
            item.mediaType === 'AUDIO' ? '🎵' :
              item.mediaType === 'TEXT' ? '📄' : '🎬'
          )}
        </div>
        <div className="item-details">
          <div className="item-header">
            <h3 className="item-title">{item.title}</h3>
            <span className={`item-status ${getStatusClass(item.status)}`}>
              <span>{getStatusIcon(item.status)}</span>
              <span>{getStatusText(item.status)}</span>
            </span>
          </div>

          {item.error && (
            <div className="error-message">
              <strong>{t('history.error')}</strong> {item.error}
            </div>
          )}

          {item.status !== 'processing' && item.status !== 'pending' && item.status !== 'failed' && (
            <div className="item-meta">
              <div className="meta-item">
                <span className="meta-label">{t('history.metaDomain')}</span>
                <span className="meta-value">{item.domain}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">{t('history.metaStyle')}</span>
                <span className="meta-value">{item.style}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">{t('history.metaVoice')}</span>
                <span className="meta-value">{item.voice}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">{t('history.metaDuration')}</span>
                <span className="meta-value">{item.duration}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">{t('history.metaSize')}</span>
                <span className="meta-value">{item.size}</span>
              </div>
            </div>
          )}

          <div className="item-info">
            {(item.status === 'processing' || item.status === 'pending') && (
              <>
                <span>{t('history.started')}</span> {item.started}
              </>
            )}
            {item.status === 'failed' && (
              <>
                <span>{t('history.attempted')}</span> {item.attempted} |{' '}
                <span>{t('history.creditsNotCharged')}</span>
              </>
            )}
            {item.status === 'completed' && (
              <>
                <span>{t('history.processed')}</span> {item.processed} |{' '}
                <span>{t('history.creditsUsed')}</span> {item.creditsUsed}
              </>
            )}
          </div>

          <div className="item-actions">
            {/* Tasks button — always visible so user can see task history */}
            <button
              className="btn btn-secondary"
              onClick={() => {
                setTasksModalVideo({ id: item.id, title: item.title });
                setTasksModalOpen(true);
              }}
            >
              <span>📋</span>
              <span>Tasks</span>
            </button>

            {item.status === 'completed' && (
              <>
                {item.transcriptUrl && item.translationUrl && (
                  <button
                    className="btn btn-secondary"
                    onClick={() => handlePreviewTextComparison(item.id)}
                  >
                    <span>📝</span>
                    <span>{t('history.preview') || 'Preview'} Text</span>
                  </button>
                )}
                <div className="action-group" style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    className="btn btn-secondary"
                    onClick={() => handlePreview(item.id)}
                  >
                    <span>👁</span>
                    <span>{t('history.preview')}</span>
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleDownload(item.id)}
                  >
                    <span>⬇</span>
                    <span>{t('history.download')}</span>
                  </button>
                </div>
                <button
                  className="btn btn-secondary"
                  onClick={() => handleRedub(item.id)}
                >
                  <span>🔄</span>
                  <span>{t('history.redub')}</span>
                </button>
              </>
            )}
            <button
              className="btn btn-danger btn-icon"
              onClick={() => handleDelete(item.id)}
            >
              🗑
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default HistoryItem;
