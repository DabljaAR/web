import React from 'react';
import PropTypes from 'prop-types';

const HistoryFilterBar = ({ filters, setFilters, activeMediaTab, setActiveMediaTab, t }) => {
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFilters(prev => ({ ...prev, [name]: value }));
  };

  return (
    <>
      <div className="history-tabs">
        <button
          className={`history-tab ${activeMediaTab === 'all' ? 'active' : ''}`}
          onClick={() => setActiveMediaTab('all')}
        >
          {t('history.tabAll')}
        </button>
        <button
          className={`history-tab ${activeMediaTab === 'video' ? 'active' : ''}`}
          onClick={() => setActiveMediaTab('video')}
        >
          {t('history.tabVideos')}
        </button>
        <button
          className={`history-tab ${activeMediaTab === 'audio' ? 'active' : ''}`}
          onClick={() => setActiveMediaTab('audio')}
        >
          {t('history.tabAudio')}
        </button>
        <button
          className={`history-tab ${activeMediaTab === 'text' ? 'active' : ''}`}
          onClick={() => setActiveMediaTab('text')}
        >
          {t('history.tabText')}
        </button>
      </div>

      <div className="filter-bar">
        <div className="search-group">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            name="search"
            value={filters.search}
            onChange={handleInputChange}
            placeholder={t('history.searchPlaceholder')}
            className="search-input"
          />
        </div>

        <div className="filters-row">
          <select
            name="status"
            value={filters.status}
            onChange={handleInputChange}
            className="filter-select"
          >
            <option value="all">{t('history.filterStatusAll')}</option>
            <option value="completed">{t('history.filterStatusCompleted')}</option>
            <option value="processing">{t('history.filterStatusProcessing')}</option>
            <option value="failed">{t('history.filterStatusFailed')}</option>
          </select>

          <select
            name="dateRange"
            value={filters.dateRange}
            onChange={handleInputChange}
            className="filter-select"
          >
            <option value="all">{t('history.filterDateAll')}</option>
            <option value="today">{t('history.filterDateToday')}</option>
            <option value="yesterday">{t('history.filterDateYesterday')}</option>
            <option value="last7Days">{t('history.filterDateLast7Days')}</option>
            <option value="last30Days">{t('history.filterDateLast30Days')}</option>
          </select>

          <select
            name="sortBy"
            value={filters.sortBy}
            onChange={handleInputChange}
            className="filter-select"
          >
            <option value="dateNewest">{t('history.sortNewest')}</option>
            <option value="dateOldest">{t('history.sortOldest')}</option>
            <option value="nameAZ">{t('history.sortNameAZ')}</option>
            <option value="nameZA">{t('history.sortNameZA')}</option>
          </select>
        </div>
      </div>
    </>
  );
};

HistoryFilterBar.propTypes = {
  filters: PropTypes.object.isRequired,
  setFilters: PropTypes.func.isRequired,
  activeMediaTab: PropTypes.string.isRequired,
  setActiveMediaTab: PropTypes.func.isRequired,
  t: PropTypes.func.isRequired,
};

export default HistoryFilterBar;
