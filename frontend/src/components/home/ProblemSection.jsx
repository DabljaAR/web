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
            <div className="problem-icon-modern">📚</div>
            <h3>{t('problem.card1Title')}</h3>
            <p>{t('problem.card1Text')}</p>
            <div className="card-stat">
              <span className="stat-number">78%</span>
              <span className="stat-label">{t('problem.card1Stat')}</span>
            </div>
          </div>
          <div className="problem-card-modern">
            <div className="card-decoration"></div>
            <div className="problem-icon-modern">🗣️</div>
            <h3>{t('problem.card2Title')}</h3>
            <p>{t('problem.card2Text')}</p>
            <div className="card-stat">
              <span className="stat-number">450M</span>
              <span className="stat-label">{t('problem.card2Stat')}</span>
            </div>
          </div>
          <div className="problem-card-modern">
            <div className="card-decoration"></div>
            <div className="problem-icon-modern">💰</div>
            <h3>{t('problem.card3Title')}</h3>
            <p>{t('problem.card3Text')}</p>
            <div className="card-stat">
              <span className="stat-number">$5K+</span>
              <span className="stat-label">{t('problem.card3Stat')}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ProblemSection;

