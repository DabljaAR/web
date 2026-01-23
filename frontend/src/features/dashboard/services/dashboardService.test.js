import { describe, it, expect, vi, beforeEach } from 'vitest';
import { dashboardService } from './dashboardService';
import api from '../../../services/api';

// Mock the api module
vi.mock('../../../services/api');

describe('DashboardService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getStats', () => {
    it('calls api.get with correct endpoint', async () => {
      const mockStats = {
        totalUsers: 1000,
        totalRevenue: 50000,
        activeProjects: 25,
        completionRate: 85,
      };

      api.get.mockResolvedValueOnce(mockStats);

      const result = await dashboardService.getStats();

      expect(api.get).toHaveBeenCalledWith('/dashboard/stats');
      expect(result).toEqual(mockStats);
    });

    it('handles errors', async () => {
      const error = new Error('Failed to fetch stats');
      api.get.mockRejectedValueOnce(error);

      await expect(dashboardService.getStats()).rejects.toThrow();
    });
  });

  describe('getRecentActivity', () => {
    it('calls api.get with correct endpoint', async () => {
      const mockActivity = [
        { id: 1, action: 'Created project', timestamp: '2024-01-01' },
        { id: 2, action: 'Updated profile', timestamp: '2024-01-02' },
      ];

      api.get.mockResolvedValueOnce(mockActivity);

      const result = await dashboardService.getRecentActivity();

      expect(api.get).toHaveBeenCalledWith('/dashboard/activity');
      expect(result).toEqual(mockActivity);
    });

    it('handles errors', async () => {
      const error = new Error('Failed to fetch activity');
      api.get.mockRejectedValueOnce(error);

      await expect(dashboardService.getRecentActivity()).rejects.toThrow();
    });
  });
});



