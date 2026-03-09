import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from '../../hooks/useTranslation';
import { mediaService } from '../../services/mediaService';
import './FileSelectorModal.css';

const FileSelectorModal = ({ isOpen, onClose, onSelect, activeTab }) => {
    const { t } = useTranslation();
    const [files, setFiles] = useState([]);
    const [loading, setLoading] = useState(false);
    const [search, setSearch] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');

    useEffect(() => {
        const handler = setTimeout(() => {
            setDebouncedSearch(search);
        }, 500);
        return () => clearTimeout(handler);
    }, [search]);

    useEffect(() => {
        if (isOpen) {
            fetchFiles();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, debouncedSearch, activeTab]);

    const fetchFiles = async () => {
        setLoading(true);
        try {
            const mediaType = activeTab.toUpperCase();
            const data = await mediaService.getVideos({
                page: 1,
                limit: 50,
                search: debouncedSearch,
                mediaType: mediaType,
                status: 'COMPLETED' // Only show completed files for processing
            });
            setFiles(data.items || []);
        } catch (error) {
            console.error("Failed to fetch files", error);
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    const handleBackdropClick = (e) => {
        if (e.target === e.currentTarget) {
            onClose();
        }
    };

    const formatSize = (bytes) => {
        if (!bytes) return '0 MB';
        const mb = bytes / (1024 * 1024);
        return `${mb.toFixed(1)} MB`;
    };

    const formatDate = (dateString) => {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleDateString();
    };

    const content = (
        <div className="file-selector-backdrop" onClick={handleBackdropClick}>
            <div className="file-selector-container">
                <div className="file-selector-header">
                    <h2>{t('dashboard.chooseExisting')}</h2>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>

                <div className="file-selector-search">
                    <input
                        type="text"
                        placeholder={t('dashboard.searchFilesPlaceholder') || "Search files..."}
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                    <span className="search-icon">🔍</span>
                </div>

                <div className="file-selector-body">
                    {loading ? (
                        <div className="loading-state">{t('dashboard.loadingLibrary')}</div>
                    ) : files.length === 0 ? (
                        <div className="empty-state">{t('dashboard.noFilesFound')}</div>
                    ) : (
                        <div className="file-grid">
                            {files.map(file => (
                                <div key={file.id} className="file-card" onClick={() => onSelect(file)}>
                                    <div className="file-thumbnail">
                                        {file.thumbnail_url ? (
                                            <img src={file.thumbnail_url} alt={file.title} />
                                        ) : (
                                            <div className="file-icon-placeholder">
                                                {activeTab === 'video' ? '🎬' : activeTab === 'audio' ? '🎵' : '📄'}
                                            </div>
                                        )}
                                    </div>
                                    <div className="file-info">
                                        <div className="file-title" title={file.title || file.original_filename}>
                                            {file.title || file.original_filename}
                                        </div>
                                        <div className="file-meta">
                                            <span>{formatSize(file.size_bytes)}</span>
                                            <span>•</span>
                                            <span>{formatDate(file.created_at)}</span>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );

    return createPortal(content, document.body);
};

export default FileSelectorModal;
