import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { authService } from '../../services/authService';
import { useAvatarUpload } from '../../hooks/useAvatarUpload';
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

  const {
    avatarFile,
    avatarPreview,
    uploadingAvatar,
    fileInputRef,
    handleAvatarChange,
    uploadAvatar,
    triggerFileInput
  } = useAvatarUpload(null, (errorKey) => {
    if (errorKey === 'invalid_type') {
      setErrors(prev => ({ ...prev, avatar: t('register.invalidImage') || 'Invalid image type' }));
    } else if (errorKey === 'invalid_size') {
      setErrors(prev => ({ ...prev, avatar: t('register.imageSizeError') || 'Image too large' }));
    } else {
      setErrors(prev => ({ ...prev, avatar: errorKey }));
    }
  });

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
      errors.push(t('register.passwordHint'));
    }
    if (!/[A-Z]/.test(password)) {
      errors.push(t('register.passwordHint'));
    }
    if (!/[a-z]/.test(password)) {
      errors.push(t('register.passwordHint'));
    }
    if (!/\d/.test(password)) {
      errors.push(t('register.passwordHint'));
    }
    return errors;
  };

  const validateUsername = (username) => {
    if (username.length < 3) {
      return t('register.usernameMin');
    }
    if (username.length > 50) {
      return t('register.usernameMax');
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(username)) {
      return t('register.usernameInvalid');
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
      newErrors.confirmPassword = t('register.passwordsDoNotMatch');
    }

    if (!formData.terms) {
      newErrors.terms = t('register.termsRequired');
    }

    // Validate first and last name
    if (!formData.firstName.trim()) {
      newErrors.firstName = t('register.firstNameRequired');
    }
    if (!formData.lastName.trim()) {
      newErrors.lastName = t('register.lastNameRequired');
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    setIsLoading(true);

    try {
      // Ensure password is not empty
      if (!formData.password || formData.password.trim() === '') {
        setErrors(prev => ({ ...prev, password: t('register.passwordRequired') }));
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
      if (import.meta.env.DEV) {
        console.log('Registration data:', { ...registrationData, password: '***' });
      }

      // 1. Create the user first (Backend now returns tokens on success)
      const response = await authService.register(registrationData);

      // 2. If registration successful and we have an avatar file, upload it now
      if (avatarFile) {
        try {
          const avatarUrl = await uploadAvatar();

          // Update the user with the new avatar URL
          const userId = response.user.user_id || response.user.id;
          await authService.updateUser(userId, { avatar_url: avatarUrl });
        } catch (uploadError) {
          console.error('Optional avatar upload failed:', uploadError);
          // We don't fail the whole registration if just the avatar upload fails
          // but we could notify the user
        }
      }

      // Success - show message and redirect to login
      toast.success(t('register.accountCreated') || 'Account created successfully! Please login with your credentials.');
      navigate('/login');
    } catch (error) {
      // Handle error response
      let errorMessage = error.message || t('register.registrationFailed') || 'Registration failed. Please try again.';
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



  const handleGoogleSignUp = () => {
    toast(t('register.googleSignUpDemo') || 'Google sign up (Demo)');
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
                <label htmlFor="username">{t('register.usernameLabel')}</label>
                <input
                  type="text"
                  id="username"
                  name="username"
                  placeholder={t('register.usernamePlaceholder')}
                  value={formData.username}
                  onChange={handleChange}
                  required
                />
                {errors.username && (
                  <small style={{ color: 'var(--accent-pink)' }}>{errors.username}</small>
                )}
              </div>

              <div className="form-row-auth">
                <div className="form-group">
                  <label htmlFor="firstName">{t('register.firstNameLabel')}</label>
                  <input
                    type="text"
                    id="firstName"
                    name="firstName"
                    placeholder={t('register.firstNamePlaceholder')}
                    value={formData.firstName}
                    onChange={handleChange}
                    required
                  />
                  {errors.firstName && (
                    <small style={{ color: 'var(--accent-pink)' }}>{errors.firstName}</small>
                  )}
                </div>
                <div className="form-group">
                  <label htmlFor="lastName">{t('register.lastNameLabel')}</label>
                  <input
                    type="text"
                    id="lastName"
                    name="lastName"
                    placeholder={t('register.lastNamePlaceholder')}
                    value={formData.lastName}
                    onChange={handleChange}
                    required
                  />
                  {errors.lastName && (
                    <small style={{ color: 'var(--accent-pink)' }}>{errors.lastName}</small>
                  )}
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
                  <small className="form-hint">{t('register.passwordHint')}</small>
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
                <label style={{ textAlign: 'center' }}>{t('register.avatarLabel')}</label>
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
                          <span className="overlay-text">{t('register.changePhoto')}</span>
                        </div>
                      </div>
                    ) : (
                      <div className="upload-placeholder">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        <span className="upload-text">{t('register.uploadPhoto')}</span>
                      </div>
                    )}
                  </label>
                </div>
                {errors.avatar && (
                  <small className="error-message-small">{errors.avatar}</small>
                )}
                <small className="form-hint" style={{ textAlign: 'center' }}>
                  {t('register.avatarHint')}
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
                  {uploadingAvatar ? t('register.uploadingImage') : isLoading ? t('register.creatingAccount') : t('register.createAccount')}
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

