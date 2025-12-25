import React from 'react';
import { useNavigate } from 'react-router-dom';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';

import Footer from '../../components/layout/Footer';
import { useTranslation } from '../../hooks/useTranslation';
import '../../styles/home.css';

const NotFound = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div>
      <BackgroundDecorations />
      <Navbar />
      <section className="not-found-section">
        <div className="container">
          <div className="not-found-content">
            <div className="not-found-illustration">
              <div className="not-found-number">404</div>
              <div className="not-found-shapes">
                <div className="shape shape-1"></div>
                <div className="shape shape-2"></div>
                <div className="shape shape-3"></div>
              </div>
            </div>
            <h1 className="not-found-title">{t('notFound.subtitle')}</h1>
            <p className="not-found-description">{t('notFound.description')}</p>
            <div className="not-found-actions">
              <button 
                className="btn btn-primary" 
                onClick={() => navigate('/')}
              >
                <span>{t('notFound.goHome')}</span>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M4 10h12m0 0l-4-4m4 4l-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
              </button>
              <button 
                className="btn btn-secondary-outline" 
                onClick={() => navigate(-1)}
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M12 4l-8 8 8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
                <span>{t('notFound.goBack')}</span>
              </button>
            </div>
          </div>
        </div>
      </section>
      <Footer />
    </div>
  );
};

export default NotFound;
