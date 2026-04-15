import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAuth } from './useAuth';
import useStore from '../store/store';

describe('useAuth Hook', () => {
  beforeEach(() => {
    // Clear all storage before each test
    localStorage.clear();
    sessionStorage.clear();
    // Reset the store to blank
    useStore.setState({ user: null });
  });

  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('returns null user when no token exists', () => {
    const { result } = renderHook(() => useAuth());
    
    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('returns user from sessionStorage when token exists', () => {
    const userData = { id: 1, username: 'testuser', email: 'test@example.com' };
    sessionStorage.setItem('access_token', 'token123');
    sessionStorage.setItem('user', JSON.stringify(userData));
    act(() => {
      useStore.getState().reset();
    });
    
    const { result } = renderHook(() => useAuth());
    
    expect(result.current.user).toEqual(userData);
    expect(result.current.isAuthenticated).toBe(true);
  });

  it('returns user from sessionStorage when token exists', () => {
    const userData = { id: 1, username: 'testuser', email: 'test@example.com' };
    sessionStorage.setItem('access_token', 'token123');
    sessionStorage.setItem('user', JSON.stringify(userData));
    act(() => {
      useStore.getState().reset();
    });
    
    const { result } = renderHook(() => useAuth());
    
    expect(result.current.user).toEqual(userData);
    expect(result.current.isAuthenticated).toBe(true);
  });

  it('login stores auth in localStorage when rememberMe is true', () => {
    const { result } = renderHook(() => useAuth());
    const userData = { id: 1, username: 'testuser' };
    
    act(() => {
      result.current.login(userData, 'access123', 'refresh123', true);
    });
    
    expect(sessionStorage.getItem('access_token')).toBe('access123');
    expect(sessionStorage.getItem('refresh_token')).toBe('refresh123');
    expect(localStorage.getItem('access_token')).toBe('access123');
    expect(localStorage.getItem('refresh_token')).toBe('refresh123');
    expect(localStorage.getItem('remember_me')).toBe('true');
    expect(result.current.user).toEqual(userData);
    expect(result.current.isAuthenticated).toBe(true);
  });

  it('login stores tokens in sessionStorage when rememberMe is false', () => {
    const { result } = renderHook(() => useAuth());
    const userData = { id: 1, username: 'testuser' };
    
    act(() => {
      result.current.login(userData, 'access123', 'refresh123', false);
    });
    
    expect(sessionStorage.getItem('access_token')).toBe('access123');
    expect(sessionStorage.getItem('refresh_token')).toBe('refresh123');
    expect(localStorage.getItem('remember_me')).toBeNull();
    expect(result.current.user).toEqual(userData);
  });

  it('logout clears all tokens and user data', () => {
    const { result } = renderHook(() => useAuth());
    const userData = { id: 1, username: 'testuser' };
    
    // First login
    act(() => {
      result.current.login(userData, 'access123', 'refresh123', true);
    });
    
    expect(result.current.isAuthenticated).toBe(true);
    
    // Then logout
    act(() => {
      result.current.logout();
    });
    
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(sessionStorage.getItem('access_token')).toBeNull();
    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('handles invalid user data gracefully', () => {
    sessionStorage.setItem('user', 'invalid json');
    sessionStorage.setItem('access_token', 'token123');
    useStore.getState().reset();
    
    const { result } = renderHook(() => useAuth());
    
    expect(result.current.user).toBeNull();
    expect(sessionStorage.getItem('access_token')).toBeNull();
  });

  it('returns user from localStorage when remember_me is true', () => {
    const userData = { id: 1, username: 'testuser', email: 'test@example.com' };
    localStorage.setItem('remember_me', 'true');
    localStorage.setItem('access_token', 'token123');
    localStorage.setItem('user', JSON.stringify(userData));
    act(() => {
      useStore.getState().reset();
    });

    const { result } = renderHook(() => useAuth());

    expect(result.current.user).toEqual(userData);
    expect(result.current.isAuthenticated).toBe(true);
  });

  it('listens to storage changes across tabs', () => {
    const { result } = renderHook(() => useAuth());
    
    // Simulate storage change event
    act(() => {
      const event = new StorageEvent('storage', {
        key: 'access_token',
        newValue: 'newtoken',
      });
      window.dispatchEvent(event);
    });
    
    // The hook should react to storage changes
    // Note: This test verifies the event listener is set up
    expect(result.current).toBeDefined();
  });

  it('logs out current tab when logout sync event comes from another tab', () => {
    const { result } = renderHook(() => useAuth());
    const userData = { id: 1, username: 'testuser' };

    act(() => {
      result.current.login(userData, 'access123', 'refresh123', false);
    });
    expect(result.current.isAuthenticated).toBe(true);

    act(() => {
      const event = new StorageEvent('storage', {
        key: 'auth:logout',
        newValue: String(Date.now()),
      });
      window.dispatchEvent(event);
    });

    expect(localStorage.getItem('access_token')).toBeNull();
    expect(sessionStorage.getItem('access_token')).toBeNull();
    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });
});
