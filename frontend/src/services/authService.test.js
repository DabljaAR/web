import { describe, it, expect, vi, beforeEach } from 'vitest';
import { authService } from './authService';
import api from './api';

// Mock the api module
vi.mock('./api');

describe('AuthService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('login', () => {
    it('calls api.post with correct endpoint and credentials', async () => {
      const mockResponse = {
        access_token: 'token123',
        refresh_token: 'refresh123',
        user: { id: 1, username: 'testuser' },
      };

      api.post.mockResolvedValueOnce(mockResponse);

      const result = await authService.login('testuser', 'password123');

      expect(api.post).toHaveBeenCalledWith('/login', {
        username: 'testuser',
        password: 'password123',
      });
      expect(result).toEqual(mockResponse);
    });

    it('handles login errors', async () => {
      const error = new Error('Invalid credentials');
      api.post.mockRejectedValueOnce(error);

      await expect(authService.login('wrong', 'wrong')).rejects.toThrow();
    });
  });

  describe('register', () => {
    it('calls api.post with user data', async () => {
      const userData = {
        username: 'newuser',
        email: 'new@example.com',
        password: 'password123',
      };

      const mockResponse = {
        access_token: 'token123',
        refresh_token: 'refresh123',
        user: { id: 2, username: 'newuser' },
      };

      api.post.mockResolvedValueOnce(mockResponse);

      const result = await authService.register(userData);

      expect(api.post).toHaveBeenCalledWith('/signup', userData);
      expect(result).toEqual(mockResponse);
    });
  });

  describe('logout', () => {
    it('calls api.post with logout endpoint', async () => {
      api.post.mockResolvedValueOnce({ success: true });

      await authService.logout();

      expect(api.post).toHaveBeenCalledWith('/auth/logout');
    });
  });

  describe('getCurrentUser', () => {
    it('calls api.get with correct endpoint', async () => {
      const mockUser = {
        id: 1,
        username: 'testuser',
        email: 'test@example.com',
      };

      api.get.mockResolvedValueOnce(mockUser);

      const result = await authService.getCurrentUser();

      expect(api.get).toHaveBeenCalledWith('/auth/me');
      expect(result).toEqual(mockUser);
    });
  });

  describe('refreshToken', () => {
    it('calls api.post with refresh token', async () => {
      const mockResponse = {
        access_token: 'new-token',
        refresh_token: 'new-refresh-token',
      };

      api.post.mockResolvedValueOnce(mockResponse);

      const result = await authService.refreshToken('refresh-token');

      expect(api.post).toHaveBeenCalledWith('/auth/refresh', {
        refresh_token: 'refresh-token',
      });
      expect(result).toEqual(mockResponse);
    });
  });
});



