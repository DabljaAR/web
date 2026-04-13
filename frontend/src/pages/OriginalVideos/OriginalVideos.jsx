import { useState, useEffect, useRef } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from '../../hooks/useTranslation';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import MediaPreviewModal from '../../components/common/MediaPreviewModal';
import { mediaService } from '../../services/mediaService';
import '../../styles/history.css';
import '../../styles/dashboard.css';

const OriginalVideos = () => {
    const { t } = useTranslation();
    const [filters, setFilters] = useState({
        search: '',
        status: 'all',
        domain: 'all',
        dateRange: 'last30Days',
        sortBy: 'dateNewest',
        mediaType: 'all'
    });

    const [activeMediaTab, setActiveMediaTab] = useState('all');

    const [pagination, setPagination] = useState({
        page: 1,
        limit: 5,
        total: 0,
        pages: 1,
        totalCompleted: 0,
        totalFailed: 0
    });

    // List & Loading State
    const [historyItems, setHistoryItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [isPolling, setIsPolling] = useState(false);
    const [error, setError] = useState(null);
    const [debouncedSearch, setDebouncedSearch] = useState(filters.search);
    const [refreshKey, setRefreshKey] = useState(0);

    // Preview Modal State
    const [previewModalOpen, setPreviewModalOpen] = useState(false);
    const [previewJob, setPreviewJob] = useState(null);

    // Upload & Processing State
    const [showUploadSection, setShowUploadSection] = useState(false);
    const [selectedFile, setSelectedFile] = useState(null);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadError, setUploadError] = useState(null);
    const [isDragOver, setIsDragOver] = useState(false);
    const fileInputRef = useRef(null);

    // YouTube Modal State
    const [showYoutubeModal, setShowYoutubeModal] = useState(false);
    const [youtubeUrl, setYoutubeUrl] = useState('');
    const [youtubeFormat, setYoutubeFormat] = useState('video');
    const [youtubeQuality, setYoutubeQuality] = useState('720p');
    const [isYoutubeDownloading, setIsYoutubeDownloading] = useState(false);
    const [youtubeError, setYoutubeError] = useState(null);

    // Track deleting items
    const deletingIds = useRef(new Set());

    const formatDuration = (seconds) => {
        if (!seconds) return '00:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const formatSize = (bytes) => {
        if (!bytes) return '0 MB';
        const mb = bytes / (1024 * 1024);
        return `${mb.toFixed(1)} MB`;
    };

    const formatDate = (dateString) => {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: 'numeric',
            minute: 'numeric',
            hour12: true
        });
    };

    useEffect(() => {
        const handler = setTimeout(() => {
            setDebouncedSearch(filters.search);
            if (filters.search !== debouncedSearch) {
                setPagination(prev => ({ ...prev, page: 1 }));
            }
        }, 500);
        return () => clearTimeout(handler);
    }, [filters.search, debouncedSearch]);

    useEffect(() => {
        const fetchHistory = async (internal = false) => {
            try {
                if (!internal) setLoading(true);
                // Specifically filter for VIDEO media type
                const data = await mediaService.getVideos({
                    page: pagination.page,
                    limit: pagination.limit,
                    search: debouncedSearch,
                    sortBy: filters.sortBy,
                    dateRange: filters.dateRange,
                    status: filters.status,
                    mediaType: activeMediaTab === 'all' ? '' : activeMediaTab.toUpperCase()
                });

                const videos = Array.isArray(data) ? data : data.items || [];
                const total = data.total || videos.length;
                const pages = data.pages || 1;
                const totalCompleted = data.total_completed || 0;
                const totalFailed = data.total_failed || 0;

                const mappedItems = videos.map(video => ({
                    id: video.id,
                    title: video.title || video.original_filename,
                    thumbnail: video.thumbnail_url,
                    status: video.status.toLowerCase(),
                    domain: video.domain || t('originalVideos.domainGeneral') || 'General',
                    style: video.style || 'Neutral',
                    voice: video.voice || 'Male Voice 1',
                    duration: formatDuration(video.duration),
                    size: formatSize(video.size_bytes),
                    processed: formatDate(video.updated_at),
                    started: formatDate(video.created_at),
                    attempted: formatDate(video.created_at),
                    rawDate: video.created_at,
                    creditsUsed: 0,
                    error: video.error_message,

                    createdAt: video.created_at,
                    url: video.url,
                    audioUrl: video.audio_url,
                    mediaType: video.media_type || (activeMediaTab !== 'all' ? activeMediaTab.toUpperCase() : 'VIDEO')
                }));

                setHistoryItems(mappedItems.filter(item => !deletingIds.current.has(item.id)));
                setPagination(prev => ({
                    ...prev,
                    total: total,
                    pages: pages,
                    totalCompleted: totalCompleted,
                    totalFailed: totalFailed
                }));

                // Track if we need to continue polling
                const hasActive = mappedItems.some(item =>
                    item.status === 'processing' || item.status === 'pending'
                );
                setIsPolling(hasActive);

                setError(null);
            } catch (err) {
                console.error("Failed to fetch original videos:", err);
                if (!internal) setError(t('originalVideos.loadError') || 'Failed to load original videos.');
                setIsPolling(false);
            } finally {
                if (!internal) setLoading(false);
            }
        };

        fetchHistory();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [pagination.page, debouncedSearch, filters.sortBy, filters.dateRange, filters.status, activeMediaTab, refreshKey]);

    // Polling Effect (Dashboard Style)
    useEffect(() => {
        let intervalId;
        if (isPolling) {
            intervalId = setInterval(() => {
                // Call fetch with internal flag to avoid showing loading spinner
                const fetchHistoryInternal = async () => {
                    try {
                        const data = await mediaService.getVideos({
                            page: pagination.page,
                            limit: pagination.limit,
                            search: debouncedSearch,
                            sortBy: filters.sortBy,
                            dateRange: filters.dateRange,
                            status: filters.status,
                            mediaType: activeMediaTab === 'all' ? '' : activeMediaTab.toUpperCase()
                        });

                        const videos = Array.isArray(data) ? data : data.items || [];
                        const mappedItems = videos.map(video => ({
                            id: video.id,
                            title: video.title || video.original_filename,
                            thumbnail: video.thumbnail_url,
                            status: video.status.toLowerCase(),
                            duration: formatDuration(video.duration),
                            size: formatSize(video.size_bytes),
                            processed: formatDate(video.updated_at),
                            started: formatDate(video.created_at),

                            createdAt: video.created_at,
                            url: video.url,
                            audioUrl: video.audio_url,
                            mediaType: video.media_type || (activeMediaTab !== 'all' ? activeMediaTab.toUpperCase() : 'VIDEO')
                        }));

                        setHistoryItems(mappedItems.filter(item => !deletingIds.current.has(item.id)));

                        const hasActive = mappedItems.some(item =>
                            item.status === 'processing' || item.status === 'pending'
                        );
                        if (!hasActive) setIsPolling(false);
                    } catch (e) {
                        console.error("Polling fetch failed", e);
                        setIsPolling(false);
                    }
                };
                fetchHistoryInternal();
            }, 5000);
        }
        return () => {
            if (intervalId) clearInterval(intervalId);
        };
    }, [isPolling, pagination.page, debouncedSearch, filters.sortBy, filters.dateRange, filters.status, activeMediaTab]);



    const handlePageChange = (newPage) => {
        if (newPage >= 1 && newPage <= pagination.pages) {
            setPagination(prev => ({ ...prev, page: newPage }));
        }
    };

    const handleFilterChange = (e) => {
        const { name, value } = e.target;
        setFilters(prev => ({
            ...prev,
            [name]: value
        }));
        setPagination(prev => ({ ...prev, page: 1 }));
    };

    const handleResetFilters = () => {
        setFilters({
            search: '',
            status: 'all',
            domain: 'all',
            dateRange: 'last30Days',
            sortBy: 'dateNewest',
            mediaType: 'all'
        });
        setActiveMediaTab('all');
        setPagination(prev => ({ ...prev, page: 1 }));
    };

    const handleMediaTabChange = (tab) => {
        setActiveMediaTab(tab);
        setPagination(prev => ({ ...prev, page: 1 }));
    };

    const handlePreview = (id) => {
        const item = historyItems.find(i => i.id === id);
        if (item && item.url) {
            setPreviewJob({
                ...item,
                name: item.title
            });
            setPreviewModalOpen(true);
        } else {
            toast.error(t('dashboard.noPreviewError') || "No preview URL available.");
        }
    };

    const handleDownload = (id) => {
        const item = historyItems.find(i => i.id === id);
        if (item && item.url) {
            const link = document.createElement('a');
            link.href = item.url;
            link.download = item.title || 'download';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } else {
            toast.error(t('dashboard.noPreviewError') || "No download URL available.");
        }
    };

    const handleFileSelect = () => {
        fileInputRef.current?.click();
    };

    const handleFileChange = (e) => {
        const file = e.target.files?.[0];
        if (file) {
            setSelectedFile(file);
        }
    };

    const handleDragOver = (e) => {
        e.preventDefault();
        setIsDragOver(true);
    };

    const handleDragLeave = () => {
        setIsDragOver(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) {
            setSelectedFile(file);
        }
    };

    const handleStartProcessing = async () => {
        if (!selectedFile) {
            toast.error(t('dashboard.selectFileError') || "Please select or upload a video first.");
            return;
        }

        setIsUploading(true);
        setUploadError(null);

        try {
            const formDataToUpload = new FormData();
            formDataToUpload.append('file', selectedFile);
            formDataToUpload.append('output_type', 'uploadOnly');

            await mediaService.uploadVideo(formDataToUpload);

            toast.success(t('dashboard.uploadSuccess') || "Upload successful! Processing started.");
            setSelectedFile(null);
            setShowUploadSection(false);

            // Refresh history
            setRefreshKey(k => k + 1);
        } catch (err) {
            console.error("Upload failed:", err);
            setUploadError(err.message || "Failed to start processing.");
        } finally {
            setIsUploading(false);
        }
    };

    const handleYoutubeDownload = async () => {
        if (!youtubeUrl.trim()) {
            setYoutubeError(t('originalVideos.youtubeErrorEmpty'));
            return;
        }
        const ytRegex = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?.*v=[\w-]+|shorts\/[\w-]+)|youtu\.be\/[\w-]+)/;
        if (!ytRegex.test(youtubeUrl.trim())) {
            setYoutubeError(t('originalVideos.youtubeErrorInvalid'));
            return;
        }

        setIsYoutubeDownloading(true);
        setYoutubeError(null);

        try {
            await mediaService.downloadFromYoutube({
                youtube_url: youtubeUrl.trim(),
                format: youtubeFormat,
                quality: youtubeQuality,
            });

            toast.success(t('originalVideos.youtubeSuccessMsg'));
            setYoutubeUrl('');
            setShowYoutubeModal(false);
            setShowUploadSection(false);
            setRefreshKey(k => k + 1);
        } catch (err) {
            console.error('YouTube download failed:', err);
            setYoutubeError(err.message || 'Failed to queue YouTube download.');
        } finally {
            setIsYoutubeDownloading(false);
        }
    };

    const handleDelete = async (id) => {
        if (window.confirm(t('originalVideos.deleteConfirm') || "Are you sure you want to delete this item?")) {
            try {
                // Mark as deleting
                deletingIds.current.add(id);

                // Optimistically remove from UI
                setHistoryItems(prev => prev.filter(item => item.id !== id));
                setPagination(prev => ({
                    ...prev,
                    total: Math.max(0, prev.total - 1)
                }));

                await mediaService.deleteVideo(id);

                const data = await mediaService.getVideos({
                    page: pagination.page,
                    limit: pagination.limit,
                    search: debouncedSearch,
                    sortBy: filters.sortBy,
                    dateRange: filters.dateRange,
                    status: filters.status,
                    mediaType: activeMediaTab === 'all' ? '' : activeMediaTab.toUpperCase()
                });
                const videos = Array.isArray(data) ? data : data.items || [];
                const mappedItems = videos.map(video => ({
                    id: video.id,
                    title: video.title || video.original_filename,
                    thumbnail: video.thumbnail_url,
                    status: video.status.toLowerCase(),
                    domain: video.domain || t('originalVideos.domainGeneral') || 'General',
                    style: video.style || 'Neutral',
                    voice: video.voice || 'Male Voice 1',
                    duration: formatDuration(video.duration),
                    size: formatSize(video.size_bytes),
                    processed: formatDate(video.updated_at),
                    started: formatDate(video.created_at),
                    attempted: formatDate(video.created_at),
                    rawDate: video.created_at,
                    creditsUsed: 0,
                    error: video.error_message,

                    createdAt: video.created_at,
                    url: video.url,
                    audioUrl: video.audio_url,
                    mediaType: video.media_type || (activeMediaTab !== 'all' ? activeMediaTab.toUpperCase() : 'VIDEO')
                }));
                setHistoryItems(mappedItems.filter(item => !deletingIds.current.has(item.id)));
                setPagination(prev => ({
                    ...prev,
                    total: data.total || 0,
                    pages: data.pages || 1,
                    totalCompleted: data.total_completed || 0,
                    totalFailed: data.total_failed || 0
                }));
                toast.success(t('dashboard.deleteSuccess') || "Deleted successfully.");
            } catch (err) {
                console.error("Failed to delete video:", err);
                toast.error(t('dashboard.deleteError') || "Failed to delete video");

                deletingIds.current.delete(id);
                // Refresh to restore state
                setRefreshKey(k => k + 1);
            } finally {
                setTimeout(() => {
                    if (deletingIds.current) deletingIds.current.delete(id);
                }, 10000);
            }
        }
    };

    const getStatusClass = (status) => {
        switch (status) {
            case 'completed': return 'status-completed';
            case 'failed': return 'status-failed';
            case 'processing':
            case 'pending': return 'status-processing';
            default: return '';
        }
    };

    const getStatusIcon = (status) => {
        switch (status) {
            case 'completed': return '✓';
            case 'failed': return '✗';
            case 'processing':
            case 'pending': return '⏳';
            default: return '';
        }
    };

    const getStatusText = (status) => {
        switch (status) {
            case 'completed': return t('originalVideos.statusCompleted');
            case 'failed': return t('originalVideos.statusFailed');
            case 'processing':
            case 'pending': return t('originalVideos.statusProcessing');
            default: return status;
        }
    };

    if (loading) {
        return (
            <div className="history-page">
                <BackgroundDecorations />
                <Navbar />
                <div className="main-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
                    <div className="loading-spinner" style={{ color: 'white' }}>{t('common.loading') || 'Loading original videos...'}</div>
                </div>
                <Footer />
            </div>
        );
    }

    return (
        <div className="history-page">
            <BackgroundDecorations />
            <Navbar />

            <div className="main-container">
                <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h1 className="page-title">{t('originalVideos.title')}</h1>
                    <button
                        className={`btn ${showUploadSection ? 'btn-secondary' : 'btn-primary'}`}
                        onClick={() => setShowUploadSection(!showUploadSection)}
                        style={{ width: 'auto', marginBottom: '16px' }}
                    >
                        {showUploadSection ? '✕ ' + t('common.cancel') : t('originalVideos.startUploading')}
                    </button>
                </div>

                <div className="tabs" style={{ marginBottom: '24px' }}>
                    <button
                        className={`tab ${activeMediaTab === 'all' ? 'active' : ''}`}
                        onClick={() => handleMediaTabChange('all')}
                    >
                        {t('originalVideos.allFiles')}
                    </button>
                    <button
                        className={`tab ${activeMediaTab === 'video' ? 'active' : ''}`}
                        onClick={() => handleMediaTabChange('video')}
                    >
                        {t('originalVideos.video')}
                    </button>
                    <button
                        className={`tab ${activeMediaTab === 'audio' ? 'active' : ''}`}
                        onClick={() => handleMediaTabChange('audio')}
                    >
                        {t('originalVideos.audio')}
                    </button>
                    <button
                        className={`tab ${activeMediaTab === 'text' ? 'active' : ''}`}
                        onClick={() => handleMediaTabChange('text')}
                    >
                        {t('originalVideos.text')}
                    </button>
                </div>

                {showUploadSection && (
                    <div className="card upload-section" style={{ marginBottom: '32px', animation: 'slideDown 0.3s ease-out' }}>
                        <input
                            type="file"
                            ref={fileInputRef}
                            onChange={handleFileChange}
                            accept={activeMediaTab === 'video' ? 'video/*' :
                                activeMediaTab === 'audio' ? 'audio/*' :
                                    activeMediaTab === 'text' ? '.txt,text/plain' :
                                        'video/*,audio/*,.txt,text/plain'}
                            style={{ display: 'none' }}
                        />

                        {!selectedFile && (
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                {/* Upload option */}
                                <div
                                    className={`upload-area ${isDragOver ? 'drag-over' : ''}`}
                                    onDragOver={handleDragOver}
                                    onDragLeave={handleDragLeave}
                                    onDrop={handleDrop}
                                    onClick={handleFileSelect}
                                >
                                    <div className="upload-icon">📤</div>
                                    <div className="upload-text">
                                        <h3>{t('dashboard.uploadTitle')}</h3>
                                        <p>{t('dashboard.uploadSubtitle')}</p>
                                    </div>
                                </div>

                                {/* YouTube option */}
                                <div
                                    className="upload-area upload-area-youtube"
                                    onClick={() => setShowYoutubeModal(true)}
                                >
                                    <div className="upload-icon">▶️</div>
                                    <div className="upload-text">
                                        <h3>{t('originalVideos.youtubeCardTitle')}</h3>
                                        <p>{t('originalVideos.youtubeCardSubtitle')}</p>
                                    </div>
                                </div>
                            </div>
                        )}

                        {selectedFile && (
                            <>
                                <div className="selected-file-info">
                                    <div className="selected-file-details">
                                        <span className="selected-file-icon">🎬</span>
                                        <span className="selected-file-name">{selectedFile.name}</span>
                                    </div>
                                    <button className="selected-file-clear" onClick={() => setSelectedFile(null)}>✕</button>
                                </div>
                                <button
                                    className="btn btn-primary"
                                    style={{ marginTop: '12px' }}
                                    onClick={handleStartProcessing}
                                    disabled={isUploading}
                                >
                                    {isUploading ? t('common.uploading') : t('originalVideos.startUploadingButton')}
                                </button>
                                {uploadError && (
                                    <div style={{ marginTop: '16px', color: 'var(--accent-red)' }}>{uploadError}</div>
                                )}
                            </>
                        )}
                    </div>
                )}

                {/* YouTube Modal */}
                {showYoutubeModal && (
                    <div
                        style={{
                            position: 'fixed', inset: 0, zIndex: 1000,
                            background: 'rgba(0,0,0,0.7)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center'
                        }}
                        onClick={(e) => { if (e.target === e.currentTarget) setShowYoutubeModal(false); }}
                    >
                        <div className="card" style={{ width: '100%', maxWidth: '520px', padding: '32px', position: 'relative' }}>
                            <button
                                onClick={() => { setShowYoutubeModal(false); setYoutubeError(null); setYoutubeUrl(''); }}
                                style={{
                                    position: 'absolute', top: '16px', right: '16px',
                                    background: 'none', border: 'none', fontSize: '1.2rem',
                                    cursor: 'pointer', color: 'var(--text-light)'
                                }}
                            >✕</button>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '24px' }}>
                                <span style={{ fontSize: '1.5rem' }}>▶️</span>
                                <h2 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700 }}>{t('originalVideos.youtubeModalTitle')}</h2>
                            </div>

                            <div style={{ marginBottom: '16px' }}>
                                <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-medium)' }}>
                                    {t('originalVideos.youtubeUrlLabel')}
                                </label>
                                <input
                                    type="url"
                                    className="search-input"
                                    placeholder={t('originalVideos.youtubeUrlPlaceholder')}
                                    value={youtubeUrl}
                                    onChange={(e) => { setYoutubeUrl(e.target.value); setYoutubeError(null); }}
                                    style={{ width: '100%', boxSizing: 'border-box' }}
                                />
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-medium)' }}>
                                        {t('originalVideos.youtubeFormatLabel')}
                                    </label>
                                    <select
                                        className="filter-select"
                                        value={youtubeFormat}
                                        onChange={(e) => setYoutubeFormat(e.target.value)}
                                        style={{ width: '100%' }}
                                    >
                                        <option value="video">🎬 {t('originalVideos.youtubeFormatVideo')}</option>
                                        <option value="audio">🎵 {t('originalVideos.youtubeFormatAudio')}</option>
                                    </select>
                                </div>
                                {youtubeFormat === 'video' && (
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-medium)' }}>
                                            {t('originalVideos.youtubeQualityLabel')}
                                        </label>
                                        <select
                                            className="filter-select"
                                            value={youtubeQuality}
                                            onChange={(e) => setYoutubeQuality(e.target.value)}
                                            style={{ width: '100%' }}
                                        >
                                            <option value="1080p">1080p</option>
                                            <option value="720p">720p</option>
                                            <option value="480p">480p</option>
                                            <option value="360p">360p</option>
                                        </select>
                                    </div>
                                )}
                            </div>

                            {youtubeError && (
                                <div style={{ marginBottom: '16px', color: 'var(--accent-red)', fontSize: '0.875rem' }}>
                                    {youtubeError}
                                </div>
                            )}

                            <button
                                className="btn btn-primary"
                                onClick={handleYoutubeDownload}
                                disabled={isYoutubeDownloading || !youtubeUrl.trim()}
                            >
                                {isYoutubeDownloading ? t('originalVideos.youtubeQueuingBtn') : t('originalVideos.youtubeDownloadBtn')}
                            </button>
                        </div>
                    </div>
                )}

                <div className="filter-section">
                    <h3 className="filter-title">{t('originalVideos.filterSearch')}</h3>
                    <div className="search-box">
                        <input
                            type="text"
                            className="search-input"
                            placeholder={t('originalVideos.searchPlaceholder')}
                            name="search"
                            value={filters.search}
                            onChange={handleFilterChange}
                        />
                        <span className="search-icon">🔍</span>
                    </div>

                    <div className="filter-grid">
                        <div className="filter-group">
                            <label className="filter-label">{t('originalVideos.status')}</label>
                            <select className="filter-select" name="status" value={filters.status} onChange={handleFilterChange}>
                                <option value="all">{t('originalVideos.statusAll')}</option>
                                <option value="completed">{t('originalVideos.statusCompleted')}</option>
                                <option value="failed">{t('originalVideos.statusFailed')}</option>
                                <option value="processing">{t('originalVideos.statusProcessing')}</option>
                            </select>
                        </div>

                        <div className="filter-group">
                            <label className="filter-label">{t('originalVideos.domain')}</label>
                            <select
                                className="filter-select"
                                name="domain"
                                value={filters.domain}
                                onChange={handleFilterChange}
                            >
                                <option value="all">{t('originalVideos.domainAll')}</option>
                                <option value="general">{t('originalVideos.domainGeneral')}</option>
                                <option value="technical">{t('originalVideos.domainTechnical')}</option>
                                <option value="medical">{t('originalVideos.domainMedical')}</option>
                                <option value="legal">{t('originalVideos.domainLegal')}</option>
                                <option value="education">{t('originalVideos.domainEducation')}</option>
                            </select>
                        </div>

                        <div className="filter-group">
                            <label className="filter-label">{t('originalVideos.dateRange')}</label>
                            <select className="filter-select" name="dateRange" value={filters.dateRange} onChange={handleFilterChange}>
                                <option value="last30Days">{t('originalVideos.last30Days')}</option>
                                <option value="last7Days">{t('originalVideos.last7Days')}</option>
                                <option value="last90Days">{t('originalVideos.last90Days')}</option>
                                <option value="allTime">{t('originalVideos.allTime')}</option>
                            </select>
                        </div>

                        <div className="filter-group">
                            <label className="filter-label">{t('originalVideos.sortBy')}</label>
                            <select className="filter-select" name="sortBy" value={filters.sortBy} onChange={handleFilterChange}>
                                <option value="dateNewest">{t('originalVideos.dateNewest')}</option>
                                <option value="dateOldest">{t('originalVideos.dateOldest')}</option>
                                <option value="nameAZ">{t('originalVideos.nameAZ')}</option>
                                <option value="nameZA">{t('originalVideos.nameZA')}</option>
                            </select>
                        </div>

                    </div>
                    <div style={{ display: 'flex', marginTop: '12px' }}>
                        <button className="btn btn-secondary" onClick={handleResetFilters} style={{ height: '42px', marginInlineEnd: 'auto' }}>
                            {t('originalVideos.resetFilters')}
                        </button>
                    </div>
                </div>

                <div className="stats-bar">
                    <div className="stat-item">
                        <span className="stat-label">{t('originalVideos.total')}</span>
                        <span className="stat-value">{pagination.total}</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-label">{t('originalVideos.completed')}</span>
                        <span className="stat-value">{pagination.totalCompleted}</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-label">{t('originalVideos.failed')}</span>
                        <span className="stat-value">{pagination.totalFailed}</span>
                    </div>
                </div>

                <div className="history-list">
                    {historyItems.length === 0 ? (
                        <div className="no-items" style={{ textAlign: 'center', padding: '2rem', color: 'rgba(255,255,255,0.6)' }}>
                            {error ? error : t('originalVideos.noItems')}
                        </div>
                    ) : (
                        historyItems.map((item) => (
                            <div key={item.id} className="history-item">
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
                        ))
                    )}
                </div>

                {pagination.pages > 1 && (
                    <div className="pagination">
                        <button className="page-btn" disabled={pagination.page === 1} onClick={() => handlePageChange(pagination.page - 1)}>&lt;</button>
                        {[...Array(pagination.pages)].map((_, i) => (
                            <button key={i + 1} className={`page-btn ${pagination.page === i + 1 ? 'active' : ''}`} onClick={() => handlePageChange(i + 1)}>{i + 1}</button>
                        ))}
                        <button className="page-btn" disabled={pagination.page === pagination.pages} onClick={() => handlePageChange(pagination.page + 1)}>&gt;</button>
                    </div>
                )}
            </div>
            <Footer />

            {/* Preview Modal */}
            <MediaPreviewModal
                isOpen={previewModalOpen}
                onClose={() => setPreviewModalOpen(false)}
                url={previewJob?.url}
                type={previewJob?.mediaType}
                title={previewJob?.name}
            />
        </div>
    );
};

export default OriginalVideos;
