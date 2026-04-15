import api from './api';

export const taskService = {
  /** List all VideoTasks for a given video, newest first. */
  getTasksForVideo: (videoId) => api.get(`/tasks/video/${videoId}`),

  /** Get a single VideoTask with full output (transcript, segments, etc.). */
  getTask: (taskId) => api.get(`/tasks/${taskId}`),

  /** Re-run the pipeline on an existing video with a chosen output_type. */
  startTask: (videoId, outputTypeOrPayload) => {
    const payload =
      typeof outputTypeOrPayload === 'string'
        ? { output_type: outputTypeOrPayload }
        : (outputTypeOrPayload || {});

    return api.post(`/videos/${videoId}/reprocess`, payload);
  },

  /** Explicit GUI path for full video dubbing requests. */
  startFullVideoDubbing: (videoId, payload = {}) => {
    return api.post(`/videos/${videoId}/reprocess`, {
      ...payload,
      output_type: 'fullDubbing',
    });
  },
};

export default taskService;
