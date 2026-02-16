import React from 'react';
import { useTranslation } from '../../hooks/useTranslation';

const HeroSection = () => {
  const { t } = useTranslation();

  const scrollToSection = (e, sectionId) => {
    e.preventDefault();
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <section id="home" className="hero">
      <div className="container-large">
        <div className="hero-grid">
          <div className="hero-left">
            <div className="hero-badge">
              <span className="badge-dot"></span>
              <span>{t('hero.badge')}</span>
            </div>
            <h1 className="hero-title">
              <span>{t('hero.title1')}</span><br />
              <span className="gradient-text">{t('hero.title2')}</span>
            </h1>
            <p className="hero-description">{t('hero.description')}</p>
            <div className="hero-cta">
              <a href="#demo" className="btn btn-primary" onClick={(e) => scrollToSection(e, 'demo')}>
                <span>{t('hero.startFree')}</span>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M4 10h12m0 0l-4-4m4 4l-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </a>
              <a href="#how-it-works" className="btn btn-secondary-outline" onClick={(e) => scrollToSection(e, 'how-it-works')}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M10 18a8 8 0 100-16 8 8 0 000 16z" stroke="currentColor" strokeWidth="2" />
                  <path d="M8 7.5l4 2.5-4 2.5V7.5z" fill="currentColor" />
                </svg>
                <span>{t('hero.watchDemo')}</span>
              </a>
            </div>
            <div className="hero-stats">
              <div className="stat-item">
                <h3>15K+</h3>
                <p>{t('stats.videos')}</p>
              </div>
              <div className="stat-item">
                <h3>98%</h3>
                <p>{t('stats.accuracy')}</p>
              </div>
              <div className="stat-item">
                <h3>2 Min</h3>
                <p>{t('stats.processing')}</p>
              </div>
            </div>
          </div>
          <div className="hero-right">
            <div className="mockup-container">
              <div className="mockup-window">
                <div className="window-header">
                  <div className="window-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <div className="window-title">dabljaar.ai</div>
                </div>
                <div className="window-content">
                  <div className="video-preview">
                    <div className="preview-overlay">
                      <div className="play-icon">
                        <svg width="60" height="60" viewBox="0 0 60 60" fill="none">
                          <circle cx="30" cy="30" r="30" fill="white" opacity="0.9" />
                          <path d="M24 20l16 10-16 10V20z" fill="#667eea" />
                        </svg>
                      </div>
                    </div>
                    <div className="waveform">
                      <span style={{ height: '40%' }}></span>
                      <span style={{ height: '70%' }}></span>
                      <span style={{ height: '50%' }}></span>
                      <span style={{ height: '85%' }}></span>
                      <span style={{ height: '60%' }}></span>
                      <span style={{ height: '90%' }}></span>
                      <span style={{ height: '75%' }}></span>
                      <span style={{ height: '55%' }}></span>
                      <span style={{ height: '80%' }}></span>
                      <span style={{ height: '45%' }}></span>
                    </div>
                  </div>
                  <div className="process-indicator">
                    <div className="process-step active">
                      <span className="step-icon">🎤</span>
                      <span className="step-label">{t('process.transcribe')}</span>
                    </div>
                    <div className="process-arrow">→</div>
                    <div className="process-step">
                      <span className="step-icon">🔄</span>
                      <span className="step-label">{t('process.translate')}</span>
                    </div>
                    <div className="process-arrow">→</div>
                    <div className="process-step">
                      <span className="step-icon">🔊</span>
                      <span className="step-label">{t('process.generate')}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="floating-badge badge-1">
                <span className="badge-icon">✓</span>
                <span>{t('badge.native')}</span>
              </div>
              <div className="floating-badge badge-2">
                <span className="badge-icon">⚡</span>
                <span>{t('badge.faster')}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;

