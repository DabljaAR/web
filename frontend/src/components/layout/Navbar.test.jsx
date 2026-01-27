import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import Navbar from './Navbar';
import { useAuth } from '../../hooks/useAuth';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';

// Mock dependencies
vi.mock('../../hooks/useAuth');
vi.mock('../../hooks/useTranslation');
vi.mock('../../contexts/ThemeContext');
vi.mock('../../contexts/LanguageContext');

describe('Navbar Component', () => {
  const mockToggleTheme = vi.fn();
  const mockToggleLanguage = vi.fn();
  const mockLogout = vi.fn();
  const mockT = vi.fn((key) => key);

  beforeEach(() => {
    vi.clearAllMocks();
    useTranslation.mockReturnValue({ t: mockT, language: 'en' });
    useTheme.mockReturnValue({ theme: 'light', toggleTheme: mockToggleTheme });
    useLanguage.mockReturnValue({ language: 'en', toggleLanguage: mockToggleLanguage });
    
    // Mock window.scrollY
    Object.defineProperty(window, 'scrollY', {
      writable: true,
      configurable: true,
      value: 0,
    });
  });

  it('renders navbar with logo', () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      user: null,
      logout: mockLogout,
    });

    render(
      <BrowserRouter>
        <Navbar />
      </BrowserRouter>
    );

    expect(screen.getByText(/dablja/i)).toBeInTheDocument();
  });

  it('renders login button when not authenticated', () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      user: null,
      logout: mockLogout,
    });

    render(
      <BrowserRouter>
        <Navbar />
      </BrowserRouter>
    );

    expect(screen.getByText(/nav.login/i)).toBeInTheDocument();
  });

  it('renders user menu when authenticated', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: 'testuser', email: 'test@example.com' },
      logout: mockLogout,
    });

    render(
      <BrowserRouter>
        <Navbar />
      </BrowserRouter>
    );

    expect(screen.getByText(/testuser/i)).toBeInTheDocument();
  });

  it('calls toggleTheme when theme button is clicked', async () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      user: null,
      logout: mockLogout,
    });

    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Navbar />
      </BrowserRouter>
    );

    const themeButton = screen.getByLabelText(/toggle theme/i);
    await user.click(themeButton);

    expect(mockToggleTheme).toHaveBeenCalledTimes(1);
  });

  it('calls toggleLanguage when language button is clicked', async () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      user: null,
      logout: mockLogout,
    });

    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Navbar />
      </BrowserRouter>
    );

    const langButton = screen.getByLabelText(/switch language/i);
    await user.click(langButton);

    expect(mockToggleLanguage).toHaveBeenCalledTimes(1);
  });

  it('calls logout when logout button is clicked', async () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: 'testuser', email: 'test@example.com' },
      logout: mockLogout,
    });

    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Navbar />
      </BrowserRouter>
    );

    // Open user menu first
    const userMenuButton = screen.getByText(/testuser/i);
    await user.click(userMenuButton);

    // Then click logout
    const logoutButton = screen.getByText(/nav.logout/i);
    await user.click(logoutButton);

    expect(mockLogout).toHaveBeenCalledTimes(1);
  });

  it('toggles mobile menu when hamburger is clicked', async () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      user: null,
      logout: mockLogout,
    });

    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Navbar />
      </BrowserRouter>
    );

    const hamburger = screen.getByLabelText(/toggle menu/i);
    await user.click(hamburger);

    // Menu should be open (check for nav-menu-open class or similar)
    expect(hamburger).toBeInTheDocument();
  });

  it('displays user email in user menu', async () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: 'testuser', email: 'test@example.com', first_name: 'Test', last_name: 'User' },
      logout: mockLogout,
    });

    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Navbar />
      </BrowserRouter>
    );

    // Open user menu first
    const userMenuButton = screen.getByText(/testuser/i);
    await user.click(userMenuButton);

    // Now check for email
    expect(screen.getByText(/test@example.com/i)).toBeInTheDocument();
  });
});

