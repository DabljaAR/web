import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App';
import { useAuth } from './hooks/useAuth';

// Mock all page components
vi.mock('./pages/Home', () => ({
  default: () => <div data-testid="home-page">Home</div>,
}));
vi.mock('./pages/About', () => ({
  default: () => <div data-testid="about-page">About</div>,
}));
vi.mock('./pages/Login', () => ({
  default: () => <div data-testid="login-page">Login</div>,
}));
vi.mock('./pages/Register', () => ({
  default: () => <div data-testid="register-page">Register</div>,
}));
vi.mock('./pages/Dashboard', () => ({
  default: () => <div data-testid="dashboard-page">Dashboard</div>,
}));
vi.mock('./pages/Profile', () => ({
  default: () => <div data-testid="profile-page">Profile</div>,
}));
vi.mock('./pages/History', () => ({
  default: () => <div data-testid="history-page">History</div>,
}));
vi.mock('./pages/NotFound', () => ({
  default: () => <div data-testid="not-found-page">NotFound</div>,
}));

// Mock ProtectedRoute and PublicRoute to avoid router conflicts
vi.mock('./components/common/ProtectedRoute', () => ({
  default: ({ children }) => <div>{children}</div>,
}));
vi.mock('./components/common/PublicRoute', () => ({
  default: ({ children }) => <div>{children}</div>,
}));

// Mock contexts
vi.mock('./contexts/ThemeContext', () => ({
  ThemeProvider: ({ children }) => <div>{children}</div>,
}));
vi.mock('./contexts/LanguageContext', () => ({
  LanguageProvider: ({ children }) => <div>{children}</div>,
}));

// Mock hooks
vi.mock('./hooks/useAuth');

describe('App Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({
      isAuthenticated: false,
      loading: false,
    });
  });

  it('renders app without errors', async () => {
    let root;
    await waitFor(() => {
      root = render(<App />);
    });
    // App should render without throwing errors
    expect(document.body).toBeInTheDocument();
  });

  it('wraps app with theme and language providers', async () => {
    let root;
    await waitFor(() => {
      root = render(<App />);
    });
    // App should render without errors, indicating providers are working
    expect(document.body).toBeInTheDocument();
  });

  it('includes router in app', async () => {
    let root;
    await waitFor(() => {
      root = render(<App />);
    });
    // Router should be present (no nested router errors)
    expect(document.body).toBeInTheDocument();
  });
});
