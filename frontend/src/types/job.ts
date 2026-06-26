export type JobStatus = 'pending' | 'processing' | 'queued' | 'downloading' | 'completed' | 'failed' | 'success';

export interface StageInfo {
  type: string;
  label: string;
  order: number;
  status: string;
  progress: number;
  segment_count?: number;
  error?: string;
}

export interface BaseJob {
  id: string;
  name: string;
  status: JobStatus;
  date?: string;
}

export interface ProcessingJob extends BaseJob {
  progress?: number;
  estTime?: string;
  type?: string;
  stages?: StageInfo[];
  totalSegments?: number;
}

export interface RecentJob extends BaseJob {
  url?: string;
  thumbnailUrl?: string;
  audioUrl?: string;
  transcriptUrl?: string;
  translationUrl?: string;
  mediaType?: string;
  realStatus?: string;
  type: 'success' | 'failed' | 'processing';
}

export interface DashboardDataResponse {
  active: Array<{
    id: string;
    name: string;
    status: string;
    type?: string;
    progress?: number;
    stages?: Array<{
      type: string;
      label: string;
      order: number;
      status: string;
      progress: number;
      segment_count?: number;
      error?: string;
    }>;
  }>;
  recent: Array<{
    id: string;
    title?: string;
    original_filename?: string;
    status: string;
    url?: string;
    thumbnail_url?: string;
    audio_url?: string;
    media_type?: string;
    created_at?: string;
    jobs?: Array<{
      transcript_url?: string;
      translation_url?: string;
    }>;
  }>;
}

export interface VideoListResponse {
  items: any[];
  total: number;
  pages: number;
  total_completed: number;
  total_failed: number;
}
