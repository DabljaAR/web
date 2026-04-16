import { getStorage } from '../utils/authUtils';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

if (!API_BASE_URL) {
  throw new Error('VITE_API_BASE_URL environment variable is required');
}

// Helper function to get auth token (checks both storages)
const getAuthToken = () => {
  const storage = getStorage();
  return storage.getItem('access_token') || localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
};

// Helper function to get refresh token (checks both storages)
const getRefreshToken = () => {
  const storage = getStorage();
  return storage.getItem('refresh_token') || localStorage.getItem('refresh_token') || sessionStorage.getItem('refresh_token');
};

// Helper function to save tokens
const saveTokens = (accessToken, refreshToken) => {
  const storage = getStorage();
  storage.setItem('access_token', accessToken);
  storage.setItem('refresh_token', refreshToken);

  // Also update the other storage if it exists (for migration)
  const otherStorage = storage === localStorage ? sessionStorage : localStorage;
  if (otherStorage.getItem('access_token')) {
    otherStorage.setItem('access_token', accessToken);
    otherStorage.setItem('refresh_token', refreshToken);
  }
};

// Helper function to clear tokens
const clearTokens = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
  localStorage.removeItem('remember_me');
  sessionStorage.removeItem('access_token');
  sessionStorage.removeItem('refresh_token');
  sessionStorage.removeItem('user');
};

// Token refresh function
let isRefreshing = false;
let refreshPromise = null;

const refreshAccessToken = async () => {
  // If already refreshing, return the existing promise
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }

  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const refreshToken = getRefreshToken();
      if (!refreshToken) {
        throw new Error('No refresh token available');
      }

      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        // Refresh token is invalid, clear tokens and logout
        clearTokens();
        throw new Error('Refresh token expired or invalid');
      }

      const data = await response.json();
      saveTokens(data.access_token, data.refresh_token);
      return data.access_token;
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();

  return refreshPromise;
};

const request = async (endpoint, options = {}, isRetry = false) => {
  const { responseType, ...fetchOptions } = options;
  const token = getAuthToken();
  const headers = { ...fetchOptions.headers };

  if (fetchOptions.body instanceof FormData) {
    // Unconditionally delete any Content-Type header when the body is FormData.
    // This allows the browser to set the correct multipart/form-data boundary automatically.
    Object.keys(headers).forEach(key => {
      if (key.toLowerCase() === 'content-type') {
        delete headers[key];
      }
    });
  } else if (!Object.keys(headers).some(key => key.toLowerCase() === 'content-type')) {
    // If not FormData and no Content-Type was provided, default to application/json.
    // This maintains backward compatibility with the previous implementation.
    headers['Content-Type'] = 'application/json';
  }

  // Remove any headers that are explicitly set to undefined
  Object.keys(headers).forEach(key => {
    if (headers[key] === undefined) {
      delete headers[key];
    }
  });

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...fetchOptions,
      headers,
    });

    if (response.status === 401 && !isRetry && getRefreshToken()) {
      try {
        await refreshAccessToken();
        return request(endpoint, options, true);
      } catch (refreshError) {
        clearTokens();
        throw refreshError;
      }
    }

    if (!response.ok) {
      let errorMessage = `API Error: ${response.statusText}`;
      try {
        const errorData = await response.json();
        if (errorData.detail) {
          if (Array.isArray(errorData.detail)) {
            errorMessage = errorData.detail.map(err => {
              const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
              return `${field}: ${err.msg}`;
            }).join(', ');
          } else {
            errorMessage = errorData.detail;
          }
        } else if (errorData.message) {
          errorMessage = errorData.message;
        }
      } catch (e) {}

      const error = new Error(errorMessage);
      error.status = response.status;
      error.response = response;
      throw error;
    }

    if (response.status === 204) {
      return null;
    }

    if (responseType === 'text') {
      return response.text();
    }

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return response.json();
    }
    
    return null;
  } catch (error) {
    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      throw new Error('Network error: the server did not respond. The server may be overloaded or unreachable.');
    }
    throw error;
  }
};

const api = {
  get: (endpoint, options = {}) => request(endpoint, { ...options, method: 'GET' }),
  getText: (endpoint, options = {}) => request(endpoint, { ...options, method: 'GET', responseType: 'text' }),
  post: (endpoint, data, options = {}) => request(endpoint, {
    ...options,
    method: 'POST',
    body: data instanceof FormData ? data : JSON.stringify(data)
  }),
  put: (endpoint, data, options = {}) => request(endpoint, {
    ...options,
    method: 'PUT',
    body: data instanceof FormData ? data : JSON.stringify(data)
  }),
  delete: (endpoint, options = {}) => request(endpoint, { ...options, method: 'DELETE' }),
};

export default api;

