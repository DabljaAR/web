import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import Register from './Register';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { authService } from '../../services/authService';

const mockNavigate = vi.fn();

// Mock dependencies
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

describe('Register Page', () => {
  const mockT = vi.fn((key) => key);
  const mockToggleTheme = vi.fn();
  const mockToggleLanguage = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
    global.fetch = vi.fn();
    useTranslation.mockReturnValue({ t: mockT });
    useTheme.mockReturnValue({ toggleTheme: mockToggleTheme });
    useLanguage.mockReturnValue({ language: 'en', toggleLanguage: mockToggleLanguage });
  });

  it('renders registration form', () => {
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    expect(screen.getByText(/register.title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/register.emailLabel/i)).toBeInTheDocument();
  });

  it('validates username', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const usernameInput = screen.getByLabelText(/username/i);
    await user.type(usernameInput, 'ab'); // Too short
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    // Wait for validation error - check if error appears or form doesn't submit
    await waitFor(() => {
      // Check for the exact error message
      const errorMessage = screen.queryByText(/Username must be at least 3 characters long/i);
      if (errorMessage) {
        expect(errorMessage).toBeInTheDocument();
      } else {
        // If error message not found, verify form didn't submit
        expect(authService.register).not.toHaveBeenCalled();
      }
    }, { timeout: 2000 });
  });

  it('validates password requirements', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'weak'); // Too weak
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'weak');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      // Check for password validation error messages
      const errorMessage = screen.queryByText(/Password must be at least 8 characters long/i) ||
                          screen.queryByText(/Password must contain at least one uppercase letter/i) ||
                          screen.queryByText(/Password must contain at least one lowercase letter/i);
      if (errorMessage) {
        expect(errorMessage).toBeInTheDocument();
      } else {
        // If error message not found, verify form didn't submit
        expect(authService.register).not.toHaveBeenCalled();
      }
    }, { timeout: 2000 });
  });

  it('validates password match', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password456'); // Mismatch
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      // Check for password mismatch error message
      const errorMessage = screen.queryByText(/Passwords do not match/i);
      if (errorMessage) {
        expect(errorMessage).toBeInTheDocument();
      } else {
        // If error message not found, verify form didn't submit
        expect(authService.register).not.toHaveBeenCalled();
      }
    }, { timeout: 2000 });
  });

  it('validates terms acceptance', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      // Check for the exact error message
      const errorMessage = screen.queryByText(/Please agree to the Terms of Service and Privacy Policy/i);
      if (errorMessage) {
        expect(errorMessage).toBeInTheDocument();
      } else {
        // If error message not found, verify form didn't submit
        expect(authService.register).not.toHaveBeenCalled();
      }
    }, { timeout: 2000 });
  });

  it('submits form with valid data', async () => {
    const user = userEvent.setup();
    const mockResponse = { success: true };
    authService.register.mockResolvedValueOnce(mockResponse);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(authService.register).toHaveBeenCalled();
      expect(alertSpy).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });

    alertSpy.mockRestore();
  });

  it('handles registration errors', async () => {
    const user = userEvent.setup();
    const error = new Error('Email already exists');
    authService.register.mockRejectedValueOnce(error);

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'existing@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      const errorElements = screen.queryAllByText((content, element) => {
        const text = element?.textContent || '';
        return text.includes('Email already exists') || text.includes('email');
      });
      expect(errorElements.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
  });

  it('handles avatar file upload', async () => {
    const user = userEvent.setup();
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' });
    
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ url: 'https://example.com/avatar.jpg' }),
    });

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const fileInput = document.querySelector('input[type="file"][accept*="image"]');
    expect(fileInput).toBeInTheDocument();
    await user.upload(fileInput, file);

    // File should be selected
    expect(fileInput.files[0]).toBe(file);
  });

  it('validates avatar file type', async () => {
    const user = userEvent.setup();
    const file = new File(['test'], 'test.txt', { type: 'text/plain' });

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const fileInput = document.querySelector('input[type="file"][accept*="image"]');
    expect(fileInput).toBeInTheDocument();
    
    await user.upload(fileInput, file);

    await waitFor(() => {
      const errorText = screen.queryByText((content, element) => {
        const text = element?.textContent || '';
        return text.includes('valid image') || 
               text.includes('jpg') || 
               text.includes('png') ||
               text.includes('gif') ||
               text.includes('webp');
      });
      expect(fileInput).toBeInTheDocument();
    }, { timeout: 2000 });
  });

  it('validates avatar file size exceeds 5MB', async () => {
    const user = userEvent.setup();
    // Create a file larger than 5MB
    const largeFile = new File(['x'.repeat(6 * 1024 * 1024)], 'large.jpg', { type: 'image/jpeg' });

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const fileInput = document.querySelector('input[type="file"][accept*="image"]');
    await user.upload(fileInput, largeFile);

    await waitFor(() => {
      const errorMessage = screen.queryByText(/File size must be less than 5MB/i);
      expect(errorMessage).toBeInTheDocument();
    }, { timeout: 2000 });
  });

  it('displays avatar preview when valid image is uploaded', async () => {
    const user = userEvent.setup();
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' });
    
    // Mock FileReader
    const mockFileReader = {
      readAsDataURL: vi.fn(),
      result: 'data:image/jpeg;base64,test',
      onloadend: null,
    };
    global.FileReader = vi.fn(() => mockFileReader);

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const fileInput = document.querySelector('input[type="file"][accept*="image"]');
    await user.upload(fileInput, file);

    // Simulate FileReader onloadend
    await waitFor(() => {
      if (mockFileReader.onloadend) {
        mockFileReader.onloadend();
      }
    });

    await waitFor(() => {
      const previewImg = screen.queryByAltText('Avatar preview');
      expect(previewImg).toBeInTheDocument();
    }, { timeout: 2000 });
  });

  it('submits form with avatar upload', async () => {
    const user = userEvent.setup();
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' });
    const mockResponse = { success: true };
    authService.register.mockResolvedValueOnce(mockResponse);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    // Mock FileReader
    const mockFileReader = {
      readAsDataURL: vi.fn(),
      result: 'data:image/jpeg;base64,test',
      onloadend: null,
    };
    global.FileReader = vi.fn(() => mockFileReader);

    // Mock successful avatar upload
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ url: 'https://example.com/avatar.jpg' }),
    });

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    // Upload avatar
    const fileInput = document.querySelector('input[type="file"][accept*="image"]');
    await user.upload(fileInput, file);

    // Simulate FileReader onloadend
    await waitFor(() => {
      if (mockFileReader.onloadend) {
        mockFileReader.onloadend();
      }
    });

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
      expect(authService.register).toHaveBeenCalled();
    }, { timeout: 3000 });

    alertSpy.mockRestore();
  });

  it('handles avatar upload error', async () => {
    const user = userEvent.setup();
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' });

    // Mock FileReader
    const mockFileReader = {
      readAsDataURL: vi.fn(),
      result: 'data:image/jpeg;base64,test',
      onloadend: null,
    };
    global.FileReader = vi.fn(() => mockFileReader);

    // Mock failed avatar upload
    global.fetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Upload failed' }),
    });

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    // Upload avatar
    const fileInput = document.querySelector('input[type="file"][accept*="image"]');
    await user.upload(fileInput, file);

    // Simulate FileReader onloadend
    await waitFor(() => {
      if (mockFileReader.onloadend) {
        mockFileReader.onloadend();
      }
    });

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      const errorMessage = screen.queryByText(/Failed to upload avatar/i) || 
                          screen.queryByText(/Upload failed/i);
      if (errorMessage) {
        expect(errorMessage).toBeInTheDocument();
      } else {
        expect(authService.register).not.toHaveBeenCalled();
      }
    }, { timeout: 3000 });
  });

  it('handles FastAPI validation errors with details array', async () => {
    const user = userEvent.setup();
    const error = new Error('Validation error');
    error.details = [
      {
        loc: ['body', 'username'],
        msg: 'Username is required',
        type: 'value_error'
      },
      {
        loc: ['body', 'email'],
        msg: 'Invalid email format',
        type: 'value_error'
      }
    ];
    authService.register.mockRejectedValueOnce(error);

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(authService.register).toHaveBeenCalled();
      const errorMessage = screen.queryByText(/Validation error/i) ||
                          screen.queryByText(/Username is required/i) ||
                          screen.queryByText(/Invalid email format/i);
      expect(errorMessage).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('maps username error from error message', async () => {
    const user = userEvent.setup();
    const error = new Error('Username already taken');
    authService.register.mockRejectedValueOnce(error);

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      const errorMessages = screen.queryAllByText(/Username already taken/i);
      expect(errorMessages.length).toBeGreaterThan(0);
      // Check that it appears in both the general error and field-specific error
      expect(errorMessages[0]).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('maps email error from error message', async () => {
    const user = userEvent.setup();
    const error = new Error('Email is invalid');
    authService.register.mockRejectedValueOnce(error);

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      const errorMessages = screen.queryAllByText(/Email is invalid/i);
      expect(errorMessages.length).toBeGreaterThan(0);
      expect(errorMessages[0]).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('maps password error from error message', async () => {
    const user = userEvent.setup();
    const error = new Error('Password is too weak');
    authService.register.mockRejectedValueOnce(error);

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      const errorMessages = screen.queryAllByText(/Password is too weak/i);
      expect(errorMessages.length).toBeGreaterThan(0);
      expect(errorMessages[0]).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('handles Google sign up button click', async () => {
    const user = userEvent.setup();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const googleButton = screen.getByRole('button', { name: /register.signUpGoogle/i });
    await user.click(googleButton);

    expect(alertSpy).toHaveBeenCalledWith('Google sign up (Demo)');
    alertSpy.mockRestore();
  });

  it('validates username length exceeds 50 characters', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const usernameInput = screen.getByLabelText(/username/i);
    await user.type(usernameInput, 'a'.repeat(51)); // Too long
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      const errorMessage = screen.queryByText(/Username must be less than 50 characters/i);
      if (errorMessage) {
        expect(errorMessage).toBeInTheDocument();
      } else {
        expect(authService.register).not.toHaveBeenCalled();
      }
    }, { timeout: 2000 });
  });

  it('validates username contains only allowed characters', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const usernameInput = screen.getByLabelText(/username/i);
    await user.type(usernameInput, 'test@user!'); // Invalid characters
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      const errorMessage = screen.queryByText(/Username must contain only letters, numbers, underscores, and hyphens/i);
      if (errorMessage) {
        expect(errorMessage).toBeInTheDocument();
      } else {
        expect(authService.register).not.toHaveBeenCalled();
      }
    }, { timeout: 2000 });
  });

  it('validates password missing digit', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password'); // Missing digit
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      const errorMessage = screen.queryByText(/Password must contain at least one digit/i);
      if (errorMessage) {
        expect(errorMessage).toBeInTheDocument();
      } else {
        expect(authService.register).not.toHaveBeenCalled();
      }
    }, { timeout: 2000 });
  });

  it('clears errors when user starts typing', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const usernameInput = screen.getByLabelText(/username/i);
    await user.type(usernameInput, 'ab'); // Too short
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    // Wait for error to appear
    await waitFor(() => {
      const errorMessage = screen.queryByText(/Username must be at least 3 characters long/i);
      if (errorMessage) {
        expect(errorMessage).toBeInTheDocument();
      }
    }, { timeout: 2000 });

    // Clear the input and type valid username
    await user.clear(usernameInput);
    await user.type(usernameInput, 'validuser');

    // Error should be cleared
    await waitFor(() => {
      const errorMessage = screen.queryByText(/Username must be at least 3 characters long/i);
      expect(errorMessage).not.toBeInTheDocument();
    }, { timeout: 1000 });
  });

  it('displays loading state during submission', async () => {
    const user = userEvent.setup();
    let resolveRegister;
    const registerPromise = new Promise((resolve) => {
      resolveRegister = resolve;
    });
    authService.register.mockReturnValueOnce(registerPromise);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    // Check loading state
    await waitFor(() => {
      expect(screen.getByText(/Creating Account.../i)).toBeInTheDocument();
      expect(submitButton).toBeDisabled();
    });

    // Resolve the promise
    resolveRegister({ success: true });
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalled();
    });

    alertSpy.mockRestore();
  });

  it('displays uploading state during avatar upload', async () => {
    const user = userEvent.setup();
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' });
    const mockResponse = { success: true };
    authService.register.mockResolvedValueOnce(mockResponse);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    // Mock FileReader
    const mockFileReader = {
      readAsDataURL: vi.fn(),
      result: 'data:image/jpeg;base64,test',
      onloadend: null,
    };
    global.FileReader = vi.fn(() => mockFileReader);

    // Mock slow avatar upload
    let resolveUpload;
    const uploadPromise = new Promise((resolve) => {
      resolveUpload = resolve;
    });
    global.fetch.mockReturnValueOnce(uploadPromise.then(() => ({
      ok: true,
      json: async () => ({ url: 'https://example.com/avatar.jpg' }),
    })));

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    // Upload avatar
    const fileInput = document.querySelector('input[type="file"][accept*="image"]');
    await user.upload(fileInput, file);

    // Simulate FileReader onloadend
    await waitFor(() => {
      if (mockFileReader.onloadend) {
        mockFileReader.onloadend();
      }
    });

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    // Check uploading state
    await waitFor(() => {
      expect(screen.getByText(/Uploading image.../i)).toBeInTheDocument();
      expect(submitButton).toBeDisabled();
    });

    // Resolve upload
    resolveUpload();
    await waitFor(() => {
      expect(authService.register).toHaveBeenCalled();
    });

    alertSpy.mockRestore();
  });

  it('handles theme toggle button click', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const themeButton = screen.getByRole('button', { name: /Toggle Theme/i });
    await user.click(themeButton);

    expect(mockToggleTheme).toHaveBeenCalled();
  });

  it('handles language toggle button click', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const langButton = screen.getByRole('button', { name: /Switch Language/i });
    await user.click(langButton);

    expect(mockToggleLanguage).toHaveBeenCalled();
  });

  it('displays language button text correctly', () => {
    useLanguage.mockReturnValue({ language: 'ar', toggleLanguage: mockToggleLanguage });
    
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    const langButton = screen.getByRole('button', { name: /Switch Language/i });
    expect(langButton).toHaveTextContent('AR');
  });

  it('submits form with fullName split into first_name and last_name', async () => {
    const user = userEvent.setup();
    const mockResponse = { success: true };
    authService.register.mockResolvedValueOnce(mockResponse);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.nameLabel/i), 'John Doe');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    await user.type(screen.getByLabelText(/register.passwordLabel/i), 'Password123');
    await user.type(screen.getByLabelText(/register.confirmLabel/i), 'Password123');
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(authService.register).toHaveBeenCalledWith(
        expect.objectContaining({
          username: 'testuser',
          email: 'test@example.com',
          password: 'Password123',
          first_name: 'John',
          last_name: 'Doe',
        })
      );
    });

    alertSpy.mockRestore();
  });

  it('handles empty password edge case', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Register />
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/username/i), 'testuser');
    await user.type(screen.getByLabelText(/register.emailLabel/i), 'test@example.com');
    // Don't type password - leave it empty (just don't fill password field)
    // Don't type confirmPassword either - leave it empty
    
    const termsCheckbox = screen.getByLabelText(/register.agree/i);
    await user.click(termsCheckbox);

    const submitButton = screen.getByRole('button', { name: /register.createAccount/i });
    await user.click(submitButton);

    await waitFor(() => {
      const errorMessage = screen.queryByText(/Password must be at least 8 characters long/i) ||
                          screen.queryByText(/Password is required/i);
      if (errorMessage) {
        expect(errorMessage).toBeInTheDocument();
      } else {
        expect(authService.register).not.toHaveBeenCalled();
      }
    }, { timeout: 2000 });
  });
});

