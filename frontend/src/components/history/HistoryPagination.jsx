import React from 'react';
import PropTypes from 'prop-types';

const HistoryPagination = ({ pagination, setPagination, t }) => {
  const { page, pages, total } = pagination;

  if (total === 0) return null;

  return (
    <div className="pagination">
      <div className="pagination-info">
        {t('history.showing')} {Math.min(total, (page - 1) * pagination.limit + 1)}-{Math.min(total, page * pagination.limit)} {t('history.of')} {total}
      </div>
      <div className="pagination-controls">
        <button
          className="pagination-btn"
          disabled={page <= 1}
          onClick={() => setPagination(prev => ({ ...prev, page: prev.page - 1 }))}
        >
          {t('history.prev')}
        </button>
        {[...Array(pages)].map((_, i) => (
          <button
            key={i + 1}
            className={`pagination-btn ${page === i + 1 ? 'active' : ''}`}
            onClick={() => setPagination(prev => ({ ...prev, page: i + 1 }))}
          >
            {i + 1}
          </button>
        ))}
        <button
          className="pagination-btn"
          disabled={page >= pages}
          onClick={() => setPagination(prev => ({ ...prev, page: prev.page + 1 }))}
        >
          {t('history.next')}
        </button>
      </div>
    </div>
  );
};

HistoryPagination.propTypes = {
  pagination: PropTypes.shape({
    page: PropTypes.number.isRequired,
    pages: PropTypes.number.isRequired,
    total: PropTypes.number.isRequired,
    limit: PropTypes.number.isRequired,
  }).isRequired,
  setPagination: PropTypes.func.isRequired,
  t: PropTypes.func.isRequired,
};

export default HistoryPagination;
