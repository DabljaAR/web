import React from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '../contexts/ThemeContext';
import { LanguageProvider } from '../contexts/LanguageContext';

export const renderWithProviders = (ui, options = {}) => {
  const Wrapper = ({ children }) => (
    <MemoryRouter>
      <ThemeProvider>
        <LanguageProvider>
          {children}
        </LanguageProvider>
      </ThemeProvider>
    </MemoryRouter>
  );
  return render(ui, { wrapper: Wrapper, ...options });
};
