import api from '../../../services/api';

export const dashboardService = {
  getStats: async () => {
    return api.get('/dashboard/stats');
  },

  getRecentActivity: async () => {
    return api.get('/dashboard/activity');
  },
};

