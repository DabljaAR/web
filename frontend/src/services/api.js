import { getStorage } from '../utils/authUtils';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

if (!API_BASE_URL) {
  throw new Error('VITE_API_BASE_URL environment variable is required');
}

// Helper function to get auth token.
// Access tokens should remain session-scoped (avoid localStorage persistence where possible).
const getAuthToken = () => {
  const token = sessionStorage.getItem('access_token') || getStorage().getItem('access_token');
  if (token) return token;

  // Legacy migration: if an old persisted access_token exists, move it into the session.
  if (localStorage.getItem('remember_me') === 'true') {
    const legacy = localStorage.getItem('access_token');
    if (legacy) {
      sessionStorage.setItem('access_token', legacy);
      localStorage.removeItem('access_token');
      return legacy;
    }
  }

  return null;
};

// Helper function to get refresh token.
// If remember-me is enabled, refresh_token may be persisted in localStorage.
const getRefreshToken = () => {
  const sessionToken = sessionStorage.getItem('refresh_token') || getStorage().getItem('refresh_token');
  if (sessionToken) return sessionToken;

  if (localStorage.getItem('remember_me') === 'true') {
    return localStorage.getItem('refresh_token');
  }

  return null;
};

// Helper function to save tokens
// - access_token: sessionStorage only
// - refresh_token: sessionStorage, and localStorage when remember_me is true
const saveTokens = (accessToken, refreshToken) => {
  sessionStorage.setItem('access_token', accessToken);
  sessionStorage.setItem('refresh_token', refreshToken);

  if (localStorage.getItem('remember_me') === 'true') {
    localStorage.setItem('refresh_token', refreshToken);
    // Never persist access tokens.
    localStorage.removeItem('access_token');
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

const redirectToLogin = () => {
  try {
    if (typeof window === 'undefined' || !window.location) return;

    // Avoid redirect loops / unnecessary reloads when we're already on the login page.
    if (window.location.pathname === '/login') return;

    // Prefer replace-style navigation to avoid polluting browser history.
    if (typeof window.location.replace === 'function') {
      window.location.replace('/login');
    } else {
      window.location.href = '/login';
    }

    // In some test/non-browser environments, `replace` is mocked and may not mutate href.
    // Keep href/pathname consistent for callers that read it after redirect.
    try {
      window.location.href = '/login';
      window.location.pathname = '/login';
    } catch (_) {
      // ignore
    }
  } catch (e) {
    // Ignore navigation errors in non-browser/test environments.
  }
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
        clearTokens();
        redirectToLogin();
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
        redirectToLogin();
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
        redirectToLogin();
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
      if (typeof response.text === 'function') {
        return response.text();
      }
      return null;
    }

    const contentType = (() => {
      const h = response.headers;
      if (h && typeof h.get === 'function') {
        return h.get('content-type');
      }
      if (h && (h['content-type'] || h['Content-Type'])) {
        return h['content-type'] || h['Content-Type'];
      }
      return null;
    })();

    // In tests, mocked fetch responses often omit headers. If `json()` exists, assume JSON.
    if ((contentType && contentType.includes('application/json')) || (!contentType && typeof response.json === 'function')) {
      try {
        // `response.json()` returns a promise; parse errors reject asynchronously.
        // Await here so parse failures are caught and we can gracefully return null.
        return await response.json();
      } catch (e) {
        return null;
      }
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

