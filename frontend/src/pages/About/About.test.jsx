import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import About from './About';
import { useTranslation } from '../../hooks/useTranslation';

// Mock dependencies
vi.mock('../../hooks/useTranslation');
vi.mock('../../components/layout/Navbar', () => ({
  default: () => <nav data-testid="navbar">Navbar</nav>,
}));
vi.mock('../../components/layout/Footer', () => ({
  default: () => <footer data-testid="footer">Footer</footer>,
}));

describe('About Page', () => {
  const mockT = vi.fn((key) => key);

  beforeEach(() => {
    vi.clearAllMocks();
    useTranslation.mockReturnValue({ t: mockT });
  });

  it('renders about page content', () => {
    render(
      <BrowserRouter>
        <About />
      </BrowserRouter>
    );

    expect(screen.getByTestId('navbar')).toBeInTheDocument();
    expect(screen.getByTestId('footer')).toBeInTheDocument();
  });
});



