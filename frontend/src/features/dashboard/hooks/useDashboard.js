import { useState, useEffect } from 'react';
import { useFetch } from '../../../hooks/useFetch';

export const useDashboard = () => {
  const [stats, setStats] = useState(null);
  const { data, loading, error } = useFetch('/api/dashboard/stats');

  useEffect(() => {
    if (data) {
      setStats(data);
    }
  }, [data]);

  return {
    stats,
    loading,
    error,
  };
};

