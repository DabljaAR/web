import React from 'react';
import { useTranslation } from '../../hooks/useTranslation';

const HowItWorksSection = () => {
  const { t } = useTranslation();

  return (
    <section id="how-it-works" className="how-it-works">
      <div className="container">
        <h2 className="section-title">{t('howItWorks.title')}</h2>
        <div className="workflow">
          <div className="workflow-step">
            <div className="step-number">1</div>
            <div className="step-content">
              <h3>{t('howItWorks.step1Title')}</h3>
              <p>{t('howItWorks.step1Text')}</p>
            </div>
          </div>
          <div className="workflow-arrow">→</div>
          <div className="workflow-step">
            <div className="step-number">2</div>
            <div className="step-content">
              <h3>{t('howItWorks.step2Title')}</h3>
              <p>{t('howItWorks.step2Text')}</p>
            </div>
          </div>
          <div className="workflow-arrow">→</div>
          <div className="workflow-step">
            <div className="step-number">3</div>
            <div className="step-content">
              <h3>{t('howItWorks.step3Title')}</h3>
              <p>{t('howItWorks.step3Text')}</p>
            </div>
          </div>
          <div className="workflow-arrow">→</div>
          <div className="workflow-step">
            <div className="step-number">4</div>
            <div className="step-content">
              <h3>{t('howItWorks.step4Title')}</h3>
              <p>{t('howItWorks.step4Text')}</p>
            </div>
          </div>
          <div className="workflow-arrow">→</div>
          <div className="workflow-step">
            <div className="step-number">5</div>
            <div className="step-content">
              <h3>{t('howItWorks.step5Title')}</h3>
              <p>{t('howItWorks.step5Text')}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default HowItWorksSection;

