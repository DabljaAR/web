import { useState, useEffect, useRef } from 'react';
import { mediaService } from '../services/mediaService';

export const useJobPolling = (pollInterval = 5000) => {
  const [processingJobs, setProcessingJobs] = useState([]);
  const [recentJobs, setRecentJobs] = useState([]);
  const [isPolling, setIsPolling] = useState(true);
  const [isLoading, setIsLoading] = useState(true);

  // Track deleting items to prevent flickering during polling
  const deletingIds = useRef(new Set());

  const fetchJobs = async () => {
    try {
      const data = await mediaService.getDashboardData();

      const active = data.active || [];
      const recent = data.recent || [];

      const pending = active.map(v => ({
        id: v.id,
        name: v.name,
        status: v.status.toLowerCase(),
        type: v.type,
        progress: v.progress,
        estTime: v.progress > 0 ? `${v.progress.toFixed(0)}%` : 'Processing...'
      }));

      const completed = recent.map(v => {
        // Find transcript and translation URLs from the jobs array
        const transcriptUrl = v.jobs?.find(j => j.transcript_url)?.transcript_url;
        const translationUrl = v.jobs?.find(j => j.translation_url)?.translation_url;

        return {
          id: v.id,
          name: v.title || v.original_filename,
          status: v.status.toLowerCase(),
          url: v.url,
          thumbnailUrl: v.thumbnail_url,
          audioUrl: v.audio_url,
          transcriptUrl: transcriptUrl,
          translationUrl: translationUrl,
          mediaType: v.media_type,
          type: v.status === 'COMPLETED' ? 'success' : 'failed'
        };
      });

      // Filter out items that are currently marked for deletion
      const safePending = pending.filter(job => !deletingIds.current.has(job.id));
      const safeCompleted = completed.filter(job => !deletingIds.current.has(job.id));

      setProcessingJobs(safePending);
      setRecentJobs(safeCompleted);

      // Poll only if there are pending jobs
      setIsPolling(pending.length > 0);

    } catch (error) {
      console.error("Error fetching jobs:", error);
      setIsPolling(false);
    } finally {
      setIsLoading(false);
    }
  };

  // Initial fetch on mount
  useEffect(() => {
    fetchJobs();
  }, []);

  // Polling effect
  useEffect(() => {
    let intervalId;
    if (isPolling) {
      intervalId = setInterval(fetchJobs, pollInterval);
    }
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [isPolling, pollInterval]);

  return {
    processingJobs,
    setProcessingJobs,
    recentJobs,
    setRecentJobs,
    isPolling,
    setIsPolling,
    isLoading,
    deletingIds,
    fetchJobs
  };
};
