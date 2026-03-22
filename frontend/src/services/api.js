import { getStorage } from '../utils/authUtils';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

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

const api = {
  get: async (endpoint, options = {}) => {
    try {
      const token = getAuthToken();
      const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
      };

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'GET',
        headers,
        ...options,
      });

      if (!response.ok) {
        // If 401 Unauthorized, try to refresh token
        if (response.status === 401 && getRefreshToken()) {
          try {
            const newAccessToken = await refreshAccessToken();
            // Retry the original request with new token
            headers['Authorization'] = `Bearer ${newAccessToken}`;
            const retryResponse = await fetch(`${API_BASE_URL}${endpoint}`, {
              method: 'GET',
              headers,
              ...options,
            });

            if (!retryResponse.ok) {
              // If retry still fails, throw error
              let errorMessage = `API Error: ${retryResponse.statusText}`;
              try {
                const errorData = await retryResponse.json();
                if (errorData.detail) {
                  if (Array.isArray(errorData.detail)) {
                    const validationErrors = errorData.detail.map(err => {
                      const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
                      return `${field}: ${err.msg}`;
                    });
                    errorMessage = validationErrors.join(', ');
                  } else {
                    errorMessage = errorData.detail;
                  }
                } else if (errorData.message) {
                  errorMessage = errorData.message;
                }
              } catch (e) {
                // If response is not JSON, use status text
              }
              const error = new Error(errorMessage);
              error.status = retryResponse.status;
              error.response = retryResponse;
              throw error;
            }

            return retryResponse.json();
          } catch (refreshError) {
            // Token refresh failed, clear tokens and redirect to login
            clearTokens();
            if (window.location.pathname !== '/login') {
              window.location.href = '/login';
            }
            throw refreshError;
          }
        }

        // Try to extract error detail from response
        let errorMessage = `API Error: ${response.statusText}`;
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            // Handle FastAPI validation errors (array format)
            if (Array.isArray(errorData.detail)) {
              const validationErrors = errorData.detail.map(err => {
                const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
                return `${field}: ${err.msg}`;
              });
              errorMessage = validationErrors.join(', ');
            } else {
              errorMessage = errorData.detail;
            }
          } else if (errorData.message) {
            errorMessage = errorData.message;
          }
        } catch (e) {
          // If response is not JSON, use status text
        }
        const error = new Error(errorMessage);
        error.status = response.status;
        error.response = response;
        throw error;
      }

      return response.json();
    } catch (error) {
      // Handle network errors
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Something went wrong');
      }
      throw error;
    }
  },

  getText: async (endpoint, options = {}) => {
    try {
      const token = getAuthToken();
      const headers = {
        ...options.headers,
      };

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'GET',
        headers,
        ...options,
      });

      if (!response.ok) {
        // If 401 Unauthorized, try to refresh token
        if (response.status === 401 && getRefreshToken()) {
          try {
            const newAccessToken = await refreshAccessToken();
            headers['Authorization'] = `Bearer ${newAccessToken}`;
            const retryResponse = await fetch(`${API_BASE_URL}${endpoint}`, {
              method: 'GET',
              headers,
              ...options,
            });

            if (!retryResponse.ok) {
              let errorMessage = `API Error: ${retryResponse.statusText}`;
              try {
                const errorData = await retryResponse.json();
                if (errorData.detail) {
                  if (Array.isArray(errorData.detail)) {
                    const validationErrors = errorData.detail.map(err => {
                      const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
                      return `${field}: ${err.msg}`;
                    });
                    errorMessage = validationErrors.join(', ');
                  } else {
                    errorMessage = errorData.detail;
                  }
                } else if (errorData.message) {
                  errorMessage = errorData.message;
                }
              } catch (e) {
                // If response is not JSON, use status text
              }
              const error = new Error(errorMessage);
              error.status = retryResponse.status;
              error.response = retryResponse;
              throw error;
            }

            return retryResponse.text();
          } catch (refreshError) {
            clearTokens();
            if (window.location.pathname !== '/login') {
              window.location.href = '/login';
            }
            throw refreshError;
          }
        }

        let errorMessage = `API Error: ${response.statusText}`;
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            if (Array.isArray(errorData.detail)) {
              const validationErrors = errorData.detail.map(err => {
                const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
                return `${field}: ${err.msg}`;
              });
              errorMessage = validationErrors.join(', ');
            } else {
              errorMessage = errorData.detail;
            }
          } else if (errorData.message) {
            errorMessage = errorData.message;
          }
        } catch (e) {
          // If response is not JSON, use status text
        }
        const error = new Error(errorMessage);
        error.status = response.status;
        error.response = response;
        throw error;
      }

      return response.text();
    } catch (error) {
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Something went wrong');
      }
      throw error;
    }
  },

  post: async (endpoint, data, options = {}) => {
    try {
      const token = getAuthToken();
      const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
      };

      let body;
      if (data instanceof FormData) {
        delete headers['Content-Type'];
        body = data;
      } else {
        body = JSON.stringify(data);
      }

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers,
        body,
        ...options,
      });

      if (!response.ok) {
        // If 401 Unauthorized, try to refresh token
        if (response.status === 401 && getRefreshToken()) {
          try {
            const newAccessToken = await refreshAccessToken();
            // Retry the original request with new token
            headers['Authorization'] = `Bearer ${newAccessToken}`;
            const retryResponse = await fetch(`${API_BASE_URL}${endpoint}`, {
              method: 'POST',
              headers,
              body,
              ...options,
            });

            if (!retryResponse.ok) {
              // If retry still fails, throw error
              let errorMessage = `API Error: ${retryResponse.statusText}`;
              let errorDetails = null;
              try {
                const errorData = await retryResponse.json();
                if (errorData.detail) {
                  if (Array.isArray(errorData.detail)) {
                    const validationErrors = errorData.detail.map(err => {
                      const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
                      return `${field}: ${err.msg}`;
                    });
                    errorMessage = validationErrors.join(', ');
                    errorDetails = errorData.detail;
                  } else {
                    errorMessage = errorData.detail;
                  }
                } else if (errorData.message) {
                  errorMessage = errorData.message;
                }
              } catch (e) {
                // If response is not JSON, use status text
              }
              const error = new Error(errorMessage);
              error.status = retryResponse.status;
              error.response = retryResponse;
              error.details = errorDetails;
              throw error;
            }

            return retryResponse.json();
          } catch (refreshError) {
            // Token refresh failed, clear tokens and redirect to login
            clearTokens();
            if (window.location.pathname !== '/login') {
              window.location.href = '/login';
            }
            throw refreshError;
          }
        }

        // Try to extract error detail from response
        let errorMessage = `API Error: ${response.statusText}`;
        let errorDetails = null;
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            // Handle FastAPI validation errors (array format)
            if (Array.isArray(errorData.detail)) {
              // Format validation errors into readable messages
              const validationErrors = errorData.detail.map(err => {
                const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
                return `${field}: ${err.msg}`;
              });
              errorMessage = validationErrors.join(', ');
              errorDetails = errorData.detail;
            } else {
              // Single error message
              errorMessage = errorData.detail;
            }
          } else if (errorData.message) {
            errorMessage = errorData.message;
          }
        } catch (e) {
          // If response is not JSON, use status text
        }
        const error = new Error(errorMessage);
        error.status = response.status;
        error.response = response;
        error.details = errorDetails;
        throw error;
      }

      return response.json();
    } catch (error) {
      // Handle network errors (CORS, connection refused, etc.)
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Something went wrong');
      }
      throw error;
    }
  },

  put: async (endpoint, data, options = {}) => {
    try {
      const token = getAuthToken();
      const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
      };

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(data),
        ...options,
      });

      if (!response.ok) {
        // If 401 Unauthorized, try to refresh token
        if (response.status === 401 && getRefreshToken()) {
          try {
            const newAccessToken = await refreshAccessToken();
            // Retry the original request with new token
            headers['Authorization'] = `Bearer ${newAccessToken}`;
            const retryResponse = await fetch(`${API_BASE_URL}${endpoint}`, {
              method: 'PUT',
              headers,
              body: JSON.stringify(data),
              ...options,
            });

            if (!retryResponse.ok) {
              // If retry still fails, throw error
              let errorMessage = `API Error: ${retryResponse.statusText}`;
              try {
                const errorData = await retryResponse.json();
                if (errorData.detail) {
                  if (Array.isArray(errorData.detail)) {
                    const validationErrors = errorData.detail.map(err => {
                      const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
                      return `${field}: ${err.msg}`;
                    });
                    errorMessage = validationErrors.join(', ');
                  } else {
                    errorMessage = errorData.detail;
                  }
                } else if (errorData.message) {
                  errorMessage = errorData.message;
                }
              } catch (e) {
                // If response is not JSON, use status text
              }
              const error = new Error(errorMessage);
              error.status = retryResponse.status;
              error.response = retryResponse;
              throw error;
            }

            return retryResponse.json();
          } catch (refreshError) {
            // Token refresh failed, clear tokens and redirect to login
            clearTokens();
            if (window.location.pathname !== '/login') {
              window.location.href = '/login';
            }
            throw refreshError;
          }
        }

        // Try to extract error detail from response
        let errorMessage = `API Error: ${response.statusText}`;
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            // Handle FastAPI validation errors (array format)
            if (Array.isArray(errorData.detail)) {
              const validationErrors = errorData.detail.map(err => {
                const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
                return `${field}: ${err.msg}`;
              });
              errorMessage = validationErrors.join(', ');
            } else {
              errorMessage = errorData.detail;
            }
          } else if (errorData.message) {
            errorMessage = errorData.message;
          }
        } catch (e) {
          // If response is not JSON, use status text
        }
        const error = new Error(errorMessage);
        error.status = response.status;
        error.response = response;
        throw error;
      }

      return response.json();
    } catch (error) {
      // Handle network errors
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Something went wrong');
      }
      throw error;
    }
  },

  delete: async (endpoint, options = {}) => {
    try {
      const token = getAuthToken();
      const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
      };

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'DELETE',
        headers,
        ...options,
      });

      if (!response.ok) {
        // If 401 Unauthorized, try to refresh token
        if (response.status === 401 && getRefreshToken()) {
          try {
            const newAccessToken = await refreshAccessToken();
            // Retry the original request with new token
            headers['Authorization'] = `Bearer ${newAccessToken}`;
            const retryResponse = await fetch(`${API_BASE_URL}${endpoint}`, {
              method: 'DELETE',
              headers,
              ...options,
            });

            if (!retryResponse.ok) {
              // If retry still fails, throw error
              let errorMessage = `API Error: ${retryResponse.statusText}`;
              try {
                const errorData = await retryResponse.json();
                if (errorData.detail) {
                  if (Array.isArray(errorData.detail)) {
                    const validationErrors = errorData.detail.map(err => {
                      const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
                      return `${field}: ${err.msg}`;
                    });
                    errorMessage = validationErrors.join(', ');
                  } else {
                    errorMessage = errorData.detail;
                  }
                } else if (errorData.message) {
                  errorMessage = errorData.message;
                }
              } catch (e) {
                // If response is not JSON, use status text
              }
              const error = new Error(errorMessage);
              error.status = retryResponse.status;
              error.response = retryResponse;
              throw error;
            }

            // DELETE returns 204 No Content
            if (retryResponse.status === 204) {
              return null;
            }

            const contentType = retryResponse.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
              return retryResponse.json();
            }

            return null;
          } catch (refreshError) {
            // Token refresh failed, clear tokens and redirect to login
            clearTokens();
            if (window.location.pathname !== '/login') {
              window.location.href = '/login';
            }
            throw refreshError;
          }
        }

        // Try to extract error detail from response
        let errorMessage = `API Error: ${response.statusText}`;
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            if (Array.isArray(errorData.detail)) {
              const validationErrors = errorData.detail.map(err => {
                const field = err.loc ? err.loc[err.loc.length - 1] : 'field';
                return `${field}: ${err.msg}`;
              });
              errorMessage = validationErrors.join(', ');
            } else {
              errorMessage = errorData.detail;
            }
          } else if (errorData.message) {
            errorMessage = errorData.message;
          }
        } catch (e) {
          // If response is not JSON, use status text
        }
        const error = new Error(errorMessage);
        error.status = response.status;
        error.response = response;
        throw error;
      }

      // DELETE returns 204 No Content, so no JSON to parse
      if (response.status === 204) {
        return null;
      }

      // If there's content, try to parse it
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return response.json();
      }

      return null;
    } catch (error) {
      // Handle network errors
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Something went wrong');
      }
      throw error;
    }
  },
};

export default api;

