import { describe, it, expect } from 'vitest';
import { API_ENDPOINTS, APP_NAME, APP_VERSION, STORAGE_KEYS, ROUTES } from './constants';

describe('Constants', () => {
  describe('API_ENDPOINTS', () => {
    it('defines auth endpoints', () => {
      expect(API_ENDPOINTS.AUTH).toBeDefined();
      expect(API_ENDPOINTS.AUTH.LOGIN).toBe('/auth/login');
      expect(API_ENDPOINTS.AUTH.REGISTER).toBe('/auth/register');
      expect(API_ENDPOINTS.AUTH.LOGOUT).toBe('/auth/logout');
      expect(API_ENDPOINTS.AUTH.ME).toBe('/auth/me');
    });

    it('defines user endpoints', () => {
      expect(API_ENDPOINTS.USERS).toBeDefined();
      expect(API_ENDPOINTS.USERS.LIST).toBe('/users');
      expect(API_ENDPOINTS.USERS.DETAIL).toBe('/users/:id');
    });
  });

  describe('APP_NAME', () => {
    it('has correct app name', () => {
      expect(APP_NAME).toBe('DabljaAR');
    });
  });

  describe('APP_VERSION', () => {
    it('has correct version', () => {
      expect(APP_VERSION).toBe('1.0.0');
    });
  });

  describe('STORAGE_KEYS', () => {
    it('defines storage keys', () => {
      expect(STORAGE_KEYS.AUTH_TOKEN).toBe('authToken');
      expect(STORAGE_KEYS.USER_DATA).toBe('userData');
      expect(STORAGE_KEYS.THEME).toBe('theme');
    });
  });

  describe('ROUTES', () => {
    it('defines route paths', () => {
      expect(ROUTES.HOME).toBe('/');
      expect(ROUTES.ABOUT).toBe('/about');
      expect(ROUTES.LOGIN).toBe('/login');
      expect(ROUTES.DASHBOARD).toBe('/dashboard');
      expect(ROUTES.NOT_FOUND).toBe('*');
    });
  });
});



