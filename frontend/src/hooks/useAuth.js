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
    // Access token: always sessionStorage (tab-scoped, cleared on close)
    sessionStorage.setItem('access_token', accessToken);
    sessionStorage.setItem('refresh_token', refreshToken);
    sessionStorage.setItem('user', JSON.stringify(userData));

    // Store only the preference in localStorage, not the sensitive tokens
    if (rememberMe) {
      localStorage.setItem('remember_me', 'true');
    } else {
      localStorage.removeItem('remember_me');
    }

    // Clear any legacy persistent tokens from localStorage
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');

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

