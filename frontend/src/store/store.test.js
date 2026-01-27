import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import useStore from './store';

describe('Store (Zustand)', () => {
  beforeEach(() => {
    // Reset store state before each test
    const { setUser, setTheme } = useStore.getState();
    act(() => {
      setUser(null);
      setTheme('light');
    });
  });

  it('initializes with default state', () => {
    const { result } = renderHook(() => useStore());
    
    expect(result.current.user).toBeNull();
    expect(result.current.theme).toBe('light');
  });

  it('sets user', () => {
    const { result } = renderHook(() => useStore());
    const testUser = { id: 1, username: 'testuser' };

    act(() => {
      result.current.setUser(testUser);
    });

    expect(result.current.user).toEqual(testUser);
  });

  it('sets theme', () => {
    const { result } = renderHook(() => useStore());

    act(() => {
      result.current.setTheme('dark');
    });

    expect(result.current.theme).toBe('dark');
  });

  it('isAuthenticated returns false when user is null', () => {
    const { result } = renderHook(() => useStore());

    act(() => {
      result.current.setUser(null);
    });

    expect(result.current.isAuthenticated()).toBe(false);
  });

  it('isAuthenticated returns true when user exists', () => {
    const { result } = renderHook(() => useStore());
    const testUser = { id: 1, username: 'testuser' };

    act(() => {
      result.current.setUser(testUser);
    });

    expect(result.current.isAuthenticated()).toBe(true);
  });

  it('updates state correctly', () => {
    const { result } = renderHook(() => useStore());
    const testUser = { id: 1, username: 'testuser' };

    act(() => {
      result.current.setUser(testUser);
      result.current.setTheme('dark');
    });

    expect(result.current.user).toEqual(testUser);
    expect(result.current.theme).toBe('dark');
    expect(result.current.isAuthenticated()).toBe(true);
  });

  it('maintains state across multiple hook calls', () => {
    const { result: result1 } = renderHook(() => useStore());
    const testUser = { id: 1, username: 'testuser' };

    act(() => {
      result1.current.setUser(testUser);
    });

    const { result: result2 } = renderHook(() => useStore());
    expect(result2.current.user).toEqual(testUser);
  });
});



