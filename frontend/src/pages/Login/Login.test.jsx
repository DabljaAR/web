import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import Login from './Login';
import { useAuth } from '../../hooks/useAuth';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { authService } from '../../services/authService';

const mockNavigate = vi.fn();

// Mock dependencies
vi.mock('../../hooks/useAuth');
vi.mock('../../hooks/useTranslation');
vi.mock('../../contexts/ThemeContext');
vi.mock('../../contexts/LanguageContext');
vi.mock('../../services/authService');
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('Login Page', () => {
  const mockLogin = vi.fn();
  const mockT = vi.fn((key) => key);
  const mockToggleTheme = vi.fn();
  const mockToggleLanguage = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
    useAuth.mockReturnValue({
      login: mockLogin,
    });
    useTranslation.mockReturnValue({ t: mockT });
    useTheme.mockReturnValue({ toggleTheme: mockToggleTheme });
    useLanguage.mockReturnValue({ language: 'en', toggleLanguage: mockToggleLanguage });
  });

  it('renders login form', () => {
    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    expect(screen.getByText(/login.title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/login.emailLabel/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/login.passwordLabel/i)).toBeInTheDocument();
  });

  it('handles form input changes', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    const emailInput = screen.getByLabelText(/login.emailLabel/i);
    const passwordInput = screen.getByLabelText(/login.passwordLabel/i);

    await user.type(emailInput, 'xewib@mailinator.com');
    await user.type(passwordInput, 'Password1');

    expect(emailInput.value).toBe('xewib@mailinator.com');
    expect(passwordInput.value).toBe('Password1');
  });

  it('submits form with valid credentials', async () => {
    const user = userEvent.setup();
    const mockResponse = {
      access_token: 'token123',
      refresh_token: 'refresh123',
      user: { id: 1, username: 'testuser' },
    };

    authService.login.mockResolvedValueOnce(mockResponse);

    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/login.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/login.passwordLabel/i), 'password123');
    
    // Find the submit button by its type attribute
    const form = screen.getByLabelText(/login.emailLabel/i).closest('form');
    const submitButton = form.querySelector('button[type="submit"]');
    
    expect(submitButton).toBeInTheDocument();
    await user.click(submitButton);

    await waitFor(() => {
      expect(authService.login).toHaveBeenCalledWith('test@example.com', 'password123');
    }, { timeout: 3000 });

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
    }, { timeout: 3000 });
  });

  it('handles login errors', async () => {
    const user = userEvent.setup();
    const error = new Error('Invalid credentials');
    authService.login.mockRejectedValueOnce(error);

    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/login.emailLabel/i), 'wrong@example.com');
    await user.type(screen.getByLabelText(/login.passwordLabel/i), 'wrongpass');
    
    // Find the submit button by its type attribute
    const form = screen.getByLabelText(/login.emailLabel/i).closest('form');
    const submitButton = form.querySelector('button[type="submit"]');
    
    expect(submitButton).toBeInTheDocument();
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('toggles remember me checkbox', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    const rememberCheckbox = screen.getByLabelText(/login.rememberMe/i);
    expect(rememberCheckbox.checked).toBe(false);

    await user.click(rememberCheckbox);
    expect(rememberCheckbox.checked).toBe(true);
  });

  it('handles Google login', async () => {
    const user = userEvent.setup();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    const googleButton = screen.getByRole('button', { name: /login.signInGoogle/i });
    await user.click(googleButton);

    expect(alertSpy).toHaveBeenCalledWith('Google login (Demo)');
    alertSpy.mockRestore();
  });

  it('shows loading state during submission', async () => {
    const user = userEvent.setup();
    authService.login.mockImplementation(() => new Promise(() => {})); // Never resolves

    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/login.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/login.passwordLabel/i), 'password123');
    
    // Find the submit button by its type attribute
    const form = screen.getByLabelText(/login.emailLabel/i).closest('form');
    const submitButton = form.querySelector('button[type="submit"]');
    
    expect(submitButton).toBeInTheDocument();
    expect(submitButton).not.toBeDisabled();
    
    // Click the button to trigger form submission
    await user.click(submitButton);

    // Wait for loading state to appear
    await waitFor(() => {
      expect(screen.getByText(/signing in/i)).toBeInTheDocument();
    }, { timeout: 2000 });

    // Button should be disabled during loading
    await waitFor(() => {
      expect(submitButton).toBeDisabled();
    }, { timeout: 1000 });
    
    // Verify that authService.login was called
    expect(authService.login).toHaveBeenCalledWith('test@example.com', 'password123');
  });

  it('toggles theme and language', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

    const themeButton = screen.getByLabelText(/toggle theme/i);
    const langButton = screen.getByLabelText(/switch language/i);

    await user.click(themeButton);
    await user.click(langButton);

    expect(mockToggleTheme).toHaveBeenCalled();
    expect(mockToggleLanguage).toHaveBeenCalled();
  });
});

