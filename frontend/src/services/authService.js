import api from './api';

export const authService = {
  login: async (email, password) => {
    return api.post('/auth/login', { email, password });
  },

  register: async (userData) => {
    return api.post('/auth/register', userData);
  },

  logout: async () => {
    return api.post('/auth/logout');
  },

  getCurrentUser: async () => {
    return api.get('/auth/me');
  },

  refreshToken: async () => {
    return api.post('/auth/refresh');
  },
};

