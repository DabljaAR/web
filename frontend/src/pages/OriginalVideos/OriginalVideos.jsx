import { useState, useRef } from 'react';
import toast from 'react-hot-toast';
import Swal from 'sweetalert2';
import { useTranslation } from '../../hooks/useTranslation';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import MediaPreviewModal from '../../components/common/MediaPreviewModal';
import { mediaService } from '../../services/mediaService';
import OriginalVideoItem from './OriginalVideoItem';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import { useHistory } from '../../hooks/useHistory';
import { usePageTitle } from '../../hooks/usePageTitle';
import '../../styles/home.css';
import '../../styles/history.css';
import '../../styles/dashboard.css';

const OriginalVideos = () => {
    const { t } = useTranslation();
    usePageTitle('nav.myLibrary');
    const {
        filters,
        setFilters,
        activeMediaTab,
        setActiveMediaTab,
        pagination,
        setPagination,
        historyItems,
        loading,
        error,
        deletingIds,
        fetchHistory
    } = useHistory(5);

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

    const handlePageChange = (newPage) => {
        if (newPage >= 1 && newPage <= pagination.pages) {
            setPagination(prev => ({ ...prev, page: newPage }));
        }
    };

    const handleFilterChange = (e) => {
        const { name, value } = e.target;
        setFilters(prev => ({ ...prev, [name]: value }));
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

    const handlePreview = (item) => {
        setPreviewJob(item);
        setPreviewModalOpen(true);
    };

    const handleDownload = (item) => {
        if (item.url) window.open(item.url, '_blank');
    };

    const handleDelete = async (id) => {
        const result = await Swal.fire({
            title: t('history.confirmDeleteTitle') || 'Are you sure?',
            text: t('history.confirmDeleteText') || "You won't be able to revert this!",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#ff4b2b',
            cancelButtonColor: '#333',
            confirmButtonText: t('history.confirmDeleteBtn') || 'Yes, delete it!'
        });

        if (result.isConfirmed) {
            try {
                deletingIds.current.add(id);
                await mediaService.deleteVideo(id);
                toast.success(t('dashboard.deleteSuccess') || "Deleted successfully.");
                await fetchHistory();
            } catch (err) {
                if (import.meta.env.DEV) console.error("Failed to delete video:", err);
                toast.error(t('dashboard.deleteError') || "Failed to delete video");
            } finally {
                deletingIds.current.delete(id);
            }
        }
    };

    const handleUploadClick = () => {
        fileInputRef.current?.click();
    };

    const handleFileChange = (e) => {
        const file = e.target.files?.[0];
        if (file) setSelectedFile(file);
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
        if (file) setSelectedFile(file);
    };

    const handleStartUpload = async () => {
        if (!selectedFile) return;

        setIsUploading(true);
        setUploadError(null);
        try {
            const formData = new FormData();
            formData.append('file', selectedFile);
            await mediaService.uploadVideo(formData);

            toast.success(t('originalVideos.uploadSuccess') || "Video uploaded successfully.");
            setSelectedFile(null);
            setShowUploadSection(false);
            await fetchHistory(true);
        } catch (err) {
            if (import.meta.env.DEV) console.error("Upload failed:", err);
            setUploadError(err.message || "Failed to start processing.");
        } finally {
            setIsUploading(false);
        }
    };

    const handleYoutubeDownload = async () => {
        if (!youtubeUrl) return;

        setIsYoutubeDownloading(true);
        setYoutubeError(null);
        try {
            await mediaService.downloadFromYoutube({
                youtube_url: youtubeUrl,
                format: youtubeFormat,
                quality: youtubeQuality
            });
            toast.success(t('originalVideos.youtubeSuccess') || 'Video added to processing queue.');
            setYoutubeUrl('');
            setShowYoutubeModal(false);
            setShowUploadSection(false);
            await fetchHistory(true);
        } catch (err) {
            if (import.meta.env.DEV) console.error('YouTube download failed:', err);
            setYoutubeError(err.message || 'Failed to queue YouTube download.');
        } finally {
            setIsYoutubeDownloading(false);
        }
    };

    if (loading) {
        return <LoadingSpinner fullPage size="large" />;
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
                                    onClick={handleUploadClick}
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
                                    onClick={handleStartUpload}
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
                            <select className="filter-select" name="domain" value={filters.domain} onChange={handleFilterChange}>
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
                            <OriginalVideoItem
                                key={item.id}
                                item={item}
                                t={t}
                                onPreview={handlePreview}
                                onDownload={handleDownload}
                                onDelete={handleDelete}
                            />
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
