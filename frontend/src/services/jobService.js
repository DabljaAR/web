import api from './api';

/**
 * Job Service — frontend layer for the /api/jobs endpoints.
 * Provides polling, status queries, and cancellation.
 */
export const jobService = {
  /**
   * Get a single job by ID.
   * @param {string} jobId - UUID of the job
   * @returns {Promise<Object>} Job object
   */
  getJob: async (jobId) => {
    return api.get(`/jobs/${jobId}`);
  },

  /**
   * List all jobs for a specific video.
   * @param {string} videoId - UUID of the video
   * @returns {Promise<Array>} Array of job objects
   */
  getJobsForVideo: async (videoId) => {
    return api.get(`/jobs/video/${videoId}`);
  },

  /**
   * List jobs for the current user.
   * @param {Object} params - { skip, limit }
   * @returns {Promise<Array>} Array of job objects
   */
  listJobs: async (params = {}) => {
    const queryParams = new URLSearchParams();
    if (params.skip !== undefined) queryParams.append('skip', params.skip);
    if (params.limit !== undefined) queryParams.append('limit', params.limit);
    if (params.user_id !== undefined) queryParams.append('user_id', params.user_id);
    const qs = queryParams.toString();
    return api.get(`/jobs/${qs ? `?${qs}` : ''}`);
  },

  /**
   * Cancel a queued or processing job.
   * @param {string} jobId - UUID of the job
   * @returns {Promise<Object>} Updated job object
   */
  cancelJob: async (jobId) => {
    return api.post(`/jobs/${jobId}/cancel`);
  },

  /**
   * Poll a job until it reaches a terminal state.
   * Calls onProgress on each poll. Returns the final job object.
   *
   * @param {string} jobId - UUID of the job
   * @param {Object} options
   * @param {number} options.interval - Polling interval in ms (default 2000)
   * @param {number} options.timeout  - Max polling time in ms (default 600000 = 10 min)
   * @param {Function} options.onProgress - Callback(job) on each poll
   * @returns {Promise<Object>} Final job object
   */
  pollJob: async (jobId, { interval = 2000, timeout = 600000, onProgress } = {}) => {
    const TERMINAL_STATES = ['COMPLETED', 'FAILED', 'CANCELLED'];
    const start = Date.now();

    return new Promise((resolve, reject) => {
      const poll = async () => {
        try {
          if (Date.now() - start > timeout) {
            return reject(new Error('Job polling timed out'));
          }
          const job = await jobService.getJob(jobId);
          if (onProgress) onProgress(job);

          if (TERMINAL_STATES.includes(job.status)) {
            return resolve(job);
          }
          setTimeout(poll, interval);
        } catch (err) {
          reject(err);
        }
      };
      poll();
    });
  },
};

export default jobService;
