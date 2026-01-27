import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useDashboard } from './useDashboard';
import { useFetch } from '../../../hooks/useFetch';

// Mock the useFetch hook
vi.mock('../../../hooks/useFetch');

describe('useDashboard Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns stats when data is available', async () => {
    const mockStats = {
      totalUsers: 1000,
      totalRevenue: 50000,
      activeProjects: 25,
      completionRate: 85,
    };

    useFetch.mockReturnValue({
      data: mockStats,
      loading: false,
      error: null,
    });

    const { result } = renderHook(() => useDashboard());

    await waitFor(() => {
      expect(result.current.stats).toEqual(mockStats);
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('returns loading state', () => {
    useFetch.mockReturnValue({
      data: null,
      loading: true,
      error: null,
    });

    const { result } = renderHook(() => useDashboard());

    expect(result.current.loading).toBe(true);
    expect(result.current.stats).toBeNull();
  });

  it('returns error state', () => {
    const error = 'Failed to fetch stats';
    useFetch.mockReturnValue({
      data: null,
      loading: false,
      error,
    });

    const { result } = renderHook(() => useDashboard());

    expect(result.current.error).toBe(error);
    expect(result.current.stats).toBeNull();
  });

  it('updates stats when data changes', async () => {
    const initialStats = { totalUsers: 100 };
    const updatedStats = { totalUsers: 200 };

    useFetch.mockReturnValue({
      data: initialStats,
      loading: false,
      error: null,
    });

    const { result, rerender } = renderHook(() => useDashboard());

    await waitFor(() => {
      expect(result.current.stats).toEqual(initialStats);
    });

    useFetch.mockReturnValue({
      data: updatedStats,
      loading: false,
      error: null,
    });

    rerender();

    await waitFor(() => {
      expect(result.current.stats).toEqual(updatedStats);
    });
  });
});



