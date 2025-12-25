import React from 'react';
import { useTranslation } from '../../hooks/useTranslation';

const Footer = () => {
  const { t } = useTranslation();

  const scrollToSection = (e, sectionId) => {
    e.preventDefault();
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <footer className="footer">
      <div className="footer-content">
        <div className="footer-brand">
          <h3>Dablja<span className="logo-accent">AR</span></h3>
          <p>{t('footer.description')}</p>
        </div>

        <div className="footer-links">
          <h4>{t('footer.product')}</h4>
          <ul>
            <li><a href="#features" onClick={(e) => scrollToSection(e, 'features')}>{t('footer.features')}</a></li>
            <li><a href="#pricing" onClick={(e) => scrollToSection(e, 'pricing')}>{t('footer.pricing')}</a></li>
            <li><a href="#demo" onClick={(e) => scrollToSection(e, 'demo')}>{t('footer.demo')}</a></li>
            <li><a href="#api" onClick={(e) => scrollToSection(e, 'api')}>{t('footer.api')}</a></li>
          </ul>
        </div>

        <div className="footer-links">
          <h4>{t('footer.company')}</h4>
          <ul>
            <li><a href="#about" onClick={(e) => scrollToSection(e, 'about')}>{t('footer.about')}</a></li>
            <li><a href="#team" onClick={(e) => scrollToSection(e, 'team')}>{t('footer.team')}</a></li>
            <li><a href="#careers" onClick={(e) => scrollToSection(e, 'careers')}>{t('footer.careers')}</a></li>
            <li><a href="#contact" onClick={(e) => scrollToSection(e, 'contact')}>{t('footer.contact')}</a></li>
          </ul>
        </div>

        <div className="footer-links">
          <h4>{t('footer.resources')}</h4>
          <ul>
            <li><a href="#docs" onClick={(e) => scrollToSection(e, 'docs')}>{t('footer.docs')}</a></li>
            <li><a href="#blog" onClick={(e) => scrollToSection(e, 'blog')}>{t('footer.blog')}</a></li>
            <li><a href="#support" onClick={(e) => scrollToSection(e, 'support')}>{t('footer.support')}</a></li>
            <li><a href="#status" onClick={(e) => scrollToSection(e, 'status')}>{t('footer.status')}</a></li>
          </ul>
        </div>
      </div>

      <div className="footer-bottom">
        <p>{t('footer.copyright')}</p>
      </div>
    </footer>
  );
};

export default Footer;
