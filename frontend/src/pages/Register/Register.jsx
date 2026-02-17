import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { authService } from '../../services/authService';
import '../../styles/auth.css';

const Register = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { toggleTheme } = useTheme();
  const { language, toggleLanguage } = useLanguage();
  const [formData, setFormData] = useState({
    username: '',
    firstName: '',
    lastName: '',
    email: '',
    password: '',
    confirmPassword: '',
    avatarUrl: '',
    terms: false
  });
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [avatarFile, setAvatarFile] = useState(null);
  const [avatarPreview, setAvatarPreview] = useState(null);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
    // Clear error when user starts typing
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: '' }));
    }
    if (submitError) {
      setSubmitError('');
    }
  };

  const validatePassword = (password) => {
    const errors = [];
    if (password.length < 8) {
      errors.push('Password must be at least 8 characters long');
    }
    if (!/[A-Z]/.test(password)) {
      errors.push('Password must contain at least one uppercase letter');
    }
    if (!/[a-z]/.test(password)) {
      errors.push('Password must contain at least one lowercase letter');
    }
    if (!/\d/.test(password)) {
      errors.push('Password must contain at least one digit');
    }
    return errors;
  };

  const validateUsername = (username) => {
    if (username.length < 3) {
      return 'Username must be at least 3 characters long';
    }
    if (username.length > 50) {
      return 'Username must be less than 50 characters';
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(username)) {
      return 'Username must contain only letters, numbers, underscores, and hyphens';
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitError('');
    setErrors({});

    // Validation
    const newErrors = {};

    // Validate username
    const usernameError = validateUsername(formData.username);
    if (usernameError) {
      newErrors.username = usernameError;
    }

    // Validate password
    const passwordErrors = validatePassword(formData.password);
    if (passwordErrors.length > 0) {
      newErrors.password = passwordErrors[0];
    }

    if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    if (!formData.terms) {
      newErrors.terms = 'Please agree to the Terms of Service and Privacy Policy';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    setIsLoading(true);

    try {
      // Ensure password is not empty
      if (!formData.password || formData.password.trim() === '') {
        setErrors(prev => ({ ...prev, password: 'Password is required' }));
        setIsLoading(false);
        return;
      }

      // Prepare registration data
      const registrationData = {
        username: formData.username.trim().toLowerCase(),
        email: formData.email.trim(),
        password: formData.password.trim(),
        first_name: formData.firstName?.trim() || null,
        last_name: formData.lastName?.trim() || null
      };

      if (language) {
        registrationData.preferred_language = language;
      }

      // Use manual URL if provided
      if (formData.avatarUrl && formData.avatarUrl.trim()) {
        registrationData.avatar_url = formData.avatarUrl.trim();
      }

      // Verify password is present before sending
      if (!registrationData.password || registrationData.password.length === 0) {
        setErrors(prev => ({ ...prev, password: 'Password is required' }));
        setIsLoading(false);
        return;
      }

      // Debug: Log the data being sent (remove in production)
      console.log('Registration data:', { ...registrationData, password: '***' });

      // 1. Create the user first (Backend now returns tokens on success)
      const response = await authService.register(registrationData);

      // 2. If registration successful and we have an avatar file, upload it now
      if (avatarFile) {
        setUploadingAvatar(true);
        try {
          // Save tokens to storage so update request is authenticated
          // if (response.access_token) {
          //   localStorage.setItem('access_token', response.access_token);
          //   localStorage.setItem('refresh_token', response.refresh_token);
          // }

          // Upload the file
          const avatarUrl = await uploadAvatar(avatarFile);

          // Update the user with the new avatar URL
          const userId = response.user.user_id || response.user.id;
          await authService.updateUser(userId, { avatar_url: avatarUrl });
        } catch (uploadError) {
          console.error('Optional avatar upload failed:', uploadError);
          // We don't fail the whole registration if just the avatar upload fails
          // but we could notify the user
        } finally {
          setUploadingAvatar(false);
        }
      }

      // Success - show message and redirect to login
      alert('Account created successfully! Please login with your credentials.');
      navigate('/login');
    } catch (error) {
      // Handle error response
      let errorMessage = error.message || 'Registration failed. Please try again.';
      const fieldErrors = {};

      // Handle FastAPI validation errors
      if (error.details && Array.isArray(error.details)) {
        error.details.forEach(err => {
          if (err.loc && err.loc.length > 1) {
            const field = err.loc[err.loc.length - 1]; // Get the field name
            fieldErrors[field] = err.msg;

            // Map backend field names to frontend field names
            if (field === 'password') {
              fieldErrors.password = err.msg;
            } else if (field === 'username') {
              fieldErrors.username = err.msg;
            } else if (field === 'email') {
              fieldErrors.email = err.msg;
            }
          }
        });

        // Set field-specific errors
        if (Object.keys(fieldErrors).length > 0) {
          setErrors(prev => ({ ...prev, ...fieldErrors }));
        }
      }

      // Set general error message
      setSubmitError(errorMessage);

      // If it's a username/email conflict, highlight the relevant field
      if (errorMessage.toLowerCase().includes('username')) {
        setErrors(prev => ({ ...prev, username: errorMessage }));
      } else if (errorMessage.toLowerCase().includes('email')) {
        setErrors(prev => ({ ...prev, email: errorMessage }));
      } else if (errorMessage.toLowerCase().includes('password')) {
        setErrors(prev => ({ ...prev, password: errorMessage }));
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleAvatarChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Validate file type
      const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
      if (!validTypes.includes(file.type)) {
        setErrors(prev => ({ ...prev, avatar: 'Please select a valid image file (jpg, png, gif, webp)' }));
        return;
      }

      // Validate file size (5MB)
      if (file.size > 5 * 1024 * 1024) {
        setErrors(prev => ({ ...prev, avatar: 'File size must be less than 5MB' }));
        return;
      }

      setAvatarFile(file);
      setErrors(prev => ({ ...prev, avatar: '' }));

      // Create preview
      const reader = new FileReader();
      reader.onloadend = () => {
        setAvatarPreview(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const uploadAvatar = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
      const response = await fetch(`${API_BASE_URL}/upload/avatar`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to upload avatar');
      }

      const data = await response.json();
      return data.url;
    } catch (error) {
      throw error;
    }
  };

  const handleGoogleSignUp = () => {
    alert('Google sign up (Demo)');
  };

  return (
    <div className="auth-page">
      <div className="bg-decorations-auth">
        <div className="deco-shape-auth deco-1-auth"></div>
        <div className="deco-shape-auth deco-2-auth"></div>
        <div className="flow-line-auth flow-1-auth"></div>
        <div className="flow-line-auth flow-2-auth"></div>
      </div>

      <div className="auth-container">
        <div className="auth-left">
          <div className="auth-left-content">
            <div className="logo-section">
              <div className="logo-icon">AR</div>
              <h1>DabljaAR</h1>
            </div>
            <h2>{t('register.leftTitle')}</h2>
            <p>{t('register.leftSubtitle')}</p>

            <div className="features-list">
              <div className="feature-item">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>{t('register.feature1')}</span>
              </div>
              <div className="feature-item">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>{t('register.feature2')}</span>
              </div>
              <div className="feature-item">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>{t('register.feature3')}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-right">
          <div className="auth-form-container">
            <div className="auth-controls">
              <button className="lang-toggle-auth" onClick={toggleLanguage} aria-label="Switch Language">
                {language === 'en' ? 'EN' : 'AR'}
              </button>
              <button className="theme-toggle-auth" onClick={toggleTheme} aria-label="Toggle Theme">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M10 2.5a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 2.5zm0 10a2.5 2.5 0 100-5 2.5 2.5 0 000 5zm0 1.5a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5a.75.75 0 01.75-.75zM17.5 10a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5a.75.75 0 01.75.75zm-13 0a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5a.75.75 0 01.75.75zm11.95 4.95a.75.75 0 01-1.06 0l-1.06-1.06a.75.75 0 111.06-1.06l1.06 1.06a.75.75 0 010 1.06zM5.11 5.11a.75.75 0 01-1.06 0L2.99 3.05a.75.75 0 011.06-1.06l1.06 1.06a.75.75 0 010 1.06zm9.78 0a.75.75 0 010-1.06l1.06-1.06a.75.75 0 111.06 1.06l-1.06 1.06a.75.75 0 01-1.06 0zM5.11 14.89a.75.75 0 010-1.06l1.06-1.06a.75.75 0 111.06 1.06l-1.06 1.06a.75.75 0 01-1.06 0z" />
                </svg>
              </button>
            </div>

            <div className="auth-header">
              <h2>{t('register.title')}</h2>
              <p>{t('register.subtitle')}</p>
            </div>

            <form onSubmit={handleSubmit} className="auth-form">
              {submitError && (
                <div className="error-message" style={{
                  color: 'var(--accent-pink)',
                  padding: '10px',
                  marginBottom: '15px',
                  backgroundColor: 'rgba(255, 0, 0, 0.1)',
                  borderRadius: '5px',
                  border: '1px solid var(--accent-pink)'
                }}>
                  {submitError}
                </div>
              )}

              <div className="form-group">
                <label htmlFor="username">Username</label>
                <input
                  type="text"
                  id="username"
                  name="username"
                  placeholder="Choose a username"
                  value={formData.username}
                  onChange={handleChange}
                  required
                />
                {errors.username && (
                  <small style={{ color: 'var(--accent-pink)' }}>{errors.username}</small>
                )}
              </div>

              <div className="form-row-auth" style={{ display: 'flex', gap: '15px' }}>
                <div className="form-group" style={{ flex: 1 }}>
                  <label htmlFor="firstName">First Name</label>
                  <input
                    type="text"
                    id="firstName"
                    name="firstName"
                    placeholder="First"
                    value={formData.firstName}
                    onChange={handleChange}
                  />
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label htmlFor="lastName">Last Name</label>
                  <input
                    type="text"
                    id="lastName"
                    name="lastName"
                    placeholder="Last"
                    value={formData.lastName}
                    onChange={handleChange}
                  />
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="email">{t('register.emailLabel')}</label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  placeholder={t('register.emailPlaceholder')}
                  value={formData.email}
                  onChange={handleChange}
                  required
                />
                {errors.email && (
                  <small style={{ color: 'var(--accent-pink)' }}>{errors.email}</small>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="password">{t('register.passwordLabel')}</label>
                <input
                  type="password"
                  id="password"
                  name="password"
                  placeholder={t('register.passwordPlaceholder')}
                  value={formData.password}
                  onChange={handleChange}
                  required
                />
                {errors.password ? (
                  <small style={{ color: 'var(--accent-pink)' }}>{errors.password}</small>
                ) : (
                  <small className="form-hint">Must be at least 8 characters with uppercase, lowercase, and a digit</small>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="confirmPassword">{t('register.confirmLabel')}</label>
                <input
                  type="password"
                  id="confirmPassword"
                  name="confirmPassword"
                  placeholder={t('register.confirmPlaceholder')}
                  value={formData.confirmPassword}
                  onChange={handleChange}
                  required
                />
                {errors.confirmPassword && (
                  <small style={{ color: 'var(--accent-pink)' }}>{errors.confirmPassword}</small>
                )}
              </div>


              <div className="form-group">
                <label style={{ textAlign: 'center' }}>Profile Picture (Optional)</label>
                <div className="avatar-input-container">
                  <input
                    type="file"
                    id="avatar"
                    name="avatar"
                    accept="image/jpeg,image/jpg,image/png,image/gif,image/webp"
                    onChange={handleAvatarChange}
                    className="file-input-hidden"
                  />
                  <label htmlFor="avatar" className="avatar-upload-label">
                    {avatarPreview ? (
                      <div className="avatar-preview-wrapper">
                        <img
                          src={avatarPreview}
                          alt="Avatar preview"
                          className="avatar-preview-img"
                        />
                        <div className="avatar-overlay">
                          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M12 4v16m-8-8h16" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                          <span className="overlay-text">Change</span>
                        </div>
                      </div>
                    ) : (
                      <div className="upload-placeholder">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        <span className="upload-text">Upload Photo</span>
                      </div>
                    )}
                  </label>
                </div>
                {errors.avatar && (
                  <small className="error-message-small">{errors.avatar}</small>
                )}
                <small className="form-hint" style={{ textAlign: 'center' }}>
                  Supported formats: JPG, PNG, GIF, WEBP (Max 5MB)
                </small>
              </div>

              <div className="form-options">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    name="terms"
                    checked={formData.terms}
                    onChange={handleChange}
                    required
                  />
                  <span>
                    {t('register.agree')}{' '}
                    <a href="#">{t('register.terms')}</a>{' '}
                    {t('register.and')}{' '}
                    <a href="#">{t('register.privacy')}</a>
                  </span>
                </label>
                {errors.terms && (
                  <small style={{ color: 'var(--accent-pink)', display: 'block', marginTop: '5px' }}>{errors.terms}</small>
                )}
              </div>

              <button type="submit" className="btn-submit" disabled={isLoading || uploadingAvatar}>
                <span>
                  {uploadingAvatar ? 'Uploading image...' : isLoading ? 'Creating Account...' : t('register.createAccount')}
                </span>
                {!isLoading && (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M4 10h12m0 0l-4-4m4 4l-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </button>

              <div className="divider">
                <span>{t('register.orSignUp')}</span>
              </div>

              <button type="button" className="btn-google" onClick={handleGoogleSignUp}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M18 10.2c0-.7 0-1.3-.1-1.8H10v3.4h4.5c-.2 1-.8 1.9-1.6 2.5v2.1h2.6c1.5-1.4 2.4-3.4 2.4-5.8z" fill="#4285F4" />
                  <path d="M10 18.2c2.2 0 4-.7 5.3-1.9l-2.6-2c-.7.5-1.6.8-2.7.8-2.1 0-3.8-1.4-4.5-3.3H2.8v2.1c1.3 2.6 4 4.3 7.2 4.3z" fill="#34A853" />
                  <path d="M5.5 11.8c-.4-1.2-.4-2.4 0-3.6V6.1H2.8c-1.3 2.6-1.3 5.6 0 8.2l2.7-2.1z" fill="#FBBC04" />
                  <path d="M10 5.4c1.2 0 2.2.4 3.1 1.2l2.3-2.3C13.9 2.9 12 2 10 2c-3.2 0-5.9 1.8-7.2 4.3l2.7 2.1c.7-2 2.4-3.3 4.5-3.3z" fill="#EA4335" />
                </svg>
                <span>{t('register.signUpGoogle')}</span>
              </button>
            </form>

            <div className="auth-footer">
              <p>
                <span>{t('register.haveAccount')}</span>{' '}
                <Link to="/login">{t('register.signIn')}</Link>
              </p>
              <p className="back-home">
                <Link to="/">{t('register.backHome')}</Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Register;

