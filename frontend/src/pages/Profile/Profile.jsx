import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../../hooks/useTranslation';
import { useAuth } from '../../hooks/useAuth';
import api from '../../services/api';
import ChangePasswordModal from '../../components/profile/ChangePasswordModal';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import '../../styles/profile.css';

const Profile = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user: authUser, logout } = useAuth();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [avatarFile, setAvatarFile] = useState(null);
  const [avatarPreview, setAvatarPreview] = useState(null);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false);
  const fileInputRef = useRef(null);
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    preferredLanguage: '',
    defaultDomain: 'general',
    translationStyle: 'neutral',
    defaultVoice: 'male1',
    notifCompleted: true,
    notifCredits: true,
    notifMarketing: false
  });

  // Fetch user data from API
  useEffect(() => {
    const fetchUserData = async () => {
      if (!authUser?.user_id) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);
        const userData = await api.get(`/users/${authUser.user_id}`);
        setUser(userData);

        // Update form data with user information
        setFormData(prev => ({
          ...prev,
          firstName: userData.first_name || '',
          lastName: userData.last_name || '',
          email: userData.email || '',
          preferredLanguage: userData.preferred_language || '',
          defaultDomain: userData.default_domain || 'general',
          translationStyle: userData.translation_style || 'neutral',
          defaultVoice: userData.default_voice || 'male1',
          notifCompleted: userData.notif_completed ?? true,
          notifCredits: userData.notif_credits ?? true,
          notifMarketing: userData.notif_marketing ?? false
        }));
      } catch (err) {
        setError(err.message || 'Failed to load user data');
        console.error('Error fetching user data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchUserData();
  }, [authUser]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const uploadAvatar = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://136.112.92.233:8000/api';
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
  };

  const handleAvatarChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Validate file type
      const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
      if (!validTypes.includes(file.type)) {
        alert('Please select a valid image file (jpg, png, gif, webp)');
        return;
      }

      // Validate file size (5MB)
      if (file.size > 5 * 1024 * 1024) {
        alert('File size must be less than 5MB');
        return;
      }

      setAvatarFile(file);

      // Create preview
      const reader = new FileReader();
      reader.onloadend = () => {
        setAvatarPreview(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleChangePhoto = () => {
    fileInputRef.current?.click();
  };

  const handleRemovePhoto = async () => {
    if (!window.confirm('Are you sure you want to remove your profile picture?')) {
      return;
    }

    if (!user?.user_id) return;

    try {
      setSaving(true);
      const updatedUser = await api.put(`/users/${user.user_id}`, {
        avatar_url: null
      });

      setUser(updatedUser);
      setAvatarFile(null);
      setAvatarPreview(null);
      alert('Profile picture removed successfully');
    } catch (err) {
      alert(err.message || 'Failed to remove profile picture');
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!user?.user_id) return;

    try {
      setSaving(true);
      setError(null);

      // Upload avatar if new file is selected
      let avatarUrl = user.avatar_url;
      if (avatarFile) {
        setUploadingAvatar(true);
        try {
          avatarUrl = await uploadAvatar(avatarFile);
        } catch (uploadError) {
          alert(uploadError.message || 'Failed to upload avatar');
          setUploadingAvatar(false);
          setSaving(false);
          return;
        }
        setUploadingAvatar(false);
      }

      // Prepare update data
      const updateData = {
        first_name: formData.firstName.trim() || null,
        last_name: formData.lastName.trim() || null,
        email: formData.email, // Email is disabled, but included for completeness if backend expects it
        preferred_language: formData.preferredLanguage || null,
        default_domain: formData.defaultDomain,
        translation_style: formData.translationStyle,
        default_voice: formData.defaultVoice,
        notif_completed: formData.notifCompleted,
        notif_credits: formData.notifCredits,
        notif_marketing: formData.notifMarketing,
        avatar_url: avatarUrl // Include the (potentially new) avatar URL
      };

      const updatedUser = await api.put(`/users/${user.user_id}`, updateData);

      setUser(updatedUser);
      setAvatarFile(null);
      setAvatarPreview(null);

      // Update auth user in localStorage
      localStorage.setItem('user', JSON.stringify(updatedUser));

      alert('Profile updated successfully!');
    } catch (err) {
      setError(err.message || 'Failed to update profile');
      alert(err.message || 'Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = () => {
    setIsPasswordModalOpen(true);
  };

  const handleUpgradePremium = () => {
    alert('Upgrade to Premium (Demo)');
  };

  const handleBuyCredits = () => {
    alert('Buy Credits (Demo)');
  };

  const handleDeleteAccount = async () => {
    if (!user?.user_id) return;

    const confirmMessage = t('profile.deleteConfirm') || 'Are you sure you want to delete your account? This action cannot be undone.';
    if (!window.confirm(confirmMessage)) {
      return;
    }

    // Double confirmation
    const doubleConfirm = window.prompt('Type "DELETE" to confirm account deletion:');
    if (doubleConfirm !== 'DELETE') {
      return;
    }

    try {
      setSaving(true);
      await api.delete(`/users/${user.user_id}`);

      // Logout and redirect
      logout();
      alert('Your account has been deleted successfully');
      window.location.href = '/';
    } catch (err) {
      alert(err.message || 'Failed to delete account');
      setSaving(false);
    }
  };

  // Get initials for profile picture
  const getInitials = () => {
    if (user?.first_name && user?.last_name) {
      return `${user.first_name[0]}${user.last_name[0]}`.toUpperCase();
    } else if (user?.first_name) {
      return user.first_name[0].toUpperCase();
    } else if (user?.username) {
      return user.username[0].toUpperCase();
    }
    return 'U';
  };

  // Format date
  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  };

  if (loading) {
    return (
      <div className="profile-page">
        <BackgroundDecorations />
        <Navbar />
        <div className="main-container">
          <div style={{ textAlign: 'center', padding: '50px' }}>
            <p>{t('profile.loading') || 'Loading profile...'}</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="profile-page">
        <BackgroundDecorations />
        <Navbar />
        <div className="main-container">
          <div style={{ textAlign: 'center', padding: '50px', color: 'var(--accent-red)' }}>
            <p>Error: {error}</p>
          </div>
        </div>
      </div>
    );
  }

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
            <input
              type="file"
              ref={fileInputRef}
              accept="image/jpeg,image/jpg,image/png,image/gif,image/webp"
              onChange={handleAvatarChange}
              style={{ display: 'none' }}
            />
            {(avatarPreview || user?.avatar_url) ? (
              <div className="profile-picture" style={{
                backgroundImage: `url(${avatarPreview || user.avatar_url})`,
                backgroundSize: 'cover',
                backgroundPosition: 'center'
              }}>
              </div>
            ) : (
              <div className="profile-picture">{getInitials()}</div>
            )}
            <div className="picture-actions">
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={handleChangePhoto}
                disabled={saving || uploadingAvatar}
              >
                {t('profile.changePhoto')}
              </button>
              {user?.avatar_url && (
                <button
                  type="button"
                  className="btn btn-secondary btn-small"
                  onClick={handleRemovePhoto}
                  disabled={saving || uploadingAvatar}
                >
                  {t('profile.removePhoto')}
                </button>
              )}
            </div>
            {avatarFile && (
              <small style={{ color: 'var(--text-light)', fontSize: '12px', marginTop: '8px', display: 'block' }}>
                New image selected. Click "Save Changes" to update.
              </small>
            )}
          </div>

          <form className="form-grid" onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('profile.firstName')}</label>
                <input
                  type="text"
                  className="form-input"
                  name="firstName"
                  value={formData.firstName}
                  onChange={handleChange}
                  placeholder={t('profile.firstNamePlaceholder')}
                />
              </div>

              <div className="form-group">
                <label className="form-label">{t('profile.lastName')}</label>
                <input
                  type="text"
                  className="form-input"
                  name="lastName"
                  value={formData.lastName}
                  onChange={handleChange}
                  placeholder={t('profile.lastNamePlaceholder')}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">
                <span>{t('profile.email')}</span>
                <span className="verified-badge">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                    <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  <span>{t('profile.verified')}</span>
                </span>
              </label>
              <input
                type="email"
                className="form-input"
                value={user?.email || formData.email}
                disabled
              />
            </div>

            <div className="form-group">
              <label className="form-label">{t('profile.username') || 'Username'}</label>
              <input
                type="text"
                className="form-input"
                value={user?.username || ''}
                disabled
              />
            </div>

            <div className="form-group">
              <label className="form-label">{t('profile.preferredLanguage') || 'Preferred Language'}</label>
              <select
                className="form-input"
                name="preferredLanguage"
                value={formData.preferredLanguage}
                onChange={handleChange}
              >
                <option value="">{t('dashboard.noFilesFound') ? 'Not set' : 'Not set'}</option>
                <option value="en">English</option>
                <option value="ar">Arabic</option>
                <option value="fr">French</option>
                <option value="es">Spanish</option>
              </select>
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

            {error && (
              <div style={{
                color: 'var(--accent-red)',
                padding: '10px',
                marginBottom: '15px',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                borderRadius: '5px',
                border: '1px solid var(--accent-red)'
              }}>
                {error}
              </div>
            )}
            <div className="action-buttons">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleChangePassword}
                disabled={saving}
              >
                {t('profile.changePassword')}
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={saving || uploadingAvatar}
              >
                {uploadingAvatar ? (t('profile.uploadingImage') || 'Uploading image...') : saving ? (t('profile.saving') || 'Saving...') : t('profile.saveChanges')}
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
              <span className="plan-badge" style={{ background: 'var(--accent-orange)' }}>
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
              <div className="stat-value">
                {user?.created_at ? formatDate(user.created_at) : 'N/A'}
              </div>
            </div>
            <div className="stat-item">
              <div className="stat-label">{t('profile.lastLogin') || 'Last Login'}</div>
              <div className="stat-value">
                {user?.last_login ? formatDate(user.last_login) : (t('profile.never') || 'Never')}
              </div>
            </div>
            <div className="stat-item">
              <div className="stat-label">{t('profile.userID') || 'User ID'}</div>
              <div className="stat-value">{user?.user_id || 'N/A'}</div>
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
              <div className="stat-value" style={{ fontSize: '1.25rem' }}>
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
            disabled={saving}
          >
            {saving ? (t('profile.deleting') || 'Deleting...') : t('profile.deleteAccount')}
          </button>
        </section>
      </div>
      <Footer />
      <ChangePasswordModal
        isOpen={isPasswordModalOpen}
        onClose={() => setIsPasswordModalOpen(false)}
        userId={user?.user_id}
      />
    </div>
  );
};

export default Profile;

