import { useState, useEffect, useRef } from 'react';
import { mediaService } from '../services/mediaService';
import type { ProcessingJob, RecentJob, DashboardDataResponse } from '../types/job';

export const useJobPolling = (pollInterval: number = 5000) => {
  const [processingJobs, setProcessingJobs] = useState<ProcessingJob[]>([]);
  const [recentJobs, setRecentJobs] = useState<RecentJob[]>([]);
  const [isPolling, setIsPolling] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Track deleting items to prevent flickering during polling
  const deletingIds = useRef<Set<string>>(new Set());

  const fetchJobs = async (signal?: AbortSignal) => {
    try {
      const data = await mediaService.getDashboardData({ signal }) as DashboardDataResponse;

      const active = data.active || [];
      const recent = data.recent || [];

      const pending: ProcessingJob[] = active.map((v: any) => {
        const progress = v.progress !== undefined && v.progress !== null ? Number(v.progress) : 0;
        return {
          id: v.id,
          name: v.name ?? v.title ?? v.original_filename ?? 'Untitled',
          status: (typeof v.status === 'string' ? v.status : 'PENDING').toLowerCase() as any,
          type: v.type,
          progress,
          estTime: progress > 0 ? `${Math.round(progress)}%` : 'Processing...'
        };
      });

      const completed: RecentJob[] = recent.map(v => {
        // Find transcript and translation URLs from the jobs array
        const transcriptUrl = v.jobs?.find(j => j.transcript_url)?.transcript_url;
        const translationUrl = v.jobs?.find(j => j.translation_url)?.translation_url;

        return {
          id: v.id,
          name: v.title || v.original_filename || 'Unknown Video',
          status: v.status.toLowerCase() as any,
          date: v.created_at,
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

    } catch (error: any) {
      if (error.name === 'AbortError') return;
      if (import.meta.env.DEV) console.error("Error fetching jobs:", error);
      setIsPolling(false);
    } finally {
      setIsLoading(false);
    }
  };

  // Derived state to check if we should be polling
  const hasActiveJobs = processingJobs.some(job =>
    ['pending', 'processing', 'queued', 'downloading'].includes(job.status)
  );

  // Initial fetch on mount
  useEffect(() => {
    const controller = new AbortController();
    fetchJobs(controller.signal);
    return () => controller.abort();
  }, []);

  // Polling effect
  useEffect(() => {
    // Only poll if there are active jobs OR if polling was manually triggered (e.g. after starting a job)
    if (!hasActiveJobs && !isPolling) return;

    const intervalId = setInterval(fetchJobs, pollInterval);
    return () => clearInterval(intervalId);
  }, [hasActiveJobs, isPolling, pollInterval]);

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
