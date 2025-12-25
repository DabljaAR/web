import React from 'react';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import '../../styles/home.css';

const About = () => {
  return (
    <div>
      <BackgroundDecorations />
      <Navbar />
      <section className="about-section">
        <div className="container">
          <div className="about-content">
            <div className="section-header-custom">
              <span className="section-eyebrow">About Us</span>
              <h1 className="section-title-custom">DabljaAR</h1>
              <p className="section-subtitle">
                Breaking down language barriers with AI-powered video dubbing
              </p>
            </div>
            
            <div className="about-grid">
              <div className="about-card">
                <div className="about-icon">🎯</div>
                <h3>Our Mission</h3>
                <p>
                  To make quality content accessible to Arabic speakers worldwide by providing 
                  fast, accurate, and natural-sounding video dubbing powered by cutting-edge AI technology.
                </p>
              </div>
              
              <div className="about-card">
                <div className="about-icon">🚀</div>
                <h3>Technology</h3>
                <p>
                  Built with state-of-the-art AI models including Fast Whisper for transcription, 
                  NLLB-200 for translation, and MMS for voice synthesis, all enhanced with RAG technology.
                </p>
              </div>
              
              <div className="about-card">
                <div className="about-icon">✨</div>
                <h3>Features</h3>
                <ul className="about-list">
                  <li>Component-based architecture</li>
                  <li>Custom React hooks</li>
                  <li>Service layer for API calls</li>
                  <li>State management setup</li>
                  <li>Utility functions and constants</li>
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
