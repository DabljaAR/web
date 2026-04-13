import React from 'react';
import { render } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { LanguageProvider } from '../contexts/LanguageContext';
import { ThemeProvider } from '../contexts/ThemeContext';

// Custom render function that includes providers
export const renderWithProviders = (ui, options = {}) => {
  const {
    route = '/',
    language = 'en',
    theme = 'light',
    ...renderOptions
  } = options;

  // Set localStorage for language and theme
  if (language) {
    localStorage.setItem('language', language);
  }
  if (theme) {
    localStorage.setItem('theme', theme);
  }

  const Wrapper = ({ children }) => {
    return (
      <BrowserRouter>
        <ThemeProvider>
          <LanguageProvider>
            {children}
          </LanguageProvider>
        </ThemeProvider>
      </BrowserRouter>
    );
  };

  return render(ui, { wrapper: Wrapper, ...renderOptions });
};

// Re-export everything from React Testing Library
export * from '@testing-library/react';
export { default as userEvent } from '@testing-library/user-event';

