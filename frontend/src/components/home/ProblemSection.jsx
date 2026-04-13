import React from 'react';
import { useTranslation } from '../../hooks/useTranslation';

const ProblemSection = () => {
  const { t } = useTranslation();

  return (
    <section className="problem-section">
      <div className="container-large">
        <div className="section-header-custom">
          <span className="section-eyebrow">{t('problem.eyebrow')}</span>
          <h2 className="section-title-custom">{t('problem.title')}</h2>
          <p className="section-subtitle">{t('problem.subtitle')}</p>
        </div>
        <div className="problem-cards-wrapper">
          <div className="problem-card-modern">
            <div className="card-decoration"></div>
            <div className="feature-number">01</div>
            <h3>{t('features.feature1Title')}</h3>
            <p>{t('features.feature1Text')}</p>
          </div>
          <div className="problem-card-modern">
            <div className="card-decoration"></div>
            <div className="feature-number">02</div>
            <h3>{t('features.feature2Title')}</h3>
            <p>{t('features.feature2Text')}</p>
          </div>
          <div className="problem-card-modern">
            <div className="card-decoration"></div>
            <div className="feature-number">03</div>
            <h3>{t('features.feature3Title')}</h3>
            <p>{t('features.feature3Text')}</p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ProblemSection;

