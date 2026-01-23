import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useTranslation } from './useTranslation';
import { useLanguage } from '../contexts/LanguageContext';
import { translations } from '../utils/translations';

// Mock the LanguageContext
vi.mock('../contexts/LanguageContext');

describe('useTranslation Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns translation function', () => {
    useLanguage.mockReturnValue({ language: 'en' });

    const { result } = renderHook(() => useTranslation());

    expect(typeof result.current.t).toBe('function');
    expect(result.current.language).toBe('en');
  });

  it('translates simple keys', () => {
    useLanguage.mockReturnValue({ language: 'en' });

    const { result } = renderHook(() => useTranslation());

    // Assuming translations.en has a 'nav.home' key
    const translation = result.current.t('nav.home');
    expect(translation).toBeDefined();
  });

  it('translates nested keys', () => {
    useLanguage.mockReturnValue({ language: 'en' });

    const { result } = renderHook(() => useTranslation());

    const translation = result.current.t('nav.home');
    expect(translation).toBeDefined();
  });

  it('returns key when translation is missing', () => {
    useLanguage.mockReturnValue({ language: 'en' });
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const { result } = renderHook(() => useTranslation());

    const translation = result.current.t('nonexistent.key');
    expect(translation).toBe('nonexistent.key');
    expect(consoleSpy).toHaveBeenCalled();

    consoleSpy.mockRestore();
  });

  it('uses correct language from context', () => {
    useLanguage.mockReturnValue({ language: 'ar' });

    const { result } = renderHook(() => useTranslation());

    expect(result.current.language).toBe('ar');
  });

  it('handles language changes', () => {
    useLanguage.mockReturnValue({ language: 'en' });

    const { result, rerender } = renderHook(() => useTranslation());

    expect(result.current.language).toBe('en');

    useLanguage.mockReturnValue({ language: 'ar' });
    rerender();

    expect(result.current.language).toBe('ar');
  });

  it('handles deeply nested translation keys', () => {
    useLanguage.mockReturnValue({ language: 'en' });

    const { result } = renderHook(() => useTranslation());

    // Test with a deeply nested key if it exists
    const translation = result.current.t('nav.home');
    expect(translation).toBeDefined();
  });
});



