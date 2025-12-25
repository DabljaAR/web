import React from 'react';
import { useTranslation } from '../../hooks/useTranslation';

const FeaturesSection = () => {
  const { t } = useTranslation();

  return (
    <section id="features" className="features-section">
      <div className="container">
        <h2 className="section-title">{t('features.title')}</h2>
        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-number">01</div>
            <h3>{t('features.feature1Title')}</h3>
            <p>{t('features.feature1Text')}</p>
          </div>
          <div className="feature-card">
            <div className="feature-number">02</div>
            <h3>{t('features.feature2Title')}</h3>
            <p>{t('features.feature2Text')}</p>
          </div>
          <div className="feature-card">
            <div className="feature-number">03</div>
            <h3>{t('features.feature3Title')}</h3>
            <p>{t('features.feature3Text')}</p>
          </div>
          <div className="feature-card">
            <div className="feature-number">04</div>
            <h3>{t('features.feature4Title')}</h3>
            <p>{t('features.feature4Text')}</p>
          </div>
          <div className="feature-card">
            <div className="feature-number">05</div>
            <h3>{t('features.feature5Title')}</h3>
            <p>{t('features.feature5Text')}</p>
          </div>
          <div className="feature-card">
            <div className="feature-number">06</div>
            <h3>{t('features.feature6Title')}</h3>
            <p>{t('features.feature6Text')}</p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;

