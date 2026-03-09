import React from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import '../../styles/home.css';

const About = () => {
  const { t } = useTranslation();

  return (
    <div>
      <BackgroundDecorations />
      <Navbar />
      <section className="about-section">
        <div className="container">
          <div className="about-content">
            <div className="section-header-custom">
              <span className="section-eyebrow">{t('about.eyebrow')}</span>
              <h1 className="section-title-custom">{t('about.title')}</h1>
              <p className="section-subtitle">
                {t('about.subtitle')}
              </p>
            </div>

            <div className="about-grid">
              <div className="about-card">
                <div className="about-icon">🎯</div>
                <h3>{t('about.missionTitle')}</h3>
                <p>
                  {t('about.missionText')}
                </p>
              </div>

              <div className="about-card">
                <div className="about-icon">🚀</div>
                <h3>{t('about.techTitle')}</h3>
                <p>
                  {t('about.techText')}
                </p>
              </div>

              <div className="about-card">
                <div className="about-icon">✨</div>
                <h3>{t('about.featuresTitle')}</h3>
                <ul className="about-list">
                  <li>{t('about.featureListItem1')}</li>
                  <li>{t('about.featureListItem2')}</li>
                  <li>{t('about.featureListItem3')}</li>
                  <li>{t('about.featureListItem4')}</li>
                  <li>{t('about.featureListItem5')}</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </section>
      <Footer />
    </div>
  );
};

export default About;
