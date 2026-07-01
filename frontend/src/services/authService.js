import api from './api';

export const authService = {
  login: async (username, password) => {
    // Backend accepts username or email in the username field
    return api.post('/login', { username, password });
  },

  register: async (userData) => {
    return api.post('/signup', userData);
  },

  logout: async () => {
    return api.post('/auth/logout');
  },

  getCurrentUser: async () => {
    return api.get('/auth/me');
  },

  refreshToken: async (refreshToken) => {
    return api.post('/auth/refresh', { refresh_token: refreshToken });
  },
  updateUser: async (userId, userData) => {
    return api.put(`/users/${userId}`, userData);
  },

  googleAuth: async (credential) => {
    return api.post('/auth/google', { credential });
  },
};

