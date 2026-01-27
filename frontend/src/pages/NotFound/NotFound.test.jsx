import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import NotFound from './NotFound';
import { useTranslation } from '../../hooks/useTranslation';

// Mock dependencies
vi.mock('../../hooks/useTranslation');
vi.mock('../../components/layout/Navbar', () => ({
  default: () => <nav data-testid="navbar">Navbar</nav>,
}));
vi.mock('../../components/layout/Footer', () => ({
  default: () => <footer data-testid="footer">Footer</footer>,
}));

describe('NotFound Page', () => {
  const mockT = vi.fn((key) => key);

  beforeEach(() => {
    vi.clearAllMocks();
    useTranslation.mockReturnValue({ t: mockT });
  });

  it('renders 404 message', () => {
    render(
      <BrowserRouter>
        <NotFound />
      </BrowserRouter>
    );

    expect(screen.getByText(/404/i)).toBeInTheDocument();
  });

  it('renders navbar and footer', () => {
    render(
      <BrowserRouter>
        <NotFound />
      </BrowserRouter>
    );

    expect(screen.getByTestId('navbar')).toBeInTheDocument();
    expect(screen.getByTestId('footer')).toBeInTheDocument();
  });

  it('has button to navigate home', () => {
    render(
      <BrowserRouter>
        <NotFound />
      </BrowserRouter>
    );

    const homeButton = screen.getByRole('button', { name: /notFound.goHome/i });
    expect(homeButton).toBeInTheDocument();
  });
});


