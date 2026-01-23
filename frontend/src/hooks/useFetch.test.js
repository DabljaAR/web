import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useFetch } from './useFetch';

describe('useFetch Hook', () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns loading state initially', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: 'test' }),
    });

    const { result } = renderHook(() => useFetch('https://api.example.com/data'));
    
    // Check initial state immediately
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
    
    // Wait for the fetch to complete to avoid act warnings
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
  });

  it('fetches data successfully', async () => {
    const mockData = { id: 1, name: 'Test' };
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    });

    const { result } = renderHook(() => useFetch('https://api.example.com/data'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual(mockData);
    expect(result.current.error).toBeNull();
  });

  it('handles fetch errors', async () => {
    global.fetch.mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(() => useFetch('https://api.example.com/data'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe('Network error');
  });

  it('handles HTTP errors', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    });

    const { result } = renderHook(() => useFetch('https://api.example.com/data'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('HTTP error! status: 404');
  });

  it('does not fetch when url is empty', () => {
    const { result } = renderHook(() => useFetch(''));

    expect(result.current.loading).toBe(true);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('passes options to fetch', async () => {
    const mockData = { data: 'test' };
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    });

    const options = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
    renderHook(() => useFetch('https://api.example.com/data', options));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });

    expect(global.fetch).toHaveBeenCalledWith('https://api.example.com/data', options);
  });

  it('refetches when url changes', async () => {
    const mockData1 = { id: 1 };
    const mockData2 = { id: 2 };

    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockData1,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockData2,
      });

    const { result, rerender } = renderHook(
      ({ url }) => useFetch(url),
      { initialProps: { url: 'https://api.example.com/data1' } }
    );

    await waitFor(() => {
      expect(result.current.data).toEqual(mockData1);
    });

    rerender({ url: 'https://api.example.com/data2' });

    await waitFor(() => {
      expect(result.current.data).toEqual(mockData2);
    });

    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
});

