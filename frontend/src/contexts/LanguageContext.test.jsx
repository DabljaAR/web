import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { LanguageProvider, useLanguage } from './LanguageContext';

describe('LanguageContext', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('provides default language as en', () => {
    const wrapper = ({ children }) => (
      <LanguageProvider>{children}</LanguageProvider>
    );

    const { result } = renderHook(() => useLanguage(), { wrapper });

    expect(result.current.language).toBe('en');
  });

  it('loads language from localStorage', () => {
    localStorage.setItem('language', 'ar');

    const wrapper = ({ children }) => (
      <LanguageProvider>{children}</LanguageProvider>
    );

    const { result } = renderHook(() => useLanguage(), { wrapper });

    expect(result.current.language).toBe('ar');
  });

  it('toggles language between en and ar', () => {
    const wrapper = ({ children }) => (
      <LanguageProvider>{children}</LanguageProvider>
    );

    const { result } = renderHook(() => useLanguage(), { wrapper });

    expect(result.current.language).toBe('en');

    act(() => {
      result.current.toggleLanguage();
    });

    expect(result.current.language).toBe('ar');

    act(() => {
      result.current.toggleLanguage();
    });

    expect(result.current.language).toBe('en');
  });

  it('saves language to localStorage', () => {
    const wrapper = ({ children }) => (
      <LanguageProvider>{children}</LanguageProvider>
    );

    const { result } = renderHook(() => useLanguage(), { wrapper });

    act(() => {
      result.current.toggleLanguage();
    });

    expect(localStorage.getItem('language')).toBe('ar');
  });

  it('sets document language attribute', () => {
    const wrapper = ({ children }) => (
      <LanguageProvider>{children}</LanguageProvider>
    );

    const { result } = renderHook(() => useLanguage(), { wrapper });

    act(() => {
      result.current.toggleLanguage();
    });

    expect(document.documentElement.lang).toBe('ar');
  });

  it('sets document direction for RTL languages', () => {
    const wrapper = ({ children }) => (
      <LanguageProvider>{children}</LanguageProvider>
    );

    const { result } = renderHook(() => useLanguage(), { wrapper });

    act(() => {
      result.current.toggleLanguage();
    });

    expect(document.documentElement.dir).toBe('rtl');
  });

  it('throws error when used outside provider', () => {
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => {
      renderHook(() => useLanguage());
    }).toThrow('useLanguage must be used within a LanguageProvider');

    consoleSpy.mockRestore();
  });
});



