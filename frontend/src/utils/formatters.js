/**
 * Format a date string into a human-readable format
 * @param {string} dateString - The date string to format
 * @param {string} locale - The locale to use for formatting
 * @returns {string} Formatted date string
 */
export const formatDate = (dateString, locale = 'en-US') => {
  if (!dateString) return '—';
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '—';
    return date.toLocaleDateString(locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  } catch (error) {
    return '—';
  }
};

/**
 * Format a date string into a numeric date (e.g. 4/18/2026 in en-US)
 * @param {string} dateString - The date string to format
 * @param {string} locale - The locale to use for formatting
 * @returns {string} Formatted numeric date string
 */
export const formatDateNumeric = (dateString, locale = 'en-US') => {
  if (!dateString) return '—';
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '—';
    return date.toLocaleDateString(locale, {
      year: 'numeric',
      month: 'numeric',
      day: 'numeric'
    });
  } catch (error) {
    return '—';
  }
};

/**
 * Format a date string into a long day-month-year (e.g. "18 أبريل 2026" for Arabic).
 * @param {string} dateString - The date string to format
 * @param {string} locale - The locale to use for formatting
 * @returns {string} Formatted long date string
 */
export const formatDateLongDMY = (dateString, locale = 'en-US') => {
  if (!dateString) return '—';
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '—';
    return date.toLocaleDateString(locale, {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  } catch (error) {
    return '—';
  }
};

/**
 * Format duration in seconds into MM:SS format
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted duration string
 */
export const formatDuration = (seconds) => {
  if (typeof seconds !== 'number' || isNaN(seconds)) return '—';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

/**
 * Format bytes into human-readable size string
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted size string
 */
export const formatSize = (bytes) => {
  if (!bytes || typeof bytes !== 'number' || isNaN(bytes)) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
};
