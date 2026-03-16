import React, { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { useAuth } from '../../hooks/useAuth';

const Navbar = () => {
  const { t } = useTranslation();
  const { toggleTheme } = useTheme();
  const { language, toggleLanguage } = useLanguage();
  const { isAuthenticated, logout, user } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const isHomePage = location.pathname === '/';

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 50);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollToSection = (sectionId) => {
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const handleNavClick = (e, sectionId) => {
    e.preventDefault();
    setIsMenuOpen(false); // Close mobile menu when clicking a link
    if (isHomePage) {
      // If on home page, just scroll to section
      scrollToSection(sectionId);
    } else {
      // If on other page, navigate to home then scroll
      navigate('/');
      // Wait for navigation to complete, then scroll
      setTimeout(() => {
        scrollToSection(sectionId);
      }, 100);
    }
  };

  const toggleMenu = () => {
    setIsMenuOpen(!isMenuOpen);
  };

  const toggleUserMenu = () => {
    setIsUserMenuOpen(!isUserMenuOpen);
  };

  const handleUserMenuClick = (path) => {
    navigate(path);
    setIsUserMenuOpen(false);
    setIsMenuOpen(false);
  };

  const handleLogout = () => {
    logout();
    window.location.href = '/';
  };

  // Close user menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (isUserMenuOpen && !event.target.closest('.user-menu-container')) {
        setIsUserMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isUserMenuOpen]);

  return (
    <>
      <nav className={`navbar ${scrolled ? 'scrolled' : ''}`}>
        <div className="container">
          <div className="nav-wrapper">
            <Link to="/" className="logo" onClick={() => setIsMenuOpen(false)}>
              <span className="logo-text">Dablja<span className="logo-accent">AR</span></span>
            </Link>
            <ul className={`nav-menu ${isMenuOpen ? 'nav-menu-open' : ''}`}>

              {isHomePage ? (
                <>
                  <li><a href="#home" onClick={(e) => handleNavClick(e, 'home')}>{t('nav.home')}</a></li>
                  <li><a href="#features" onClick={(e) => handleNavClick(e, 'features')}>{t('nav.features')}</a></li>
                  <li><a href="#how-it-works" onClick={(e) => handleNavClick(e, 'how-it-works')}>{t('nav.howItWorks')}</a></li>
                  <li><a href="#demo" onClick={(e) => handleNavClick(e, 'demo')}>{t('nav.demo')}</a></li>
                  <li><a href="#team" onClick={(e) => handleNavClick(e, 'team')}>{t('nav.team')}</a></li>
                </>
              ) : isAuthenticated ? (
                <>
                  <li><Link to="/" onClick={() => setIsMenuOpen(false)}>{t('nav.home')}</Link></li>
                  <li><Link to="/dashboard" onClick={() => setIsMenuOpen(false)} className={location.pathname === '/dashboard' ? 'active' : ''}>{t('nav.dashboard')}</Link></li>
                  <li><Link to="/history" onClick={() => setIsMenuOpen(false)} className={location.pathname === '/history' ? 'active' : ''}>{t('nav.history')}</Link></li>
                  <li><Link to="/original-videos" onClick={() => setIsMenuOpen(false)} className={location.pathname === '/original-videos' ? 'active' : ''}>{t('nav.myLibrary')}</Link></li>
                  <li><Link to="/profile" onClick={() => setIsMenuOpen(false)} className={location.pathname === '/profile' ? 'active' : ''}>{t('nav.profile')}</Link></li>
                  <li><Link to="/about" onClick={() => setIsMenuOpen(false)} className={location.pathname === '/about' ? 'active' : ''}>{t('nav.about')}</Link></li>
                  <li>
                    <div className="credits-badge">
                      <span>🪙</span>
                      <span>{t('nav.credits')}</span>
                      <span>25</span>
                    </div>
                  </li>
                </>
              ) : (
                <>
                  <li><Link to="/" onClick={() => setIsMenuOpen(false)}>{t('nav.home')}</Link></li>
                  <li><Link to="/about" onClick={() => setIsMenuOpen(false)} className={location.pathname === '/about' ? 'active' : ''}>{t('nav.about')}</Link></li>
                </>
              )}
            </ul>
            <div className="nav-controls">
              <button className="lang-toggle" onClick={toggleLanguage} aria-label="Switch Language">
                {language === 'en' ? 'EN' : 'AR'}
              </button>
              <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle Theme">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                  <path className="sun-icon" d="M10 2.5a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 2.5zm0 10a2.5 2.5 0 100-5 2.5 2.5 0 000 5zm0 1.5a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5a.75.75 0 01.75-.75zM17.5 10a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5a.75.75 0 01.75.75zm-13 0a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5a.75.75 0 01.75.75zm11.95 4.95a.75.75 0 01-1.06 0l-1.06-1.06a.75.75 0 111.06-1.06l1.06 1.06a.75.75 0 010 1.06zM5.11 5.11a.75.75 0 01-1.06 0L2.99 3.05a.75.75 0 011.06-1.06l1.06 1.06a.75.75 0 010 1.06zm9.78 0a.75.75 0 010-1.06l1.06-1.06a.75.75 0 111.06 1.06l-1.06 1.06a.75.75 0 01-1.06 0zM5.11 14.89a.75.75 0 010-1.06l1.06-1.06a.75.75 0 111.06 1.06l-1.06 1.06a.75.75 0 01-1.06 0z" />
                </svg>
              </button>
              {!isAuthenticated ? (
                <>
                  {isHomePage ? (
                    <>
                      <Link to="/login" className="btn-login" style={{ textDecoration: 'none' }} onClick={() => setIsMenuOpen(false)}>{t('nav.login')}</Link>
                      <a href="#demo" className="btn-demo" onClick={(e) => handleNavClick(e, 'demo')} style={{ textDecoration: 'none' }}>{t('nav.tryNow')}</a>
                    </>
                  ) : (
                    <Link to="/login" className="btn-login" style={{ textDecoration: 'none' }} onClick={() => setIsMenuOpen(false)}>{t('nav.login')}</Link>
                  )}
                </>
              ) : (
                <div className="user-menu-container" style={{ position: 'relative' }}>
                  <button
                    className="btn-user-menu"
                    onClick={toggleUserMenu}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '8px 16px',
                      background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-cyan))',
                      color: 'white',
                      border: 'none',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      fontSize: '14px',
                      fontWeight: '500',
                      transition: 'all 0.2s ease'
                    }}
                  >
                    <span>{user?.username || user?.email || (t('nav.user') || 'User')}</span>
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 16 16"
                      fill="currentColor"
                      style={{
                        transform: isUserMenuOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                        transition: 'transform 0.2s'
                      }}
                    >
                      <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>

                  {isUserMenuOpen && (
                    <div
                      style={{
                        position: 'absolute',
                        top: '100%',
                        right: 0,
                        marginTop: '8px',
                        background: 'var(--bg-white)',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '8px',
                        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
                        minWidth: '200px',
                        zIndex: 1000,
                        overflow: 'hidden'
                      }}
                    >
                      <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
                        <div style={{ fontWeight: '600', fontSize: '14px', color: 'var(--text-dark)' }}>
                          {user?.first_name && user?.last_name
                            ? `${user.first_name} ${user.last_name}`
                            : user?.username || user?.email || (t('nav.user') || 'User')}
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text-light)', marginTop: '4px' }}>
                          {user?.email}
                        </div>
                      </div>

                      <Link
                        to="/dashboard"
                        onClick={() => handleUserMenuClick('/dashboard')}
                        style={{
                          display: 'block',
                          padding: '12px 16px',
                          color: location.pathname === '/dashboard' ? 'var(--accent-blue)' : 'var(--text-dark)',
                          textDecoration: 'none',
                          fontSize: '14px',
                          transition: 'all 0.2s ease',
                          backgroundColor: location.pathname === '/dashboard' ? 'rgba(102, 126, 234, 0.1)' : 'transparent'
                        }}
                        onMouseEnter={(e) => {
                          if (location.pathname !== '/dashboard') {
                            e.target.style.backgroundColor = 'var(--bg-primary)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          e.target.style.backgroundColor = location.pathname === '/dashboard' ? 'rgba(102, 126, 234, 0.1)' : 'transparent';
                        }}
                      >
                        {t('nav.dashboard')}
                      </Link>

                      <Link
                        to="/history"
                        onClick={() => handleUserMenuClick('/history')}
                        style={{
                          display: 'block',
                          padding: '12px 16px',
                          color: location.pathname === '/history' ? 'var(--accent-blue)' : 'var(--text-dark)',
                          textDecoration: 'none',
                          fontSize: '14px',
                          transition: 'all 0.2s ease',
                          backgroundColor: location.pathname === '/history' ? 'rgba(102, 126, 234, 0.1)' : 'transparent'
                        }}
                        onMouseEnter={(e) => {
                          if (location.pathname !== '/history') {
                            e.target.style.backgroundColor = 'var(--bg-primary)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          e.target.style.backgroundColor = location.pathname === '/history' ? 'rgba(102, 126, 234, 0.1)' : 'transparent';
                        }}
                      >
                        {t('nav.history')}
                      </Link>

                      <Link
                        to="/original-videos"
                        onClick={() => handleUserMenuClick('/original-videos')}
                        style={{
                          display: 'block',
                          padding: '12px 16px',
                          color: location.pathname === '/original-videos' ? 'var(--accent-blue)' : 'var(--text-dark)',
                          textDecoration: 'none',
                          fontSize: '14px',
                          transition: 'all 0.2s ease',
                          backgroundColor: location.pathname === '/original-videos' ? 'rgba(102, 126, 234, 0.1)' : 'transparent'
                        }}
                        onMouseEnter={(e) => {
                          if (location.pathname !== '/original-videos') {
                            e.target.style.backgroundColor = 'var(--bg-primary)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          e.target.style.backgroundColor = location.pathname === '/original-videos' ? 'rgba(102, 126, 234, 0.1)' : 'transparent';
                        }}
                      >
                        {t('nav.myLibrary')}
                      </Link>

                      <Link
                        to="/profile"
                        onClick={() => handleUserMenuClick('/profile')}
                        style={{
                          display: 'block',
                          padding: '12px 16px',
                          color: location.pathname === '/profile' ? 'var(--accent-blue)' : 'var(--text-dark)',
                          textDecoration: 'none',
                          fontSize: '14px',
                          transition: 'all 0.2s ease',
                          backgroundColor: location.pathname === '/profile' ? 'rgba(102, 126, 234, 0.1)' : 'transparent'
                        }}
                        onMouseEnter={(e) => {
                          if (location.pathname !== '/profile') {
                            e.target.style.backgroundColor = 'var(--bg-primary)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          e.target.style.backgroundColor = location.pathname === '/profile' ? 'rgba(102, 126, 234, 0.1)' : 'transparent';
                        }}
                      >
                        {t('nav.profile')}
                      </Link>

                      <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.1)', marginTop: '4px' }}></div>

                      <button
                        onClick={handleLogout}
                        style={{
                          width: '100%',
                          padding: '12px 16px',
                          background: 'transparent',
                          border: 'none',
                          color: 'var(--accent-red)',
                          textAlign: 'left',
                          cursor: 'pointer',
                          fontSize: '14px',
                          transition: 'all 0.2s ease'
                        }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = 'rgba(239, 68, 68, 0.1)'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                      >
                        {t('nav.logout')}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
            <div className={`hamburger ${isMenuOpen ? 'hamburger-active' : ''}`} onClick={toggleMenu} aria-label="Toggle Menu">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      </nav>
      {isMenuOpen && <div className="mobile-menu-overlay" onClick={() => setIsMenuOpen(false)}></div>}
    </>
  );
};

export default Navbar;

