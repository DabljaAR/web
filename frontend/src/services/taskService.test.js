import { describe, it, expect, vi, beforeEach } from 'vitest';
import { taskService } from './taskService';
import api from './api';

vi.mock('./api');

describe('TaskService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts task with output type string', async () => {
    api.post.mockResolvedValueOnce({ id: 'task_1' });

    await taskService.startTask('video_1', 'translationAndTTS');

    expect(api.post).toHaveBeenCalledWith('/videos/video_1/reprocess', {
      output_type: 'translationAndTTS',
    });
  });

  it('starts task with payload object', async () => {
    api.post.mockResolvedValueOnce({ id: 'task_2' });

    await taskService.startTask('video_2', {
      output_type: 'captionsAndTranslation',
      domain: 'education',
    });

    expect(api.post).toHaveBeenCalledWith('/videos/video_2/reprocess', {
      output_type: 'captionsAndTranslation',
      domain: 'education',
    });
  });

  it('forces full dubbing in dedicated GUI request', async () => {
    api.post.mockResolvedValueOnce({ id: 'task_3' });

    await taskService.startFullVideoDubbing('video_3', {
      domain: 'business',
      output_type: 'captionsOnly',
    });

    expect(api.post).toHaveBeenCalledWith('/videos/video_3/reprocess', {
      domain: 'business',
      output_type: 'fullDubbing',
    });
  });
});
