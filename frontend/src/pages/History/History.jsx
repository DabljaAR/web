import React, { useState, useMemo, useEffect } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import MediaPreviewModal from '../../components/common/MediaPreviewModal';
import { mediaService } from '../../services/mediaService';
import '../../styles/history.css';

const History = () => {
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

  // Preview Modal State
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewJob, setPreviewJob] = useState(null);
  const [comparisonPreview, setComparisonPreview] = useState(null);

  // Track deleting items
  const deletingIds = React.useRef(new Set());

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

  const formatDate = (dateString, isFullFormat = true) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    if (!isFullFormat) {
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: 'numeric',
        hour12: true
      });
    }
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
      // Reset to page 1 on new search
      if (filters.search !== debouncedSearch) {
        setPagination(prev => ({ ...prev, page: 1 }));
      }
    }, 500);
    return () => clearTimeout(handler);
  }, [filters.search]);

  useEffect(() => {
    const fetchHistory = async (internal = false) => {
      try {
        if (!internal) setLoading(true);
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

        const mappedItems = videos.map(video => {
          const hasActiveJob = Boolean(video.has_active_job);
          const computedStatus = hasActiveJob ? 'processing' : video.status.toLowerCase();
          return {
          id: video.id,
          title: video.title || video.original_filename,
          thumbnail: video.thumbnail_url,
          status: computedStatus,
          domain: video.domain || t('history.domainGeneral') || 'General',
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
          estCompletion: hasActiveJob || video.status === 'PROCESSING' ? (t('history.processing') || 'Calculating...') : '',
          url: video.url,
          audioUrl: video.audio_url,
          mediaType: video.media_type,
          transcriptUrl: video.transcript_url,
          translationUrl: video.translation_url,
          activeJobStatus: video.active_job_status,
          activeJobProgress: video.active_job_progress
        };
      });

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
        console.error("Failed to fetch history:", err);
        if (!internal) setError(t('history.loadError') || 'Failed to load history items.');
        setIsPolling(false);
      } finally {
        if (!internal) setLoading(false);
      }
    };

    fetchHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagination.page, debouncedSearch, filters.sortBy, filters.dateRange, filters.status, activeMediaTab]);

  // Polling Effect (Dashboard Style)
  useEffect(() => {
    let intervalId;
    if (isPolling) {
      intervalId = setInterval(() => {
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
            const mappedItems = videos.map(video => {
              const hasActiveJob = Boolean(video.has_active_job);
              const computedStatus = hasActiveJob ? 'processing' : video.status.toLowerCase();
              return {
              id: video.id,
              title: video.title || video.original_filename,
              thumbnail: video.thumbnail_url,
              status: computedStatus,
              duration: formatDuration(video.duration),
              size: formatSize(video.size_bytes),
              processed: formatDate(video.updated_at),
              started: formatDate(video.created_at),

              createdAt: video.created_at,
              url: video.url,
              audioUrl: video.audio_url,
              mediaType: video.media_type,
              transcriptUrl: video.transcript_url,
              translationUrl: video.translation_url,
              activeJobStatus: video.active_job_status,
              activeJobProgress: video.active_job_progress
            };
          });

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

  const handlePreviewTextComparison = (id) => {
    const item = historyItems.find(i => i.id === id);
    if (!item || !item.transcriptUrl || !item.translationUrl) {
      alert(t('dashboard.noPreviewError') || 'No text preview available.');
      return;
    }

    setComparisonPreview({
      id,
      originalUrl: item.transcriptUrl,
      translatedUrl: item.translationUrl,
      title: item.title
    });
    setPreviewJob({
      mediaType: 'TEXT',
      name: `${item.title} (Original + Translation)`
    });
    setPreviewModalOpen(true);
  };



  const filteredItems = historyItems; // Backend handles filtering now




  // Handle Page Change
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
      alert(t('dashboard.noPreviewError') || "No preview URL available.");
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
      alert(t('dashboard.noPreviewError') || "No download URL available.");
    }
  };

  const handleRedub = (id) => {
    alert(`${t('history.redub')} ${id} (Demo)`);
  };

  const handleDelete = async (id) => {
    if (window.confirm(t('history.deleteConfirm') || "Are you sure you want to delete this item?")) {
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

        // Refresh the list in the background
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
          domain: video.domain || t('history.domainGeneral') || 'General',
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

          estCompletion: video.status === 'PROCESSING' ? 'Calculating...' : '',
          url: video.url,
          audioUrl: video.audio_url,
          mediaType: video.media_type
        }));

        setHistoryItems(mappedItems.filter(item => !deletingIds.current.has(item.id)));
        setPagination(prev => ({ ...prev, total, pages, totalCompleted, totalFailed }));

        alert(t('dashboard.deleteSuccess') || "Deleted successfully.");
      } catch (err) {
        console.error("Failed to delete video:", err);
        alert(t('dashboard.deleteError') || "Failed to delete video");

        deletingIds.current.delete(id);
        // Revert UI if needed by reloading
        window.location.reload();
      } finally {
        setTimeout(() => {
          if (deletingIds.current) deletingIds.current.delete(id);
        }, 10000);
      }
    }
  };

  const handleRetry = (id) => {
    alert(`Retry video ${id} (Demo)`);
  };

  const handleCancelProcessing = (id) => {
    if (window.confirm(t('history.cancelConfirm'))) {
      alert(`Cancel processing video ${id} (Demo)`);
    }
  };

  const getStatusClass = (status) => {
    switch (status) {
      case 'completed':
        return 'status-completed';
      case 'failed':
        return 'status-failed';
      case 'processing':
      case 'pending':
        return 'status-processing';
      default:
        return '';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return '✓';
      case 'failed':
        return '✗';
      case 'processing':
      case 'pending':
        return '⏳';
      default:
        return '';
    }
  };

  const getStatusText = (status) => {
    switch (status) {
      case 'completed':
        return t('history.statusCompleted');
      case 'failed':
        return t('history.statusFailed');
      case 'processing':
      case 'pending':
        return t('history.statusProcessing');
      default:
        return status;
    }
  };

  const stats = {
    total: pagination.total,
    completed: pagination.totalCompleted,
    failed: pagination.totalFailed
  };

  if (loading) {
    return (
      <div className="history-page">
        <BackgroundDecorations />
        <Navbar />
        <div className="main-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
          <div className="loading-spinner" style={{ color: 'white' }}>{t('common.loading') || 'Loading history...'}</div>
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
        {/* Page Header */}
        <div className="page-header">
          <h1 className="page-title">{t('history.title')}</h1>
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

        {/* Filter Section */}
        <div className="filter-section">
          <h3 className="filter-title">{t('history.filterSearch')}</h3>

          {/* Search Box */}
          <div className="search-box">
            <input
              type="text"
              className="search-input"
              placeholder={t('history.searchPlaceholder')}
              name="search"
              value={filters.search}
              onChange={handleFilterChange}
            />
            <span className="search-icon">🔍</span>
          </div>

          {/* Filter Grid */}
          <div className="filter-grid">
            <div className="filter-group">
              <label className="filter-label">{t('history.status')}</label>
              <select
                className="filter-select"
                name="status"
                value={filters.status}
                onChange={handleFilterChange}
              >
                <option value="all">{t('history.statusAll')}</option>
                <option value="completed">{t('history.statusCompleted')}</option>
                <option value="failed">{t('history.statusFailed')}</option>
                <option value="processing">{t('history.statusProcessing')}</option>
              </select>
            </div>

            <div className="filter-group">
              <label className="filter-label">{t('history.domain')}</label>
              <select
                className="filter-select"
                name="domain"
                value={filters.domain}
                onChange={handleFilterChange}
              >
                <option value="all">{t('history.domainAll')}</option>
                <option value="general">{t('history.domainGeneral')}</option>
                <option value="technical">{t('history.domainTechnical')}</option>
                <option value="medical">{t('history.domainMedical')}</option>
                <option value="legal">{t('history.domainLegal')}</option>
                <option value="education">{t('history.domainEducation')}</option>
              </select>
            </div>

            <div className="filter-group">
              <label className="filter-label">{t('history.dateRange')}</label>
              <select
                className="filter-select"
                name="dateRange"
                value={filters.dateRange}
                onChange={handleFilterChange}
              >
                <option value="last30Days">{t('history.last30Days')}</option>
                <option value="last7Days">{t('history.last7Days')}</option>
                <option value="last90Days">{t('history.last90Days')}</option>
                <option value="allTime">{t('history.allTime')}</option>
              </select>
            </div>

            <div className="filter-group">
              <label className="filter-label">{t('history.sortBy')}</label>
              <select
                className="filter-select"
                name="sortBy"
                value={filters.sortBy}
                onChange={handleFilterChange}
              >
                <option value="dateNewest">{t('history.dateNewest')}</option>
                <option value="dateOldest">{t('history.dateOldest')}</option>
                <option value="nameAZ">{t('history.nameAZ')}</option>
                <option value="nameZA">{t('history.nameZA')}</option>
              </select>
            </div>

            <div className="filter-group" style={{ display: 'flex', alignItems: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={handleResetFilters}
                style={{ height: '42px' }}
              >
                {t('history.resetFilters', 'Reset Filters')}
              </button>
            </div>
          </div>
        </div>

        {/* Stats Bar */}
        <div className="stats-bar">
          <div className="stat-item">
            <span className="stat-label">{t('history.total')}</span>
            <span className="stat-value">{stats.total}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">{t('history.completed')}</span>
            <span className="stat-value">{stats.completed}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">{t('history.failed')}</span>
            <span className="stat-value">{stats.failed}</span>
          </div>
        </div>

        {/* History List */}
        <div className="history-list">
          {filteredItems.length === 0 ? (
            <div className="no-items" style={{ textAlign: 'center', padding: '2rem', color: 'rgba(255,255,255,0.6)' }}>
              {error ? error : t('history.noItems', 'No history items found.')}
            </div>
          ) : (
            filteredItems.map((item) => (
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
            ))
          )}
        </div>

        {/* Pagination */}
        {pagination.pages > 1 && (
          <div className="pagination">
            <button
              className="page-btn"
              disabled={pagination.page === 1}
              onClick={() => handlePageChange(pagination.page - 1)}
            >
              &lt;
            </button>

            {[...Array(pagination.pages)].map((_, i) => {
              const pageNum = i + 1;
              // Show first, last, current, and surrounding pages
              if (
                pageNum === 1 ||
                pageNum === pagination.pages ||
                (pageNum >= pagination.page - 1 && pageNum <= pagination.page + 1)
              ) {
                return (
                  <button
                    key={pageNum}
                    className={`page-btn ${pagination.page === pageNum ? 'active' : ''}`}
                    onClick={() => handlePageChange(pageNum)}
                  >
                    {pageNum}
                  </button>
                );
              } else if (
                pageNum === pagination.page - 2 ||
                pageNum === pagination.page + 2
              ) {
                return <span key={pageNum} className="page-dots">...</span>;
              }
              return null;
            })}

            <button
              className="page-btn"
              disabled={pagination.page === pagination.pages}
              onClick={() => handlePageChange(pagination.page + 1)}
            >
              &gt;
            </button>
          </div>
        )}
      </div>
      <Footer />

      {/* Preview Modal */}
      <MediaPreviewModal
        isOpen={previewModalOpen}
        onClose={() => {
          setPreviewModalOpen(false);
          setComparisonPreview(null);
        }}
        url={comparisonPreview?.originalUrl || previewJob?.url}
        secondaryUrl={comparisonPreview?.translatedUrl}
        secondaryTitle={t('dashboard.previewTranslation') || 'Translation'}
        primaryTitle={t('dashboard.previewTranscript') || 'Original Transcript'}
        type={previewJob?.mediaType}
        title={previewJob?.name}
      />
    </div >
  );
};

export default History;

