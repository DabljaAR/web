import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock api module before importing jobService
vi.mock('./api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import api from './api';
import { jobService } from './jobService';

describe('jobService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getJob calls GET /jobs/:id', async () => {
    const mockJob = { id: 'job-1', status: 'QUEUED', progress: 0 };
    api.get.mockResolvedValueOnce(mockJob);

    const result = await jobService.getJob('job-1');
    expect(api.get).toHaveBeenCalledWith('/jobs/job-1');
    expect(result).toEqual(mockJob);
  });

  it('getJobsForVideo calls GET /jobs/video/:videoId', async () => {
    const mockJobs = [{ id: 'job-1', status: 'QUEUED' }];
    api.get.mockResolvedValueOnce(mockJobs);

    const result = await jobService.getJobsForVideo('vid-1');
    expect(api.get).toHaveBeenCalledWith('/jobs/video/vid-1');
    expect(result).toEqual(mockJobs);
  });

  it('listJobs calls GET /jobs/ with query params', async () => {
    api.get.mockResolvedValueOnce([]);

    await jobService.listJobs({ skip: 0, limit: 5 });
    expect(api.get).toHaveBeenCalledWith('/jobs/?skip=0&limit=5');
  });

  it('cancelJob calls POST /jobs/:id/cancel', async () => {
    const cancelled = { id: 'job-1', status: 'CANCELLED' };
    api.post.mockResolvedValueOnce(cancelled);

    const result = await jobService.cancelJob('job-1');
    expect(api.post).toHaveBeenCalledWith('/jobs/job-1/cancel');
    expect(result.status).toBe('CANCELLED');
  });

  it('pollJob resolves when job reaches terminal state', async () => {
    const states = [
      { id: 'j1', status: 'QUEUED', progress: 0 },
      { id: 'j1', status: 'PROCESSING', progress: 50 },
      { id: 'j1', status: 'COMPLETED', progress: 100 },
    ];
    let callIndex = 0;
    api.get.mockImplementation(() => Promise.resolve(states[Math.min(callIndex++, states.length - 1)]));

    const onProgress = vi.fn();
    const result = await jobService.pollJob('j1', { interval: 10, onProgress });

    expect(result.status).toBe('COMPLETED');
    expect(onProgress).toHaveBeenCalled();
  });

  it('pollJob rejects on timeout', async () => {
    api.get.mockImplementation(() =>
      Promise.resolve({ id: 'j1', status: 'PROCESSING', progress: 10 })
    );

    await expect(
      jobService.pollJob('j1', { interval: 10, timeout: 50 })
    ).rejects.toThrow('Job polling timed out');
  });
});
