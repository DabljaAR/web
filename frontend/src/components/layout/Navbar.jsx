import React, { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../contexts/ThemeContext';
import { useLanguage } from '../../contexts/LanguageContext';

const Navbar = () => {
  const { t } = useTranslation();
  const { toggleTheme } = useTheme();
  const { language, toggleLanguage } = useLanguage();
  const [scrolled, setScrolled] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
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
              ) : (
                <>
                  <li><Link to="/" onClick={() => setIsMenuOpen(false)}>{t('nav.home')}</Link></li>
                  <li><Link to="/dashboard" onClick={() => setIsMenuOpen(false)} className={location.pathname === '/dashboard' ? 'active' : ''}>{t('nav.dashboard')}</Link></li>
                  <li><Link to="/history" onClick={() => setIsMenuOpen(false)} className={location.pathname === '/history' ? 'active' : ''}>{t('nav.history')}</Link></li>
                  <li><Link to="/profile" onClick={() => setIsMenuOpen(false)} className={location.pathname === '/profile' ? 'active' : ''}>{t('nav.profile')}</Link></li>
                  <li>
                    <div className="credits-badge">
                      <span>🪙</span>
                      <span>{t('nav.credits')}</span>
                      <span>25</span>
                    </div>
                  </li>
                </>
              )}
            </ul>
            <div className="nav-controls">
              <button className="lang-toggle" onClick={toggleLanguage} aria-label="Switch Language">
                {language === 'en' ? 'EN' : 'AR'}
              </button>
              <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle Theme">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                  <path className="sun-icon" d="M10 2.5a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 2.5zm0 10a2.5 2.5 0 100-5 2.5 2.5 0 000 5zm0 1.5a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5a.75.75 0 01.75-.75zM17.5 10a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5a.75.75 0 01.75.75zm-13 0a.75.75 0 01-.75.75h-1.5a.75.75 0 010-1.5h1.5a.75.75 0 01.75.75zm11.95 4.95a.75.75 0 01-1.06 0l-1.06-1.06a.75.75 0 111.06-1.06l1.06 1.06a.75.75 0 010 1.06zM5.11 5.11a.75.75 0 01-1.06 0L2.99 3.05a.75.75 0 011.06-1.06l1.06 1.06a.75.75 0 010 1.06zm9.78 0a.75.75 0 010-1.06l1.06-1.06a.75.75 0 111.06 1.06l-1.06 1.06a.75.75 0 01-1.06 0zM5.11 14.89a.75.75 0 010-1.06l1.06-1.06a.75.75 0 111.06 1.06l-1.06 1.06a.75.75 0 01-1.06 0z"/>
                </svg>
              </button>
              {isHomePage ? (
                <>
                  <Link to="/login" className="btn-login" style={{textDecoration: 'none'}} onClick={() => setIsMenuOpen(false)}>{t('nav.login')}</Link>
                  <a href="#demo" className="btn-demo" onClick={(e) => handleNavClick(e, 'demo')} style={{textDecoration: 'none'}}>{t('nav.tryNow')}</a>
                </>
              ) : (
                <button 
                  className="btn-logout" 
                  onClick={() => {
                    alert('Logout (Demo)');
                    navigate('/');
                  }}
                >
                  {t('nav.logout')}
                </button>
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

