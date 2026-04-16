import React from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '../contexts/ThemeContext';
import { LanguageProvider } from '../contexts/LanguageContext';

export const renderWithProviders = (ui, options = {}) => {
  // Backward-compatible custom options (route/language/theme) while still supporting
  // standard RTL render options. Prefer passing RTL options via `renderOptions`.
  const {
    route,
    language,
    theme,
    renderOptions,
    ...rtlOptionsFromRoot
  } = options;

  // Keep tests deterministic: ensure providers always start from known settings.
  localStorage.setItem('language', typeof language === 'string' ? language : 'en');
  localStorage.setItem('theme', typeof theme === 'string' ? theme : 'light');

  const rtlOptions = {
    ...rtlOptionsFromRoot,
    ...(renderOptions || {}),
  };

  const UserWrapper = rtlOptions.wrapper;
  const { wrapper: _ignoredWrapper, ...rtlOptionsWithoutWrapper } = rtlOptions;

  const initialEntries =
    route == null ? undefined : (Array.isArray(route) ? route : [route]);

  const Wrapper = ({ children }) => {
    const content = UserWrapper ? <UserWrapper>{children}</UserWrapper> : children;

    // Only pass `initialEntries` when explicitly provided to avoid overriding
    // MemoryRouter defaults.
    return initialEntries ? (
      <MemoryRouter initialEntries={initialEntries}>
        <ThemeProvider>
          <LanguageProvider>{content}</LanguageProvider>
        </ThemeProvider>
      </MemoryRouter>
    ) : (
      <MemoryRouter>
        <ThemeProvider>
          <LanguageProvider>{content}</LanguageProvider>
        </ThemeProvider>
      </MemoryRouter>
    );
  };

  return render(ui, { wrapper: Wrapper, ...rtlOptionsWithoutWrapper });
};
