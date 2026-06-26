import { useState, useEffect, useRef } from 'react';
import { mediaService } from '../services/mediaService';
import type { ProcessingJob, RecentJob, StageInfo, DashboardDataResponse } from '../types/job';

const STAGE_WEIGHT: Record<string, number> = {
  STT_TRANSCRIBE: 20,
  NMT_TRANSLATE: 35,
  TTS_SYNTHESIZE: 55,
  DUBBING_MERGE: 80,
};

const STAGE_ORDER = ['STT_TRANSCRIBE', 'NMT_TRANSLATE', 'TTS_SYNTHESIZE', 'DUBBING_MERGE'];

export const useJobPolling = (pollInterval: number = 5000) => {
  const [processingJobs, setProcessingJobs] = useState<ProcessingJob[]>([]);
  const [recentJobs, setRecentJobs] = useState<RecentJob[]>([]);
  const [isPolling, setIsPolling] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const deletingIds = useRef<Set<string>>(new Set());

  const fetchJobs = async (signal?: AbortSignal) => {
    try {
      const data = await mediaService.getDashboardData({ signal }) as DashboardDataResponse;

      const active = data.active || [];
      const recent = data.recent || [];

      const pending: ProcessingJob[] = active.map((v: any) => {
        const rawStages: StageInfo[] = (v.stages || []).map((s: any) => ({
          type: s.type || '',
          label: s.label || s.type || '',
          order: s.order ?? 99,
          status: (s.status || 'QUEUED').toLowerCase(),
          progress: s.progress ?? 0,
          segment_count: s.segment_count ?? undefined,
          error: s.error ?? undefined,
        }));

        // Sort stages by order
        rawStages.sort((a, b) => a.order - b.order);

        // Calculate realistic progress from completed stages
        const completedStages = rawStages.filter(s => s.status === 'completed').length;
        const currentStage = rawStages.find(s => s.status === 'processing');

        let progress = v.progress !== undefined && v.progress !== null ? Number(v.progress) : 0;
        if (rawStages.length > 0 && currentStage) {
          const baseWeight = STAGE_WEIGHT[currentStage.type] ?? (completedStages * 25);
          const intraProgress = (currentStage.progress / 100) * (25 / Math.max(rawStages.length, 1));
          progress = Math.round(baseWeight + intraProgress);
        } else if (rawStages.length > 0 && completedStages > 0) {
          progress = completedStages * 25;
        }
        progress = Math.min(100, Math.max(0, progress));

        // Estimate time based on completed stages
        let estTime = 'Waiting...';
        if (completedStages >= 3) {
          estTime = 'Almost done';
        } else if (currentStage) {
          const label = STAGE_ORDER.includes(currentStage.type)
            ? currentStage.label
            : currentStage.type;
          const segs = currentStage.segment_count ? ` (${currentStage.segment_count} segments)` : '';
          estTime = `${label}${segs}`;
        } else if (completedStages > 0) {
          estTime = 'Queued...';
        }

        // Take the first non-null segment count from any stage (they all have same count)
        const totalSegments = rawStages.find(s => s.segment_count != null)?.segment_count ?? 0;

        return {
          id: v.id,
          name: v.name ?? v.title ?? v.original_filename ?? 'Untitled',
          status: (typeof v.status === 'string' ? v.status : 'PENDING').toLowerCase() as any,
          type: v.type,
          progress,
          stages: rawStages,
          estTime: currentStage
            ? `${progress}% — ${estTime}`
            : progress > 0
              ? `${progress}%`
              : 'Processing...',
          totalSegments,
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
