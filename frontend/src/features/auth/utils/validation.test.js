import { describe, it, expect } from 'vitest';
import { validateEmail, validatePassword, validateLoginForm } from './validation';

describe('Validation Functions', () => {
  describe('validateEmail', () => {
    it('validates correct email addresses', () => {
      expect(validateEmail('test@example.com')).toBe(true);
      expect(validateEmail('user.name@domain.co.uk')).toBe(true);
      expect(validateEmail('user+tag@example.com')).toBe(true);
    });

    it('rejects invalid email addresses', () => {
      expect(validateEmail('invalid')).toBe(false);
      expect(validateEmail('@example.com')).toBe(false);
      expect(validateEmail('user@')).toBe(false);
      expect(validateEmail('user@domain')).toBe(false);
      expect(validateEmail('')).toBe(false);
    });
  });

  describe('validatePassword', () => {
    it('validates correct passwords', () => {
      expect(validatePassword('Password123')).toBe(true);
      expect(validatePassword('MyP@ssw0rd')).toBe(true);
      expect(validatePassword('Test1234')).toBe(true);
    });

    it('rejects passwords without uppercase', () => {
      expect(validatePassword('password123')).toBe(false);
    });

    it('rejects passwords without lowercase', () => {
      expect(validatePassword('PASSWORD123')).toBe(false);
    });

    it('rejects passwords without numbers', () => {
      expect(validatePassword('Password')).toBe(false);
    });

    it('rejects passwords shorter than 8 characters', () => {
      expect(validatePassword('Pass123')).toBe(false);
    });

    it('rejects empty passwords', () => {
      expect(validatePassword('')).toBe(false);
    });
  });

  describe('validateLoginForm', () => {
    it('validates correct form data', () => {
      const formData = {
        email: 'test@example.com',
        password: 'password123',
      };

      const result = validateLoginForm(formData);
      expect(result.isValid).toBe(true);
      expect(Object.keys(result.errors)).toHaveLength(0);
    });

    it('returns error for missing email', () => {
      const formData = {
        email: '',
        password: 'password123',
      };

      const result = validateLoginForm(formData);
      expect(result.isValid).toBe(false);
      expect(result.errors.email).toBe('Email is required');
    });

    it('returns error for invalid email format', () => {
      const formData = {
        email: 'invalid-email',
        password: 'password123',
      };

      const result = validateLoginForm(formData);
      expect(result.isValid).toBe(false);
      expect(result.errors.email).toBe('Invalid email format');
    });

    it('returns error for missing password', () => {
      const formData = {
        email: 'test@example.com',
        password: '',
      };

      const result = validateLoginForm(formData);
      expect(result.isValid).toBe(false);
      expect(result.errors.password).toBe('Password is required');
    });

    it('returns multiple errors for invalid form', () => {
      const formData = {
        email: 'invalid',
        password: '',
      };

      const result = validateLoginForm(formData);
      expect(result.isValid).toBe(false);
      expect(result.errors.email).toBeDefined();
      expect(result.errors.password).toBeDefined();
    });
  });
});



