import { useState, useEffect } from 'react';

// Helper functions to get/set tokens based on remember me
const getStorage = () => {
  const rememberMe = localStorage.getItem('remember_me') === 'true';
  return rememberMe ? localStorage : sessionStorage;
};

// Helper function to get initial user (checks both localStorage and sessionStorage)
const getInitialUser = () => {
  try {
    // Check localStorage first (remember me)
    let token = localStorage.getItem('access_token');
    let userData = localStorage.getItem('user');
    
    // If not in localStorage, check sessionStorage
    if (!token || !userData) {
      token = sessionStorage.getItem('access_token');
      userData = sessionStorage.getItem('user');
    }
    
    if (token && userData) {
      return JSON.parse(userData);
    }
  } catch (e) {
    // Invalid user data, clear it
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');
    sessionStorage.removeItem('user');
  }
  return null;
};

export const useAuth = () => {
  // Initialize user state synchronously from localStorage
  const [user, setUser] = useState(getInitialUser);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Listen for storage changes (e.g., logout in another tab)
    const handleStorageChange = (e) => {
      if (e.key === 'access_token' || e.key === 'user' || e.key === 'remember_me') {
        const newUser = getInitialUser();
        setUser(newUser);
      }
    };

    // Listen for localStorage changes (works across tabs)
    window.addEventListener('storage', handleStorageChange);
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

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
    
    setUser(userData);
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
    setUser(null);
  };

  return {
    user,
    loading,
    login,
    logout,
    isAuthenticated: !!user,
  };
};

