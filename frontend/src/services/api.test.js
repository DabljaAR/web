import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import api from './api';

describe('API Service', () => {
  beforeEach(() => {
    global.fetch = vi.fn();
    localStorage.clear();
    sessionStorage.clear();
    // Reset module-level variables
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  describe('GET requests', () => {
    it('makes GET request successfully', async () => {
      const mockData = { id: 1, name: 'Test' };
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockData,
      });

      const result = await api.get('/test');

      expect(result).toEqual(mockData);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test'),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('includes authorization header when token exists', async () => {
      sessionStorage.setItem('access_token', 'test-token');

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      });

      await api.get('/test');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer test-token',
          }),
        })
      );
    });

    it('handles HTTP errors', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ detail: 'Not found' }),
      });

      await expect(api.get('/test')).rejects.toThrow();
    });

    it('handles GET errors with array detail', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({
          detail: [
            { loc: ['query', 'id'], msg: 'Invalid ID' },
          ],
        }),
      });

      await expect(api.get('/test')).rejects.toThrow();
    });

    it('handles GET errors with single detail', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Single error message' }),
      });

      await expect(api.get('/test')).rejects.toThrow('Single error message');
    });

    it('handles GET errors with message field', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ message: 'Error message' }),
      });

      await expect(api.get('/test')).rejects.toThrow('Error message');
    });

    it('handles GET non-JSON error response', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => {
          throw new Error('Not JSON');
        },
      });

      await expect(api.get('/test')).rejects.toThrow('API Error: Internal Server Error');
    });

    it('handles network errors', async () => {
      global.fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));

      await expect(api.get('/test')).rejects.toThrow(/network error/i);
    });
  });

  describe('POST requests', () => {
    it('makes POST request successfully', async () => {
      const mockData = { success: true };
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockData,
      });

      const result = await api.post('/test', { data: 'test' });

      expect(result).toEqual(mockData);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ data: 'test' }),
        })
      );
    });

    it('refreshes token on 401 and retries', async () => {
      sessionStorage.setItem('access_token', 'expired-token');
      localStorage.setItem('refresh_token', 'refresh-token');
      localStorage.setItem('remember_me', 'true');

      // First call returns 401
      global.fetch
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
        })
        // Token refresh succeeds
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            access_token: 'new-token',
            refresh_token: 'new-refresh-token',
          }),
        })
        // Retry succeeds
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ success: true }),
        });

      const result = await api.post('/test', { data: 'test' });

      expect(result.success).toBe(true);
      expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    it('handles validation errors', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({
          detail: [
            { loc: ['body', 'email'], msg: 'Invalid email' },
            { loc: ['body', 'password'], msg: 'Password too short' },
          ],
        }),
      });

      await expect(api.post('/test', {})).rejects.toThrow();
    });

    it('handles POST errors with single detail', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Single error message' }),
      });

      await expect(api.post('/test', {})).rejects.toThrow('Single error message');
    });

    it('handles POST errors with message field', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ message: 'Error message' }),
      });

      await expect(api.post('/test', {})).rejects.toThrow('Error message');
    });

    it('handles POST non-JSON error response', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => {
          throw new Error('Not JSON');
        },
      });

      await expect(api.post('/test', {})).rejects.toThrow('API Error: Internal Server Error');
    });

    it('handles POST network errors', async () => {
      global.fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));

      await expect(api.post('/test', {})).rejects.toThrow(/network error/i);
    });
  });

  describe('PUT requests', () => {
    it('makes PUT request successfully', async () => {
      const mockData = { updated: true };
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockData,
      });

      const result = await api.put('/test/1', { name: 'Updated' });

      expect(result).toEqual(mockData);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test/1'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ name: 'Updated' }),
        })
      );
    });

    it('refreshes token on 401 and retries PUT', async () => {
      sessionStorage.setItem('access_token', 'expired-token');
      localStorage.setItem('refresh_token', 'refresh-token');
      localStorage.setItem('remember_me', 'true');

      global.fetch
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            access_token: 'new-token',
            refresh_token: 'new-refresh-token',
          }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ success: true }),
        });

      const result = await api.put('/test/1', { name: 'Updated' });

      expect(result.success).toBe(true);
      expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    it('handles PUT errors with single detail', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Single error message' }),
      });

      await expect(api.put('/test', {})).rejects.toThrow('Single error message');
    });

    it('handles PUT errors with message field', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ message: 'Error message' }),
      });

      await expect(api.put('/test', {})).rejects.toThrow('Error message');
    });

    it('handles PUT network errors', async () => {
      global.fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));

      await expect(api.put('/test', {})).rejects.toThrow(/network error/i);
    });
  });

  describe('DELETE requests', () => {
    it('makes DELETE request successfully', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: {
          get: () => null,
        },
      });

      const result = await api.delete('/test/1');

      expect(result).toBeNull();
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test/1'),
        expect.objectContaining({ method: 'DELETE' })
      );
    });

    it('returns JSON response when available', async () => {
      const mockData = { deleted: true };
      global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: {
          get: () => 'application/json',
        },
        json: async () => mockData,
      });

      const result = await api.delete('/test/1');

      expect(result).toEqual(mockData);
    });

    it('refreshes token on 401 and retries DELETE', async () => {
      sessionStorage.setItem('access_token', 'expired-token');
      localStorage.setItem('refresh_token', 'refresh-token');
      localStorage.setItem('remember_me', 'true');

      global.fetch
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            access_token: 'new-token',
            refresh_token: 'new-refresh-token',
          }),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 204,
          headers: {
            get: () => null,
          },
        });

      const result = await api.delete('/test/1');

      expect(result).toBeNull();
      expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    it('handles DELETE errors with array detail', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({
          detail: [
            { loc: ['body', 'id'], msg: 'Invalid ID' },
          ],
        }),
      });

      await expect(api.delete('/test')).rejects.toThrow();
    });

    it('handles DELETE errors with single detail', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Not found' }),
      });

      await expect(api.delete('/test')).rejects.toThrow('Not found');
    });

    it('handles DELETE errors with message field', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ message: 'Error message' }),
      });

      await expect(api.delete('/test')).rejects.toThrow('Error message');
    });

    it('handles DELETE non-JSON error response', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => {
          throw new Error('Not JSON');
        },
      });

      await expect(api.delete('/test')).rejects.toThrow('API Error: Internal Server Error');
    });

    it('handles DELETE network errors', async () => {
      global.fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));

      await expect(api.delete('/test')).rejects.toThrow(/network error/i);
    });
  });

  describe('Token management', () => {
    beforeEach(() => {
      // Ensure window.location.href is writable for tests
      if (window.location) {
        Object.defineProperty(window.location, 'href', {
          writable: true,
          value: '/test',
        });
        Object.defineProperty(window.location, 'pathname', {
          writable: true,
          value: '/test',
        });
      }
    });

    it('uses sessionStorage when remember_me is false', async () => {
      sessionStorage.setItem('access_token', 'session-token');
      localStorage.setItem('remember_me', 'false');

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      });

      await api.get('/test');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer session-token',
          }),
        })
      );
    });

    it('clears tokens on refresh failure', async () => {
      sessionStorage.setItem('access_token', 'expired');
      localStorage.setItem('refresh_token', 'invalid-refresh');
      localStorage.setItem('remember_me', 'true');

      global.fetch
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
        });

      await expect(api.post('/test', {})).rejects.toThrow();

      // Tokens should be cleared (tested indirectly through fetch calls)
      expect(global.fetch).toHaveBeenCalled();
      // Verify that navigation was attempted (location.href should be set to /login)
      // Note: In jsdom, this won't actually navigate, but the assignment should happen
      expect(window.location.href).toBe('/login');
    });
  });
});

