import api from './api';

export const taskService = {
  /** List all VideoTasks for a given video, newest first. */
  getTasksForVideo: (videoId) => api.get(`/tasks/video/${videoId}`),

  /** Get a single VideoTask with full output (transcript, segments, etc.). */
  getTask: (taskId) => api.get(`/tasks/${taskId}`),

  /** Re-run the pipeline on an existing video with a chosen output_type. */
  startTask: (videoId, outputType) =>
    api.post(`/media/${videoId}/reprocess`, { output_type: outputType }),
};

export default taskService;
