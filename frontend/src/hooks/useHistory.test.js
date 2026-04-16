import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useHistory } from './useHistory';
import { mediaService } from '../services/mediaService';

vi.mock('../services/mediaService', () => ({
  mediaService: {
    getVideos: vi.fn(),
  },
}));

vi.mock('./useTranslation', () => ({
  useTranslation: () => ({
    t: (key) => key,
  }),
}));

describe('useHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('maps history items defensively and computes status + polling', async () => {
    mediaService.getVideos.mockResolvedValueOnce({
      items: [
        {
          id: '1',
          has_active_job: true,
          status: 'COMPLETED',
          // Missing title/original_filename/created_at should not break mapping
          title: undefined,
          original_filename: undefined,
          created_at: undefined,
          url: 'https://example.com/video.mp4',
          thumbnail_url: 'https://example.com/thumb.jpg',
          audio_url: 'https://example.com/audio.mp3',
          media_type: 'VIDEO',
          jobs: [
            { transcript_url: 'https://example.com/t.txt' },
            { translation_url: 'https://example.com/x.txt' },
          ],
        },
        {
          id: '2',
          has_active_job: false,
          status: 'completed',
          title: 'My Title',
          created_at: '2020-01-01T00:00:00.000Z',
          jobs: [],
        },
      ],
      total: 2,
      pages: 1,
      total_completed: 1,
      total_failed: 0,
    });

    const { result } = renderHook(() => useHistory(5));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mediaService.getVideos).toHaveBeenCalledWith(
      expect.objectContaining({
        page: 1,
        limit: 5,
        search: '',
        sortBy: 'dateNewest',
        dateRange: 'last30Days',
        status: 'all',
        mediaType: '',
      })
    );

    expect(result.current.historyItems).toHaveLength(2);

    // Item 1: safe defaults + job URL extraction
    expect(result.current.historyItems[0].name).toBe('history.untitled');
    expect(result.current.historyItems[0].date).toBeNull();
    expect(result.current.historyItems[0].status).toBe('processing');
    expect(result.current.historyItems[0].transcriptUrl).toBe('https://example.com/t.txt');
    expect(result.current.historyItems[0].translationUrl).toBe('https://example.com/x.txt');

    // Polling should be enabled when any item is processing/queued/pending
    expect(result.current.isPolling).toBe(true);

    // Pagination stats should be applied
    expect(result.current.pagination.total).toBe(2);
    expect(result.current.pagination.pages).toBe(1);
    expect(result.current.pagination.totalCompleted).toBe(1);
    expect(result.current.pagination.totalFailed).toBe(0);
  });

  it('debounces search input and resets page to 1', async () => {
    // Use real timers here: the hook relies on a 500ms debounce in a useEffect,
    // and waitFor is more reliable with real timers.

    mediaService.getVideos
      // Initial fetch (page 1)
      .mockResolvedValueOnce({ items: [], total: 0, pages: 1 })
      // Fetch after manual page change (page 2)
      .mockResolvedValueOnce({ items: [], total: 0, pages: 1 })
      // Fetch after debounce triggers page reset + new search (page 1, search="hello")
      .mockResolvedValueOnce({ items: [], total: 0, pages: 1 });

    const { result } = renderHook(() => useHistory(5));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Move to another page so we can verify page reset
    act(() => {
      result.current.setPagination((prev) => ({ ...prev, page: 2 }));
    });
    expect(result.current.pagination.page).toBe(2);

    // Change search and ensure it triggers the debounced update
    act(() => {
      result.current.setFilters((prev) => ({ ...prev, search: 'hello' }));
    });

    await waitFor(
      () => {
        expect(result.current.pagination.page).toBe(1);
        expect(mediaService.getVideos).toHaveBeenCalledTimes(3);
      },
      { timeout: 3000 }
    );

    expect(mediaService.getVideos).toHaveBeenLastCalledWith(
      expect.objectContaining({
        search: 'hello',
        page: 1,
      })
    );
  });
});
