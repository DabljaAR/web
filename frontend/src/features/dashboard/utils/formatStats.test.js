import { describe, it, expect } from 'vitest';
import { formatStats, formatCurrency } from './formatStats';

describe('formatStats Functions', () => {
  describe('formatStats', () => {
    it('formats stats object correctly', () => {
      const stats = {
        totalUsers: 1000,
        totalRevenue: 50000,
        activeProjects: 25,
        completionRate: 85,
      };

      const formatted = formatStats(stats);

      expect(formatted.totalUsers).toBe(1000);
      expect(formatted.totalRevenue).toContain('$50,000');
      expect(formatted.activeProjects).toBe(25);
      expect(formatted.completionRate).toBe('85%');
    });

    it('handles null/undefined stats', () => {
      expect(formatStats(null)).toBeNull();
      expect(formatStats(undefined)).toBeNull();
    });

    it('handles missing properties with defaults', () => {
      const stats = {};
      const formatted = formatStats(stats);

      expect(formatted.totalUsers).toBe(0);
      expect(formatted.totalRevenue).toContain('$0');
      expect(formatted.activeProjects).toBe(0);
      expect(formatted.completionRate).toBe('0%');
    });

    it('handles partial stats', () => {
      const stats = {
        totalUsers: 500,
      };

      const formatted = formatStats(stats);

      expect(formatted.totalUsers).toBe(500);
      expect(formatted.totalRevenue).toContain('$0');
      expect(formatted.activeProjects).toBe(0);
    });
  });

  describe('formatCurrency', () => {
    it('formats currency correctly', () => {
      expect(formatCurrency(1000)).toContain('$1,000');
      expect(formatCurrency(50000)).toContain('$50,000');
      expect(formatCurrency(1234567)).toContain('$1,234,567');
    });

    it('handles zero', () => {
      expect(formatCurrency(0)).toContain('$0');
    });

    it('handles decimal values', () => {
      expect(formatCurrency(1234.56)).toContain('$1,234.56');
    });

    it('handles negative values', () => {
      const result = formatCurrency(-1000);
      expect(result).toBeDefined();
    });
  });
});



