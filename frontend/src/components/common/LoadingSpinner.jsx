import React from 'react';
import PropTypes from 'prop-types';
import './LoadingSpinner.css';

const LoadingSpinner = ({ fullPage = false, size = 'medium', color = 'primary' }) => {
  const spinnerClass = `spinner ${size} ${color}`;

  if (fullPage) {
    return (
      <div className="full-page-spinner" role="status" aria-live="polite" aria-label="Loading content...">
        <div className={spinnerClass}></div>
      </div>
    );
  }

  return (
    <div className="spinner-container" role="status" aria-live="polite" aria-label="Loading...">
      <div className={spinnerClass}></div>
    </div>
  );
};

LoadingSpinner.propTypes = {
  fullPage: PropTypes.bool,
  size: PropTypes.oneOf(['small', 'medium', 'large']),
  color: PropTypes.oneOf(['primary', 'white', 'secondary']),
};

export default LoadingSpinner;
