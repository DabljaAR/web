// API endpoints
export const API_ENDPOINTS = {
  AUTH: {
    LOGIN: '/auth/login',
    REGISTER: '/auth/register',
    LOGOUT: '/auth/logout',
    ME: '/auth/me',
  },
  USERS: {
    LIST: '/users',
    DETAIL: '/users/:id',
  },
};

// App constants
export const APP_NAME = 'DabljaAR';
export const APP_VERSION = '1.0.0';

// Local storage keys
export const STORAGE_KEYS = {
  AUTH_TOKEN: 'authToken',
  USER_DATA: 'userData',
  THEME: 'theme',
};

// Route paths
export const ROUTES = {
  HOME: '/',
  ABOUT: '/about',
  LOGIN: '/login',
  DASHBOARD: '/dashboard',
  NOT_FOUND: '*',
};

