import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';
import '../../styles/auth.css';

const Register = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { toggleTheme } = useTheme();
  const { language, toggleLanguage } = useLanguage();
  const [formData, setFormData] = useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
    terms: false
  });
  const [errors, setErrors] = useState({});

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
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    
    // Validation
    const newErrors = {};
    if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
      setErrors(newErrors);
      return;
    }
    
    if (!formData.terms) {
      alert('Please agree to the Terms of Service and Privacy Policy');
      return;
    }
    
    // Demo registration
    alert('Account created successfully! (Demo)');
    navigate('/');
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
                  <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <span>{t('register.feature1')}</span>
              </div>
              <div className="feature-item">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <span>{t('register.feature2')}</span>
              </div>
              <div className="feature-item">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
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
                  <path d="M10 2.5a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 2.5zm0 10a2.5 2.5 0 100-5 2.5 2.5 0 000 5zm0 1.5a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5a.75.75 0 01.75-.75zM17.5 10a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5a.75.75 0 01.75.75zm-13 0a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5a.75.75 0 01.75.75zm11.95 4.95a.75.75 0 01-1.06 0l-1.06-1.06a.75.75 0 111.06-1.06l1.06 1.06a.75.75 0 010 1.06zM5.11 5.11a.75.75 0 01-1.06 0L2.99 3.05a.75.75 0 011.06-1.06l1.06 1.06a.75.75 0 010 1.06zm9.78 0a.75.75 0 010-1.06l1.06-1.06a.75.75 0 111.06 1.06l-1.06 1.06a.75.75 0 01-1.06 0zM5.11 14.89a.75.75 0 010-1.06l1.06-1.06a.75.75 0 111.06 1.06l-1.06 1.06a.75.75 0 01-1.06 0z"/>
                </svg>
              </button>
            </div>

            <div className="auth-header">
              <h2>{t('register.title')}</h2>
              <p>{t('register.subtitle')}</p>
            </div>

            <form onSubmit={handleSubmit} className="auth-form">
              <div className="form-group">
                <label htmlFor="fullName">{t('register.nameLabel')}</label>
                <input
                  type="text"
                  id="fullName"
                  name="fullName"
                  placeholder={t('register.namePlaceholder')}
                  value={formData.fullName}
                  onChange={handleChange}
                  required
                />
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
                <small className="form-hint">{t('register.passwordHint')}</small>
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
              </div>

              <button type="submit" className="btn-submit">
                <span>{t('register.createAccount')}</span>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M4 10h12m0 0l-4-4m4 4l-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>

              <div className="divider">
                <span>{t('register.orSignUp')}</span>
              </div>

              <button type="button" className="btn-google" onClick={handleGoogleSignUp}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M18 10.2c0-.7 0-1.3-.1-1.8H10v3.4h4.5c-.2 1-.8 1.9-1.6 2.5v2.1h2.6c1.5-1.4 2.4-3.4 2.4-5.8z" fill="#4285F4"/>
                  <path d="M10 18.2c2.2 0 4-.7 5.3-1.9l-2.6-2c-.7.5-1.6.8-2.7.8-2.1 0-3.8-1.4-4.5-3.3H2.8v2.1c1.3 2.6 4 4.3 7.2 4.3z" fill="#34A853"/>
                  <path d="M5.5 11.8c-.4-1.2-.4-2.4 0-3.6V6.1H2.8c-1.3 2.6-1.3 5.6 0 8.2l2.7-2.1z" fill="#FBBC04"/>
                  <path d="M10 5.4c1.2 0 2.2.4 3.1 1.2l2.3-2.3C13.9 2.9 12 2 10 2c-3.2 0-5.9 1.8-7.2 4.3l2.7 2.1c.7-2 2.4-3.3 4.5-3.3z" fill="#EA4335"/>
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

