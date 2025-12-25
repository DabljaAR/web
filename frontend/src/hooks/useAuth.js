import { useState, useEffect } from 'react';

export const useAuth = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check for stored auth token
    const token = localStorage.getItem('authToken');
    if (token) {
      // Validate token and set user
      // This is a placeholder - implement actual auth logic
      setUser({ id: 1, name: 'User' });
    }
    setLoading(false);
  }, []);

  const login = async (credentials) => {
    // Implement login logic
    const token = 'mock-token';
    localStorage.setItem('authToken', token);
    setUser({ id: 1, name: 'User' });
  };

  const logout = () => {
    localStorage.removeItem('authToken');
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

