import React, { memo } from 'react';
import PropTypes from 'prop-types';
import { formatDateLongDMY } from '../../utils/formatters';

const OriginalVideoItem = memo(({ item, t, language, onPreview, onDownload, onDelete }) => {
    const getStatusClass = (status) => {
        switch (status) {
            case 'completed': return 'completed';
            case 'processing':
            case 'queued':
            case 'pending': return 'processing';
            case 'failed': return 'failed';
            default: return '';
        }
    };

    const getStatusIcon = (status) => {
        switch (status) {
            case 'completed': return '✅';
            case 'processing':
            case 'queued':
            case 'pending': return '⏳';
            case 'failed': return '❌';
            default: return '❓';
        }
    };

    // item.name can be missing (e.g., when both title and original_filename are absent upstream),
    // so normalize to a safe display name and only run extension checks on a string.
    const displayName =
        (typeof item?.name === 'string' && item.name.trim()) ? item.name :
        (typeof item?.title === 'string' && item.title.trim()) ? item.title :
        (typeof item?.original_filename === 'string' && item.original_filename.trim()) ? item.original_filename :
        (t('history.untitled') || 'Untitled');

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

                    <div className="item-info" style={{ marginTop: '8px' }}>
                        <span className="item-date">{dateText}</span>{' '}
                        <br />
                        <span className="item-type-inline">{typeText}</span>
                    </div>

                    <div className="item-actions" style={{ marginTop: '16px' }}>
                        {item.status === 'completed' && (
                            <>
                                <button className="btn btn-secondary" onClick={() => onPreview(item)}>
                                    <span>👁️</span> {t('originalVideos.preview')}
                                </button>
                                <button className="btn btn-secondary" onClick={() => onDownload(item)}>
                                    <span>⬇️</span> {t('originalVideos.download')}
                                </button>
                            </>
                        )}
                        <div className="spacer" style={{ flex: 1 }}></div>
                        <button 
                            className="btn btn-danger btn-icon" 
                            onClick={() => onDelete(item.id)}
                            aria-label={t('history.delete') || 'Delete'}
                        >
                            🗑️
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
});

OriginalVideoItem.propTypes = {
    item: PropTypes.object.isRequired,
    t: PropTypes.func.isRequired,
    language: PropTypes.string,
    onPreview: PropTypes.func.isRequired,
    onDownload: PropTypes.func.isRequired,
    onDelete: PropTypes.func.isRequired,
};

export default OriginalVideoItem;
