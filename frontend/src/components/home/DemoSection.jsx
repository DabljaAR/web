import React, { useRef, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';

const DemoSection = () => {
  const { t } = useTranslation();
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleFile = (file) => {
    console.log('File selected:', file.name);
    alert(`File "${file.name}" selected! (Demo - no actual upload)`);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFile(files[0]);
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  };

  return (
    <section id="demo" className="demo-section">
      <div className="container">
        <div className="section-header-custom">
          <span className="section-eyebrow">{t('demo.eyebrow')}</span>
          <h2 className="section-title-custom">{t('demo.title')}</h2>
          <p className="section-subtitle">{t('demo.subtitle')}</p>
        </div>
        <div className="upload-container">
          <div
            className="upload-area"
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              borderColor: isDragging ? 'var(--accent-blue)' : undefined,
              background: isDragging ? 'rgba(102, 126, 234, 0.05)' : undefined
            }}
          >
            <div className="upload-icon">📤</div>
            <h3>{t('demo.uploadTitle')}</h3>
            <p>{t('demo.uploadText')}</p>
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              style={{ display: 'none' }}
              onChange={handleFileInput}
            />
            <button className="btn btn-primary">
              <span>{t('demo.chooseFile')}</span>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M4 10h12m0 0l-4-4m4 4l-4 4" stroke="currentColor" strokeWidth="2"/>
              </svg>
            </button>
          </div>
          <div className="upload-info">
            <div className="info-item">
              <span className="info-icon">✓</span>
              <span>{t('demo.info1')}</span>
            </div>
            <div className="info-item">
              <span className="info-icon">✓</span>
              <span>{t('demo.info2')}</span>
            </div>
            <div className="info-item">
              <span className="info-icon">✓</span>
              <span>{t('demo.info3')}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default DemoSection;

