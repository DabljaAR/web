import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { authService } from '../../services/authService';
import '../../styles/auth.css';

const ForgotPassword = () => {
  const { t } = useTranslation();
  const { toggleTheme } = useTheme();
  const { language, toggleLanguage } = useLanguage();
  const [email, setEmail] = useState('');
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [submitStatus, setSubmitStatus] = useState(null);

  const validateEmail = (email) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const handleChange = (e) => {
    const { value } = e.target;
    setEmail(value);
    if (errors.email) {
      setErrors(prev => ({ ...prev, email: '' }));
    }
    if (submitStatus) {
      setSubmitStatus(null);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrors({});
    setSubmitStatus(null);

    if (!email.trim()) {
      setErrors({ email: t('login.invalidEmail') || 'Email is required' });
      return;
    }

    if (!validateEmail(email)) {
      setErrors({ email: t('forgotPassword.invalidEmail') || 'Please enter a valid email address' });
      return;
    }

    setIsLoading(true);

    try {
      await authService.forgotPassword(email);
      setSubmitStatus({ type: 'success', message: t('forgotPassword.successMessage') });
      setEmail('');
    } catch (error) {
      setSubmitStatus({ type: 'error', message: t('forgotPassword.errorMessage') });
    } finally {
      setIsLoading(false);
    }
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
            <h2>{t('login.leftTitle')}</h2>
            <p>{t('login.leftSubtitle')}</p>

            <div className="features-list">
              <div className="feature-item">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>{t('login.feature1')}</span>
              </div>
              <div className="feature-item">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>{t('login.feature2')}</span>
              </div>
              <div className="feature-item">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>{t('login.feature3')}</span>
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
              <h2>{t('forgotPassword.title')}</h2>
              <p>{t('forgotPassword.subtitle')}</p>
            </div>

            {submitStatus && (
              <div className={`status-message ${submitStatus.type}`} style={{
                padding: '10px',
                marginBottom: '15px',
                borderRadius: '5px',
                backgroundColor: submitStatus.type === 'success' ? 'rgba(0, 255, 0, 0.1)' : 'rgba(255, 0, 0, 0.1)',
                border: `1px solid ${submitStatus.type === 'success' ? 'var(--accent-green)' : 'var(--accent-pink)'}`,
                color: submitStatus.type === 'success' ? 'var(--accent-green)' : 'var(--accent-pink)'
              }}>
                {submitStatus.message}
              </div>
            )}

            <form onSubmit={handleSubmit} className="auth-form">
              <div className="form-group">
                <label htmlFor="email">{t('forgotPassword.emailLabel')}</label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  placeholder={t('forgotPassword.emailPlaceholder')}
                  value={email}
                  onChange={handleChange}
                  required
                />
                {errors.email && (
                  <small style={{ color: 'var(--accent-pink)' }}>{errors.email}</small>
                )}
              </div>

              <button type="submit" className="btn-submit" disabled={isLoading}>
                <span>{isLoading ? t('forgotPassword.sending') : t('forgotPassword.sendResetLink')}</span>
                {!isLoading && (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M4 10h12m0 0l-4-4m4 4l-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </button>
            </form>

            <div className="auth-footer">
              <p>
                <Link to="/login">{t('forgotPassword.backToLogin')}</Link>
              </p>
              <p className="back-home">
                <Link to="/">{t('login.backHome')}</Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ForgotPassword;
