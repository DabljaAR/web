import { useState, useEffect, useRef, useMemo } from 'react';
import { mediaService } from '../services/mediaService';
import { useTranslation } from './useTranslation';

export const useHistory = (initialLimit = 5) => {
  const { t } = useTranslation();
  const [filters, setFilters] = useState({
    search: '',
    status: 'all',
    domain: 'all',
    dateRange: 'last30Days',
    sortBy: 'dateNewest',
    mediaType: 'all'
  });

  const [activeMediaTab, setActiveMediaTab] = useState('all');

  const [pagination, setPagination] = useState({
    page: 1,
    limit: initialLimit,
    total: 0,
    pages: 1,
    totalCompleted: 0,
    totalFailed: 0
  });

  const [historyItems, setHistoryItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState(null);
  const [debouncedSearch, setDebouncedSearch] = useState(filters.search);
  const deletingIds = useRef(new Set());

  // Debounced search logic for API calls
  useEffect(() => {
    const handler = setTimeout(() => {
      if (filters.search !== debouncedSearch) {
        setDebouncedSearch(filters.search);
        setPagination(prev => ({ ...prev, page: 1 }));
      }
    }, 500);
    return () => clearTimeout(handler);
  }, [filters.search, debouncedSearch]);

  const fetchHistory = async (internal = false, signal = null) => {
    try {
      if (!internal) setLoading(true);
      const data = await mediaService.getVideos({
        page: pagination.page,
        limit: pagination.limit,
        search: debouncedSearch,
        sortBy: filters.sortBy,
        dateRange: filters.dateRange,
        status: filters.status,
        mediaType: activeMediaTab === 'all' ? '' : activeMediaTab.toUpperCase(),
        signal
      });

      const videos = Array.isArray(data) ? data : data.items || [];
      const total = data.total || videos.length;
      const pages = data.pages || 1;
      const totalCompleted = data.total_completed || 0;
      const totalFailed = data.total_failed || 0;

      const mappedItems = videos.map(video => {
        const hasActiveJob = Boolean(video.has_active_job);
        const computedStatus = hasActiveJob ? 'processing' : video.status.toLowerCase();
        
        // Find transcript and translation URLs from the jobs array
        const transcriptUrl = video.jobs?.find(j => j.transcript_url)?.transcript_url;
        const translationUrl = video.jobs?.find(j => j.translation_url)?.translation_url;

        return {
          id: video.id,
          name: video.title || video.original_filename,
          date: video.created_at,
          status: computedStatus,
          realStatus: video.status,
          url: video.url,
          thumbnailUrl: video.thumbnail_url,
          audioUrl: video.audio_url,
          transcriptUrl: transcriptUrl,
          translationUrl: translationUrl,
          mediaType: video.media_type,
          type: computedStatus === 'completed' ? 'success' :
            computedStatus === 'failed' ? 'failed' : 'processing'
        };
      });

      const safeItems = mappedItems.filter(item => !deletingIds.current.has(item.id));
      setHistoryItems(safeItems);
      setPagination(prev => ({ ...prev, total, pages, totalCompleted, totalFailed }));

      const hasActive = mappedItems.some(v => v.status === 'processing' || v.status === 'queued' || v.status === 'pending');
      setIsPolling(hasActive);
      setError(null);
    } catch (err) {
      if (err.name === 'AbortError') return;
      if (import.meta.env.DEV) console.error("Failed to fetch history:", err);
      if (!internal) setError(t('history.loadError') || 'Failed to load history items.');
      setIsPolling(false);
    } finally {
      if (!internal) setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    fetchHistory(false, controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagination.page, pagination.limit, debouncedSearch, filters.sortBy, filters.dateRange, filters.status, activeMediaTab]);

  useEffect(() => {
    let intervalId;
    if (isPolling) {
      intervalId = setInterval(() => fetchHistory(true), 10000);
    }
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPolling, pagination.page, pagination.limit, debouncedSearch, filters.sortBy, filters.dateRange, filters.status, activeMediaTab]);

  return {
    filters,
    setFilters,
    activeMediaTab,
    setActiveMediaTab,
    pagination,
    setPagination,
    historyItems,
    loading,
    error,
    isPolling,
    deletingIds,
    fetchHistory
  };
};
