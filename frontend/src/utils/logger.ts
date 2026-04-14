/**
 * Centralised logger utility.
 *
 * In development  → full output to the browser console.
 * In production   → only errors are logged (no debug noise).
 *                   Replace the `reportError` body with a real monitoring
 *                   service call (Sentry, Datadog, etc.) when available.
 *
 * Usage:
 *   import logger from '../utils/logger';
 *   logger.error('Something broke', error);
 *   logger.warn('Missing key', key);
 *   logger.info('User logged in');
 *   logger.debug('State snapshot', state);  // DEV only
 */

const IS_DEV = import.meta.env.DEV;

/**
 * Send an error report to a monitoring service.
 * Swap this body for `Sentry.captureException(error, { extra: context })`
 * once Sentry (or equivalent) is configured.
 */
function reportError(error: Error, context?: unknown): void {
  // TODO: replace with Sentry.captureException(error, { extra: context })
  // For now, always log errors to the console so nothing is silently swallowed.
  console.error('[ErrorReport]', error, context ?? '');
}

const logger = {
  /**
   * Log an error. Always outputs — both dev and production.
   * In production this should also forward to a monitoring service.
   */
  error(message: string | Error, ...args: unknown[]): void {
    if (IS_DEV) {
      console.error(`[ERROR] ${message}`, ...args);
    } else {
      reportError(message instanceof Error ? message : new Error(String(message)), args[0]);
    }
  },

  /**
   * Log a warning. Dev only.
   */
  warn(message: string, ...args: unknown[]): void {
    if (IS_DEV) {
      console.warn(`[WARN] ${message}`, ...args);
    }
  },

  /**
   * Log general info. Dev only.
   */
  info(message: string, ...args: unknown[]): void {
    if (IS_DEV) {
      console.info(`[INFO] ${message}`, ...args);
    }
  },

  /**
   * Log debug output. Dev only.
   */
  debug(message: string, ...args: unknown[]): void {
    if (IS_DEV) {
      console.log(`[DEBUG] ${message}`, ...args);
    }
  },
};

export default logger;
