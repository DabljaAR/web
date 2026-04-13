import React from 'react';

const OriginalVideoItem = ({ item, t, getStatusClass, getStatusIcon, getStatusText, handlePreview, handleDownload, handleDelete }) => {
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

                    <div className="item-meta">
                        <div className="meta-item">
                            <span className="meta-label">{t('originalVideos.metaDuration')}</span>
                            <span className="meta-value">{item.duration}</span>
                        </div>
                        <div className="meta-item">
                            <span className="meta-label">{t('originalVideos.metaSize')}</span>
                            <span className="meta-value">{item.size}</span>
                        </div>
                    </div>

                    <div className="item-info">
                        <span>{t('originalVideos.started')}</span> {item.started}
                    </div>

                    <div className="item-actions">
                        {item.status === 'completed' && (
                            <>
                                <button className="btn btn-secondary" onClick={() => handlePreview(item.id)}>
                                    <span>👁</span> {t('originalVideos.preview')}
                                </button>
                                <button className="btn btn-secondary" onClick={() => handleDownload(item.id)}>
                                    <span>⬇</span> {t('originalVideos.download')}
                                </button>
                            </>
                        )}
                        <button className="btn btn-danger btn-icon" onClick={() => handleDelete(item.id)}>🗑</button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default OriginalVideoItem;
