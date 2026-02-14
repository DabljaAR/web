import React, { useState, useEffect } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import { mediaService } from '../../services/mediaService';
import '../../styles/history.css';

const OriginalVideos = () => {
    const { t } = useTranslation();
    const [filters, setFilters] = useState({
        search: '',
        status: 'all',
        domain: 'all',
        dateRange: 'last30Days',
        sortBy: 'dateNewest'
    });

    const [pagination, setPagination] = useState({
        page: 1,
        limit: 5,
        total: 0,
        pages: 1,
        totalCompleted: 0,
        totalFailed: 0
    });

    const [historyItems, setHistoryItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [debouncedSearch, setDebouncedSearch] = useState(filters.search);

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
        const fetchHistory = async () => {
            try {
                setLoading(true);
                // Specifically filter for VIDEO media type
                const data = await mediaService.getVideos({
                    page: pagination.page,
                    limit: pagination.limit,
                    search: debouncedSearch,
                    sortBy: filters.sortBy,
                    dateRange: filters.dateRange,
                    status: filters.status,
                    mediaType: 'VIDEO'
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
                    domain: 'General',
                    style: 'Neutral',
                    voice: 'Male Voice 1',
                    duration: formatDuration(video.duration),
                    size: formatSize(video.size_bytes),
                    processed: formatDate(video.updated_at),
                    started: formatDate(video.created_at),
                    attempted: formatDate(video.created_at),
                    rawDate: video.created_at,
                    creditsUsed: 0,
                    error: video.error_message,
                    progress: video.status === 'PROCESSING' ? 50 : (video.status === 'PENDING' ? 0 : 100),
                    estCompletion: video.status === 'PROCESSING' ? 'Calculating...' : ''
                }));

                setHistoryItems(mappedItems);
                setPagination(prev => ({
                    ...prev,
                    total: total,
                    pages: pages,
                    totalCompleted: totalCompleted,
                    totalFailed: totalFailed
                }));
                setError(null);
            } catch (err) {
                console.error("Failed to fetch original videos:", err);
                setError('Failed to load original videos.');
            } finally {
                setLoading(false);
            }
        };

        fetchHistory();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [pagination.page, debouncedSearch, filters.sortBy, filters.dateRange, filters.status]);

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
            sortBy: 'dateNewest'
        });
        setPagination(prev => ({ ...prev, page: 1 }));
    };

    const handlePreview = (id) => {
        alert(`Preview video ${id} (Demo)`);
    };

    const handleDownload = (id) => {
        alert(`Download video ${id} (Demo)`);
    };

    const handleRedub = (id) => {
        alert(`Re-dub video ${id} (Demo)`);
    };

    const handleDelete = async (id) => {
        if (window.confirm(t('originalVideos.deleteConfirm'))) {
            try {
                await mediaService.deleteVideo(id);
                const data = await mediaService.getVideos({
                    page: pagination.page,
                    limit: pagination.limit,
                    search: debouncedSearch,
                    sortBy: filters.sortBy,
                    dateRange: filters.dateRange,
                    status: filters.status,
                    mediaType: 'VIDEO'
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
                    progress: video.status === 'PROCESSING' ? 50 : (video.status === 'PENDING' ? 0 : 100),
                }));
                setHistoryItems(mappedItems);
                setPagination(prev => ({
                    ...prev,
                    total: data.total || 0,
                    pages: data.pages || 1,
                    totalCompleted: data.total_completed || 0,
                    totalFailed: data.total_failed || 0
                }));
            } catch (err) {
                console.error("Failed to delete video:", err);
                alert("Failed to delete video");
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
                    <div className="loading-spinner" style={{ color: 'white' }}>Loading original videos...</div>
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
                <div className="page-header">
                    <h1 className="page-title">{t('originalVideos.title')}</h1>
                </div>

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

                        <div className="filter-group" style={{ display: 'flex', alignItems: 'flex-end' }}>
                            <button className="btn btn-secondary" onClick={handleResetFilters} style={{ height: '42px' }}>
                                {t('originalVideos.resetFilters')}
                            </button>
                        </div>
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
                                            '📹'
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

                                        {(item.status === 'processing' || item.status === 'pending') && (
                                            <div className="progress-bar">
                                                <div className="progress-fill" style={{ width: `${item.progress}%` }}></div>
                                            </div>
                                        )}

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
                                            <button className="btn btn-secondary" onClick={() => handlePreview(item.id)}>
                                                <span>👁</span> {t('originalVideos.preview')}
                                            </button>
                                            <button className="btn btn-secondary" onClick={() => handleDownload(item.id)}>
                                                <span>⬇</span> {t('originalVideos.download')}
                                            </button>
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
        </div>
    );
};

export default OriginalVideos;
