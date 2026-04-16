import { useState, useEffect } from 'react';
import useStore from '../store/store';
import { getInitialUser } from '../utils/authUtils';

const LOGOUT_SYNC_KEY = 'auth:logout';

export const useAuth = () => {
  const { user, setUser: setGlobalUser } = useStore();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Listen for storage changes (e.g., logout in another tab)
    const handleStorageChange = (e) => {
      if (e.key === LOGOUT_SYNC_KEY) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        localStorage.removeItem('remember_me');
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
        sessionStorage.removeItem('user');
        setGlobalUser(null);
        return;
      }

      if (e.key === 'access_token' || e.key === 'user' || e.key === 'remember_me') {
        const newUser = getInitialUser();
        setGlobalUser(newUser);
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [setGlobalUser]);

  const login = (userData, accessToken, refreshToken, rememberMe = false) => {
    // Always keep access tokens session-scoped to reduce persistence and XSS exposure.
    // If persistence is required, only persist the refresh token and user profile.
    sessionStorage.setItem('access_token', accessToken);
    sessionStorage.setItem('refresh_token', refreshToken);
    sessionStorage.setItem('user', JSON.stringify(userData));

    if (rememberMe) {
      localStorage.setItem('remember_me', 'true');
      // Do NOT persist access tokens in localStorage.
      localStorage.removeItem('access_token');
      localStorage.setItem('refresh_token', refreshToken);
      localStorage.setItem('user', JSON.stringify(userData));
    } else {
      localStorage.removeItem('remember_me');
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
    }

    setGlobalUser(userData);
  };

  const logout = () => {
    // Clear both localStorage and sessionStorage
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    localStorage.removeItem('remember_me');
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');
    sessionStorage.removeItem('user');
    // Force other tabs to logout too (works even when auth is sessionStorage-only).
    localStorage.setItem(LOGOUT_SYNC_KEY, String(Date.now()));
    setGlobalUser(null);
  };

  return {
    user,
    loading,
    login,
    logout,
    isAuthenticated: !!user,
  };
};
