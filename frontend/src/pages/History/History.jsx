import React, { useState } from 'react';
import toast from 'react-hot-toast';
import Swal from 'sweetalert2';
import { useTranslation } from '../../hooks/useTranslation';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import MediaPreviewModal from '../../components/common/MediaPreviewModal';
import VideoTasksModal from '../../components/common/VideoTasksModal';
import RedubModal from '../../components/common/RedubModal';
import { mediaService } from '../../services/mediaService';
import taskService from '../../services/taskService';
import HistoryItem from './HistoryItem';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import { useHistory } from '../../hooks/useHistory';
import { usePageTitle } from '../../hooks/usePageTitle';
import '../../styles/home.css';
import '../../styles/history.css';

const History = () => {
  const { t } = useTranslation();
  usePageTitle('nav.history');
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
  const [comparisonPreview, setComparisonPreview] = useState(null);

  // Tasks Modal State
  const [tasksModalOpen, setTasksModalOpen] = useState(false);
  const [tasksModalVideo, setTasksModalVideo] = useState(null);

  // Redub Modal State
  const [redubModalOpen, setRedubModalOpen] = useState(false);
  const [redubModalVideo, setRedubModalVideo] = useState(null);

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
    if (item && item.url) {
      setComparisonPreview(null);
      setPreviewJob({ ...item, name: item.name });
      setPreviewModalOpen(true);
    } else {
      toast.error(t('dashboard.noPreviewError') || "No preview URL available.");
    }
  };

  const handleDownload = (item) => {
    if (item && item.url) {
      const link = document.createElement('a');
      link.href = item.url;
      link.download = item.name || 'download';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else {
      toast.error(t('dashboard.noPreviewError') || "No download URL available.");
    }
  };

  const handleViewTasks = (id, name) => {
    setTasksModalVideo({ id, title: name });
    setTasksModalOpen(true);
  };

  const handleRedub = (id, name) => {
    setRedubModalVideo({ id, title: name });
    setRedubModalOpen(true);
  };

  const handleRedubSubmit = async (videoId, outputType) => {
    await taskService.startTask(videoId, outputType);
  };

  const handlePreviewTranscript = (item) => {
    setComparisonPreview(null);
    setPreviewJob({ url: item.transcriptUrl, mediaType: 'TEXT', name: `${item.name} (Transcript)` });
    setPreviewModalOpen(true);
  };

  const handlePreviewTranslation = (item) => {
    setComparisonPreview(null);
    setPreviewJob({ url: item.translationUrl, mediaType: 'TEXT', name: `${item.name} (Translation)` });
    setPreviewModalOpen(true);
  };

  const handleDelete = async (id) => {
    const confirmResult = await Swal.fire({
      title: t('common.warning') || 'Are you sure?',
      text: t('history.deleteConfirm') || "Are you sure you want to delete this item?",
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#d33',
      cancelButtonColor: '#3085d6',
      confirmButtonText: t('common.delete') || 'Yes, delete it!'
    });

    if (confirmResult.isConfirmed) {
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

  const stats = {
    total: pagination.total,
    completed: pagination.totalCompleted,
    failed: pagination.totalFailed
  };

  if (loading) {
    return <LoadingSpinner fullPage size="large" />;
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
          </div>

          <div style={{ display: 'flex', marginTop: '12px' }}>
            <button
              className="btn btn-secondary"
              onClick={handleResetFilters}
              style={{ height: '42px', marginInlineEnd: 'auto' }}
            >
              {t('history.resetFilters', 'Reset Filters')}
            </button>
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
          {historyItems.length === 0 ? (
            <div className="no-items" style={{ textAlign: 'center', padding: '2rem', color: 'rgba(255,255,255,0.6)' }}>
              {error ? error : t('history.noItems', 'No history items found.')}
            </div>
          ) : (
            historyItems.map((item) => (
              <HistoryItem
                key={item.id}
                item={item}
                t={t}
                onPreview={handlePreview}
                onDownload={handleDownload}
                onDelete={handleDelete}
                onViewTasks={handleViewTasks}
                onRedub={handleRedub}
                onPreviewTranscript={handlePreviewTranscript}
                onPreviewTranslation={handlePreviewTranslation}
              />
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

      {/* Tasks Modal */}
      <VideoTasksModal
        isOpen={tasksModalOpen}
        onClose={() => {
          setTasksModalOpen(false);
          setTasksModalVideo(null);
        }}
        videoId={tasksModalVideo?.id}
        videoTitle={tasksModalVideo?.title}
      />

      {/* Redub Modal */}
      <RedubModal
        isOpen={redubModalOpen}
        onClose={() => {
          setRedubModalOpen(false);
          setRedubModalVideo(null);
        }}
        videoId={redubModalVideo?.id}
        videoTitle={redubModalVideo?.title}
        onSubmit={handleRedubSubmit}
      />
    </div>
  );
};

export default History;
