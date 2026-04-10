import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';
import { BCRYPT_MAX_PASSWORD_BYTES, validatePasswordByteLength } from '../../features/auth/utils/validation';
import './ChangePasswordModal.css';

const ChangePasswordModal = ({ isOpen, onClose, userId }) => {
    const { t } = useTranslation();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);
    const [formData, setFormData] = useState({
        oldPassword: '',
        newPassword: '',
        confirmPassword: ''
    });

    // Close on Escape key
    useEffect(() => {
        const handleEsc = (e) => {
            if (e.key === 'Escape') onClose();
        };
        if (isOpen) {
            document.addEventListener('keydown', handleEsc);
            document.body.style.overflow = 'hidden';
            setError(null);
            setSuccess(false);
            setFormData({
                oldPassword: '',
                newPassword: '',
                confirmPassword: ''
            });
        }
        return () => {
            document.removeEventListener('keydown', handleEsc);
            document.body.style.overflow = 'unset';
        };
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const handleChange = (e) => {
        setFormData({
            ...formData,
            [e.target.name]: e.target.value
        });
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);

        if (formData.newPassword !== formData.confirmPassword) {
            setError(t('profile.passwordMatchError') || 'Passwords do not match');
            return;
        }
        if (!validatePasswordByteLength(formData.newPassword)) {
            setError(
                t('profile.passwordByteLimit') ||
                `Password is too long for secure hashing. Max ${BCRYPT_MAX_PASSWORD_BYTES} UTF-8 bytes.`
            );
            return;
        }

        try {
            setLoading(true);
            await api.post(`/users/${userId}/change-password`, {
                old_password: formData.oldPassword,
                new_password: formData.newPassword
            });
            setSuccess(true);
            setTimeout(() => {
                onClose();
            }, 2000);
        } catch (err) {
            setError(err.message || t('profile.passwordChangeError') || 'Failed to change password');
        } finally {
            setLoading(false);
        }
    };

    const handleBackdropClick = (e) => {
        if (e.target === e.currentTarget) {
            onClose();
        }
    };

    const content = (
        <div className="password-modal-backdrop" onClick={handleBackdropClick}>
            <div className="password-modal-container">
                <div className="password-modal-header">
                    <h3>{t('profile.changePassword') || 'Change Password'}</h3>
                    <button className="close-btn" onClick={onClose}>
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                    </button>
                </div>

                <div className="password-modal-body">
                    {success ? (
                        <div className="success-message">
                            <div className="success-icon">✓</div>
                            <p>{t('profile.passwordChangeSuccess') || 'Password changed successfully'}</p>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit}>
                            {error && <div className="error-message">{error}</div>}

                            <div className="form-group">
                                <label className="form-label">{t('profile.oldPassword') || 'Current Password'}</label>
                                <input
                                    type="password"
                                    name="oldPassword"
                                    className="form-input"
                                    value={formData.oldPassword}
                                    onChange={handleChange}
                                    required
                                    placeholder="••••••••"
                                />
                            </div>

                            <div className="form-group">
                                <label className="form-label">{t('profile.newPassword') || 'New Password'}</label>
                                <input
                                    type="password"
                                    name="newPassword"
                                    className="form-input"
                                    value={formData.newPassword}
                                    onChange={handleChange}
                                    required
                                    placeholder="••••••••"
                                />
                            </div>

                            <div className="form-group">
                                <label className="form-label">{t('profile.confirmNewPassword') || 'Confirm New Password'}</label>
                                <input
                                    type="password"
                                    name="confirmPassword"
                                    className="form-input"
                                    value={formData.confirmPassword}
                                    onChange={handleChange}
                                    required
                                    placeholder="••••••••"
                                />
                            </div>

                            <div className="modal-actions">
                                <button type="button" className="btn btn-secondary" onClick={onClose}>
                                    {t('common.cancel') || 'Cancel'}
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={loading}>
                                    {loading ? (t('dashboard.changing') || 'Changing...') : t('profile.changePassword') || 'Change Password'}
                                </button>
                            </div>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );

    return createPortal(content, document.body);
};

export default ChangePasswordModal;
