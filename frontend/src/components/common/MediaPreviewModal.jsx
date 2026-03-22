import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';
import './MediaPreviewModal.css';

const MediaPreviewModal = ({ isOpen, onClose, url, type, title, secondaryUrl, primaryTitle = 'Original', secondaryTitle = 'Translated' }) => {
    const { t } = useTranslation();
    const [isMaximized, setIsMaximized] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [textPreview, setTextPreview] = useState('');
    const [textError, setTextError] = useState('');
    const [secondaryTextPreview, setSecondaryTextPreview] = useState('');
    const [secondaryTextError, setSecondaryTextError] = useState('');
    const videoRef = useRef(null);

    // Close on Escape key
    useEffect(() => {
        const handleEsc = (e) => {
            if (e.key === 'Escape') onClose();
        };
        if (isOpen) {
            document.addEventListener('keydown', handleEsc);
            document.body.style.overflow = 'hidden'; // Prevent background scrolling
        }
        return () => {
            document.removeEventListener('keydown', handleEsc);
            document.body.style.overflow = 'unset';
        };
    }, [isOpen, onClose]);

    // Reset max state when opening
    useEffect(() => {
        if (isOpen) {
            setIsMaximized(false);
            setIsLoading(true);
            setTextPreview('');
            setTextError('');
            setSecondaryTextPreview('');
            setSecondaryTextError('');
        }
    }, [isOpen]);

    useEffect(() => {
        if (!isOpen || !url) return;

        const isVideoLike = type === 'VIDEO' || type === 'video' || (type === undefined && url.match(/\.(mp4|mov|avi|mkv|webm|m3u8)$/i));
        const isAudioLike = type === 'AUDIO' || type === 'audio' || (type === undefined && url.match(/\.(mp3|wav|m4a|ogg)$/i));

        if (isVideoLike || isAudioLike) return;

        let aborted = false;

        const parseTextPayload = (payload) => {
            if (payload == null) return 'No content available.';

            if (typeof payload === 'string') {
                // Might be a raw JSON string or plain text.
                try {
                    return parseTextPayload(JSON.parse(payload));
                } catch (_) {
                    return payload || 'No content available.';
                }
            }

            // Object payload
            if (typeof payload?.text === 'string') return payload.text;
            if (typeof payload?.transcript === 'string') return payload.transcript;
            return JSON.stringify(payload, null, 2);
        };

        const loadText = async (u) => {
            // Backend API endpoints are passed as relative paths (e.g. /jobs/{id}/preview)
            if (typeof u === 'string' && u.startsWith('/')) {
                const data = await api.getText(u);
                return parseTextPayload(data);
            }

            const res = await fetch(u);
            if (!res.ok) {
                throw new Error(`Failed to fetch preview (${res.status})`);
            }
            const bodyText = await res.text();
            return parseTextPayload(bodyText);
        };

        const loadTextPreview = async () => {
            try {
                const preview = await loadText(url);

                if (!aborted) {
                    setTextPreview(preview);

                    if (secondaryUrl) {
                        try {
                            const secondPreview = await loadText(secondaryUrl);
                            if (!aborted) {
                                setSecondaryTextPreview(secondPreview);
                            }
                        } catch (secondaryErr) {
                            if (!aborted) {
                                setSecondaryTextError(secondaryErr.message || 'Failed to load translation preview.');
                            }
                        }
                    }

                    setIsLoading(false);
                }
            } catch (err) {
                if (!aborted) {
                    setTextError(err.message || 'Failed to load text preview.');
                    setIsLoading(false);
                }
            }
        };

        loadTextPreview();

        return () => {
            aborted = true;
        };
    }, [isOpen, url, type, secondaryUrl]);

    if (!isOpen || !url) return null;

    const toggleMaximize = () => {
        setIsMaximized(!isMaximized);
    };

    const handleMediaLoaded = () => {
        setIsLoading(false);
        // Auto play if desired
        if (videoRef.current) {
            videoRef.current.play().catch(err => console.log('Autoplay blocked', err));
        }
    };

    const handleBackdropClick = (e) => {
        if (e.target === e.currentTarget) {
            onClose();
        }
    };

    // Determine label based on type
    const typeLabel = type === 'VIDEO' ? t('dashboard.tabVideo') || 'Video' :
        type === 'AUDIO' ? t('dashboard.tabAudio') || 'Audio' :
            type === 'TEXT' ? t('dashboard.tabText') || 'Text' :
                'Media';

    // Improved detection logic
    const isVideo = type === 'VIDEO' || type === 'video' || (type === undefined && url.match(/\.(mp4|mov|avi|mkv|webm|m3u8)$/i));
    const isAudio = type === 'AUDIO' || type === 'audio' || (type === undefined && url.match(/\.(mp3|wav|m4a|ogg)$/i));

    const content = (
        <div className="media-modal-backdrop" onClick={handleBackdropClick}>
            <div className={`media-modal-container ${isMaximized ? 'maximized' : ''}`}>

                {/* Header */}
                <div className="media-modal-header">
                    <div className="media-modal-title">
                        <span className="media-type-badge">{typeLabel}</span>
                        <span>{title || t('dashboard.preview')}</span>
                    </div>
                    <div className="media-modal-controls">
                        <button
                            className="ctrl-btn"
                            onClick={toggleMaximize}
                            title={isMaximized ? "Restore Down" : "Maximize"}
                        >
                            {isMaximized ? (
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path>
                                </svg>
                            ) : (
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"></path>
                                </svg>
                            )}
                        </button>
                        <button
                            className="ctrl-btn close-btn"
                            onClick={onClose}
                            title="Close"
                        >
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <line x1="18" y1="6" x2="6" y2="18"></line>
                                <line x1="6" y1="6" x2="18" y2="18"></line>
                            </svg>
                        </button>
                    </div>
                </div>

                {/* Body */}
                <div className="media-modal-body">
                    {isLoading && <div className="loading-spinner"></div>}

                    {isVideo ? (
                        <video
                            ref={videoRef}
                            className="media-player"
                            controls
                            autoPlay={false}
                            onLoadedData={handleMediaLoaded}
                            onError={() => setIsLoading(false)}
                        >
                            <source src={url} />
                            Your browser does not support the video tag.
                        </video>
                    ) : isAudio ? (
                        <div style={{ width: '100%', padding: '0 40px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                            <div style={{ marginBottom: '20px', fontSize: '64px' }}>🎵</div>
                            <audio
                                className="media-player"
                                style={{ height: '54px' }}
                                controls
                                autoPlay={false}
                                onLoadedData={handleMediaLoaded}
                                onError={() => setIsLoading(false)}
                                src={url}
                            >
                                Your browser does not support the audio element.
                            </audio>
                        </div>
                    ) : (
                        <div className="text-preview-wrapper">
                            {secondaryUrl ? (
                                <div className="text-compare-grid">
                                    <div className="text-compare-panel">
                                        <h4 className="text-compare-title">{primaryTitle}</h4>
                                        {textError ? (
                                            <div className="text-preview-error">
                                                {textError}
                                                <br />
                                                <a href={url} target="_blank" rel="noreferrer" style={{ color: '#3b82f6' }}>Open File</a>
                                            </div>
                                        ) : (
                                            <pre className="text-preview-content">{textPreview}</pre>
                                        )}
                                    </div>

                                    <div className="text-compare-panel">
                                        <h4 className="text-compare-title">{secondaryTitle}</h4>
                                        {secondaryTextError ? (
                                            <div className="text-preview-error">
                                                {secondaryTextError}
                                                <br />
                                                <a href={secondaryUrl} target="_blank" rel="noreferrer" style={{ color: '#3b82f6' }}>Open File</a>
                                            </div>
                                        ) : (
                                            <pre className="text-preview-content">{secondaryTextPreview}</pre>
                                        )}
                                    </div>
                                </div>
                            ) : textError ? (
                                <div className="text-preview-error">
                                    {textError}
                                    <br />
                                    <a href={url} target="_blank" rel="noreferrer" style={{ color: '#3b82f6' }}>Open File</a>
                                </div>
                            ) : (
                                <pre className="text-preview-content">{textPreview}</pre>
                            )}
                        </div>
                    )}
                </div>

            </div>
        </div>
    );

    // Use portal explicitly to render at document body level
    return createPortal(content, document.body);
};

export default MediaPreviewModal;
