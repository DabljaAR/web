import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import { useTranslation } from '../../hooks/useTranslation';
import '../../styles/home.css';

const ErrorPage = ({ errorCode = '500', title, description }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  // Pick up props from location state if available
  const stateCode = location.state?.errorCode || errorCode;
  const stateTitle = location.state?.title || title || t('errorPage.defaultTitle') || 'Internal Server Error';
  const stateDescription = location.state?.description || description || t('errorPage.defaultDescription') || 'Something went wrong on our end. Please try again later.';

  return (
    <div>
      <BackgroundDecorations />
      <Navbar />
      <section className="not-found-section">
        <div className="container">
          <div className="not-found-content">
            <div className="not-found-illustration">
              <div className="not-found-number">{stateCode}</div>
              <div className="not-found-shapes">
                <div className="shape shape-1" style={{ backgroundColor: 'var(--accent-red, #ef4444)' }}></div>
                <div className="shape shape-2" style={{ backgroundColor: 'var(--accent-orange, #f97316)' }}></div>
                <div className="shape shape-3" style={{ backgroundColor: 'var(--accent-pink, #ec4899)' }}></div>
              </div>
            </div>
            <h1 className="not-found-title">{stateTitle}</h1>
            <p className="not-found-description">{stateDescription}</p>
            <div className="not-found-actions">
              <button 
                className="btn btn-primary" 
                onClick={() => navigate('/')}
              >
                <span>{t('notFound.goHome') || 'Go Home'}</span>
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
                <span>{t('notFound.goBack') || 'Go Back'}</span>
              </button>
            </div>
          </div>
        </div>
      </section>
      <Footer />
    </div>
  );
};

export default ErrorPage;
