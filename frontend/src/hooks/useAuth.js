import { useState, useEffect } from 'react';
import useStore from '../store/store';
import { getInitialUser } from '../utils/authUtils';

export const useAuth = () => {
  const { user, setUser: setGlobalUser } = useStore();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Listen for storage changes (e.g., logout in another tab)
    const handleStorageChange = (e) => {
      if (e.key === 'access_token' || e.key === 'user' || e.key === 'remember_me') {
        const newUser = getInitialUser();
        setGlobalUser(newUser);
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [setGlobalUser]);

  const login = (userData, accessToken, refreshToken, rememberMe = false) => {
    const storage = rememberMe ? localStorage : sessionStorage;

    // Store tokens in appropriate storage
    storage.setItem('access_token', accessToken);
    storage.setItem('refresh_token', refreshToken);
    storage.setItem('user', JSON.stringify(userData));

    // Store remember_me flag in localStorage (always)
    if (rememberMe) {
      localStorage.setItem('remember_me', 'true');
    } else {
      localStorage.removeItem('remember_me');
      // Clear localStorage tokens if not remembering
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

