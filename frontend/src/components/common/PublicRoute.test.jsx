import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PublicRoute from './PublicRoute';
import { useAuth } from '../../hooks/useAuth';

// Mock the useAuth hook
vi.mock('../../hooks/useAuth');

describe('PublicRoute Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders children when user is not authenticated', () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      loading: false,
    });

    render(
      <MemoryRouter>
        <PublicRoute>
          <div>Public Content</div>
        </PublicRoute>
      </MemoryRouter>
    );

    expect(screen.getByText(/public content/i)).toBeInTheDocument();
  });

  it('shows loading state when loading', () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      loading: true,
    });

    render(
      <MemoryRouter>
        <PublicRoute>
          <div>Public Content</div>
        </PublicRoute>
      </MemoryRouter>
    );

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText(/public content/i)).not.toBeInTheDocument();
  });

  it('redirects to dashboard when authenticated', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      loading: false,
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <PublicRoute>
          <div>Public Content</div>
        </PublicRoute>
      </MemoryRouter>
    );

    // The Navigate component should redirect, but in test we check that public content is not shown
    expect(screen.queryByText(/public content/i)).not.toBeInTheDocument();
  });

  it('handles authentication state changes', () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      loading: false,
    });

    const { rerender } = render(
      <MemoryRouter>
        <PublicRoute>
          <div>Public Content</div>
        </PublicRoute>
      </MemoryRouter>
    );

    expect(screen.getByText(/public content/i)).toBeInTheDocument();

    // Simulate login
    useAuth.mockReturnValue({
      isAuthenticated: true,
      loading: false,
    });

    rerender(
      <MemoryRouter>
        <PublicRoute>
          <div>Public Content</div>
        </PublicRoute>
      </MemoryRouter>
    );

    expect(screen.queryByText(/public content/i)).not.toBeInTheDocument();
  });
});



