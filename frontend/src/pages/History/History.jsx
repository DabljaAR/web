import React, { useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import '../../styles/history.css';

const History = () => {
  const { t } = useTranslation();
  const [filters, setFilters] = useState({
    search: '',
    status: 'all',
    domain: 'all',
    dateRange: 'last30Days',
    sortBy: 'dateNewest'
  });

  const [historyItems] = useState([
    {
      id: 1,
      title: 'Tech_Tutorial_2024.mp4',
      status: 'completed',
      domain: 'Technical',
      style: 'Neutral',
      voice: 'Male Voice 1',
      duration: '15:30',
      size: '145 MB',
      processed: 'Nov 20, 2025 at 2:30 PM',
      creditsUsed: 5
    },
    {
      id: 2,
      title: 'Medical_Lecture_Nov.mp4',
      status: 'completed',
      domain: 'Medical',
      style: 'Formal',
      voice: 'Female Voice 2',
      duration: '45:20',
      size: '520 MB',
      processed: 'Nov 19, 2025 at 10:15 AM',
      creditsUsed: 8
    },
    {
      id: 3,
      title: 'Large_Video_Test.mp4',
      status: 'failed',
      domain: 'General',
      style: 'Neutral',
      voice: 'Male Voice 1',
      error: 'File size exceeded limit',
      attempted: 'Nov 18, 2025 at 3:45 PM'
    },
    {
      id: 4,
      title: 'New_Tutorial.mp4',
      status: 'processing',
      domain: 'Technical',
      style: 'Neutral',
      voice: 'Male Voice 1',
      progress: 67,
      started: 'Nov 23, 2025 at 11:20 AM',
      estCompletion: '1 minute'
    }
  ]);

  const handleFilterChange = (e) => {
    const { name, value } = e.target;
    setFilters(prev => ({
      ...prev,
      [name]: value
    }));
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

  const handleDelete = (id) => {
    if (window.confirm(t('history.deleteConfirm'))) {
      alert(`Delete video ${id} (Demo)`);
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
        return t('history.statusProcessing');
      default:
        return '';
    }
  };

  const stats = {
    total: 47,
    completed: 45,
    failed: 2
  };

  return (
    <div className="history-page">
      <BackgroundDecorations />
      <Navbar />
      
      <div className="main-container">
        {/* Page Header */}
        <div className="page-header">
          <h1 className="page-title">{t('history.title')}</h1>
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
          {historyItems.map((item) => (
            <div key={item.id} className="history-item">
              <div className="item-content">
                <div className="item-thumbnail">📹</div>
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

                  {item.status === 'processing' && (
                    <>
                      <div className="progress-bar">
                        <div className="progress-fill" style={{width: `${item.progress}%`}}></div>
                      </div>
                      <div className="progress-text">
                        <span>{t('history.processing')} {item.progress}%</span> |{' '}
                        <span>{t('history.estCompletion')}</span> {item.estCompletion}
                      </div>
                    </>
                  )}

                  {item.status !== 'processing' && item.status !== 'failed' && (
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
                    {item.status === 'processing' && (
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
                        <button
                          className="btn btn-secondary"
                          onClick={() => handleRedub(item.id)}
                        >
                          <span>🔄</span>
                          <span>{t('history.redub')}</span>
                        </button>
                        <button
                          className="btn btn-danger btn-icon"
                          onClick={() => handleDelete(item.id)}
                        >
                          🗑
                        </button>
                      </>
                    )}
                    {item.status === 'failed' && (
                      <>
                        <button
                          className="btn btn-primary"
                          onClick={() => handleRetry(item.id)}
                        >
                          <span>🔄</span>
                          <span>{t('history.retry')}</span>
                        </button>
                        <button
                          className="btn btn-secondary"
                          onClick={() => handlePreview(item.id)}
                        >
                          <span>ℹ</span>
                          <span>{t('history.details')}</span>
                        </button>
                      </>
                    )}
                    {item.status === 'processing' && (
                      <button
                        className="btn btn-danger"
                        onClick={() => handleCancelProcessing(item.id)}
                      >
                        <span>❌</span>
                        <span>{t('history.cancelProcessing')}</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Pagination */}
        <div className="pagination">
          <button className="page-btn active">1</button>
          <button className="page-btn">2</button>
          <button className="page-btn">3</button>
          <button className="page-btn">...</button>
          <button className="page-btn">10</button>
        </div>
      </div>
      <Footer />
    </div>
  );
};

export default History;

