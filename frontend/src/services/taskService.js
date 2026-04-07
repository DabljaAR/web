import api from './api';

export const taskService = {
  /** List all VideoTasks for a given video, newest first. */
  getTasksForVideo: (videoId) => api.get(`/tasks/video/${videoId}`),

  /** Get a single VideoTask with full output (transcript, segments, etc.). */
  getTask: (taskId) => api.get(`/tasks/${taskId}`),
};

export default taskService;
