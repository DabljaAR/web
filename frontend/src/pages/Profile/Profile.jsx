import React, { useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import '../../styles/profile.css';

const Profile = () => {
  const { t } = useTranslation();
  const [formData, setFormData] = useState({
    fullName: 'John Doe',
    email: 'john@example.com',
    defaultDomain: 'general',
    translationStyle: 'neutral',
    defaultVoice: 'male1',
    notifCompleted: true,
    notifCredits: true,
    notifMarketing: false
  });

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    // Handle form submission
    alert('Settings saved! (Demo)');
  };

  const handleChangePhoto = () => {
    alert('Change photo (Demo)');
  };

  const handleRemovePhoto = () => {
    alert('Remove photo (Demo)');
  };

  const handleChangePassword = () => {
    alert('Change password (Demo)');
  };

  const handleUpgradePremium = () => {
    alert('Upgrade to Premium (Demo)');
  };

  const handleBuyCredits = () => {
    alert('Buy Credits (Demo)');
  };

  const handleDeleteAccount = () => {
    if (window.confirm(t('profile.deleteConfirm'))) {
      alert('Account deletion (Demo)');
    }
  };

  // Get initials for profile picture
  const getInitials = () => {
    return formData.fullName
      .split(' ')
      .map(n => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  return (
    <div className="profile-page">
      <BackgroundDecorations />
      <Navbar />
      
      <div className="main-container">
        {/* Page Header */}
        <div className="page-header">
          <h1 className="page-title">{t('profile.title')}</h1>
          <p className="page-subtitle">{t('profile.subtitle')}</p>
        </div>

        {/* Personal Information */}
        <section className="profile-section">
          <h2 className="section-title">
            <span className="section-icon">👤</span>
            <span>{t('profile.personalInfo')}</span>
          </h2>
          
          <div className="profile-picture-container">
            <div className="profile-picture">{getInitials()}</div>
            <div className="picture-actions">
              <button 
                type="button" 
                className="btn btn-secondary btn-small" 
                onClick={handleChangePhoto}
              >
                {t('profile.changePhoto')}
              </button>
              <button 
                type="button" 
                className="btn btn-secondary btn-small" 
                onClick={handleRemovePhoto}
              >
                {t('profile.removePhoto')}
              </button>
            </div>
          </div>

          <form className="form-grid" onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">{t('profile.fullName')}</label>
              <input
                type="text"
                className="form-input"
                name="fullName"
                value={formData.fullName}
                onChange={handleChange}
                placeholder={t('profile.fullNamePlaceholder')}
              />
            </div>

            <div className="form-group">
              <label className="form-label">
                <span>{t('profile.email')}</span>
                <span className="verified-badge">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                    <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                  <span>{t('profile.verified')}</span>
                </span>
              </label>
              <input
                type="email"
                className="form-input"
                value={formData.email}
                disabled
              />
            </div>

            <div className="form-group">
              <label className="form-label">{t('profile.password')}</label>
              <input
                type="password"
                className="form-input"
                value="••••••••••••"
                disabled
              />
            </div>

            <div className="action-buttons">
              <button 
                type="button" 
                className="btn btn-secondary" 
                onClick={handleChangePassword}
              >
                {t('profile.changePassword')}
              </button>
              <button type="submit" className="btn btn-primary">
                {t('profile.saveChanges')}
              </button>
            </div>
          </form>
        </section>

        {/* Subscription & Credits */}
        <section className="profile-section">
          <h2 className="section-title">
            <span className="section-icon">💳</span>
            <span>{t('profile.subscription')}</span>
          </h2>

          {/* Credits Display */}
          <div className="credits-display">
            <div className="credits-icon">🪙</div>
            <div className="credits-info">
              <h3>25 <span>{t('profile.credits')}</span></h3>
              <p>
                <span>{t('profile.usageThisMonth')}</span> 15 <span>{t('profile.credits')}</span>
              </p>
            </div>
          </div>

          {/* Current Plan */}
          <div className="plan-card">
            <div className="plan-header">
              <h3 className="plan-name">{t('profile.freePlan')}</h3>
              <span className="plan-badge">{t('profile.active')}</span>
            </div>
            <ul className="plan-features">
              <li>{t('profile.freeFeature1')}</li>
              <li>{t('profile.freeFeature2')}</li>
              <li>{t('profile.freeFeature3')}</li>
              <li>{t('profile.freeFeature4')}</li>
            </ul>
          </div>

          {/* Premium Plan */}
          <div className="plan-card premium">
            <div className="plan-header">
              <h3 className="plan-name">{t('profile.premiumPlan')}</h3>
              <span className="plan-badge" style={{background: 'var(--accent-orange)'}}>
                {t('profile.recommended')}
              </span>
            </div>
            <ul className="plan-features">
              <li>{t('profile.premiumFeature1')}</li>
              <li>{t('profile.premiumFeature2')}</li>
              <li>{t('profile.premiumFeature3')}</li>
              <li>{t('profile.premiumFeature4')}</li>
              <li>{t('profile.premiumFeature5')}</li>
            </ul>
          </div>

          <div className="action-buttons">
            <button 
              type="button" 
              className="btn btn-primary" 
              onClick={handleUpgradePremium}
            >
              {t('profile.upgradePremium')}
            </button>
            <button 
              type="button" 
              className="btn btn-secondary" 
              onClick={handleBuyCredits}
            >
              {t('profile.buyCredits')}
            </button>
          </div>
        </section>

        {/* Account Statistics */}
        <section className="profile-section">
          <h2 className="section-title">
            <span className="section-icon">📊</span>
            <span>{t('profile.statistics')}</span>
          </h2>
          
          <div className="stats-grid">
            <div className="stat-item">
              <div className="stat-label">{t('profile.memberSince')}</div>
              <div className="stat-value">Jan 2025</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">{t('profile.totalVideos')}</div>
              <div className="stat-value">47</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">{t('profile.totalCredits')}</div>
              <div className="stat-value">235</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">{t('profile.favoriteDomain')}</div>
              <div className="stat-value" style={{fontSize: '1.25rem'}}>
                {t('profile.domainTechnical')}
              </div>
            </div>
          </div>
        </section>

        {/* Preferences */}
        <section className="profile-section">
          <h2 className="section-title">
            <span className="section-icon">⚙️</span>
            <span>{t('profile.preferences')}</span>
          </h2>
          
          <form className="form-grid" onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">{t('profile.defaultDomain')}</label>
              <select 
                className="form-input"
                name="defaultDomain"
                value={formData.defaultDomain}
                onChange={handleChange}
              >
                <option value="general">{t('profile.domainGeneral')}</option>
                <option value="technical">{t('profile.domainTechnical')}</option>
                <option value="medical">{t('profile.domainMedical')}</option>
                <option value="legal">{t('profile.domainLegal')}</option>
                <option value="education">{t('profile.domainEducation')}</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">{t('profile.translationStyle')}</label>
              <select 
                className="form-input"
                name="translationStyle"
                value={formData.translationStyle}
                onChange={handleChange}
              >
                <option value="neutral">{t('profile.styleNeutral')}</option>
                <option value="formal">{t('profile.styleFormal')}</option>
                <option value="casual">{t('profile.styleCasual')}</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">{t('profile.defaultVoice')}</label>
              <select 
                className="form-input"
                name="defaultVoice"
                value={formData.defaultVoice}
                onChange={handleChange}
              >
                <option value="male1">{t('profile.voiceMale1')}</option>
                <option value="male2">{t('profile.voiceMale2')}</option>
                <option value="female1">{t('profile.voiceFemale1')}</option>
                <option value="female2">{t('profile.voiceFemale2')}</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">{t('profile.emailNotifications')}</label>
              <div className="checkbox-list">
                <div className="checkbox-item">
                  <input
                    type="checkbox"
                    id="notif1"
                    name="notifCompleted"
                    checked={formData.notifCompleted}
                    onChange={handleChange}
                  />
                  <label htmlFor="notif1">{t('profile.notifCompleted')}</label>
                </div>
                <div className="checkbox-item">
                  <input
                    type="checkbox"
                    id="notif2"
                    name="notifCredits"
                    checked={formData.notifCredits}
                    onChange={handleChange}
                  />
                  <label htmlFor="notif2">{t('profile.notifCredits')}</label>
                </div>
                <div className="checkbox-item">
                  <input
                    type="checkbox"
                    id="notif3"
                    name="notifMarketing"
                    checked={formData.notifMarketing}
                    onChange={handleChange}
                  />
                  <label htmlFor="notif3">{t('profile.notifMarketing')}</label>
                </div>
              </div>
            </div>

            <button type="submit" className="btn btn-primary">
              {t('profile.savePreferences')}
            </button>
          </form>
        </section>

        {/* Danger Zone */}
        <section className="profile-section danger-zone">
          <h2 className="section-title">
            <span className="section-icon">⚠️</span>
            <span>{t('profile.dangerZone')}</span>
          </h2>
          <p className="danger-warning">
            {t('profile.deleteWarning')}
          </p>
          <button 
            type="button" 
            className="btn btn-danger" 
            onClick={handleDeleteAccount}
          >
            {t('profile.deleteAccount')}
          </button>
        </section>
      </div>
      <Footer />
    </div>
  );
};

export default Profile;

