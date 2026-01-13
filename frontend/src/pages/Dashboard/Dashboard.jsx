import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../../hooks/useTranslation';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import '../../styles/dashboard.css';

const Dashboard = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [activeTab, setActiveTab] = useState('video');
  const [isDragOver, setIsDragOver] = useState(false);
  const [formData, setFormData] = useState({
    outputType: 'both',
    domain: 'general',
    voice: 'male1',
    translationStyle: 'neutral',
    textInput: ''
  });
  const [processingJobs] = useState([
    {
      id: 1,
      name: 'Video_123.mp4',
      progress: 45,
      estTime: '2 minutes'
    }
  ]);
  const [recentJobs] = useState([
    {
      id: 1,
      name: 'Tech_Tutorial.mp4',
      status: 'completed',
      type: 'success'
    },
    {
      id: 2,
      name: 'Medical_Lecture.mp4',
      status: 'completed',
      type: 'success'
    },
    {
      id: 3,
      name: 'Large_Video.mp4',
      status: 'failed',
      type: 'failed'
    }
  ]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      alert(`File uploaded: ${file.name} (Demo)`);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      alert(`File dropped: ${file.name} (Demo)`);
    }
  };

  const handleStartProcessing = () => {
    alert('Processing started! (Demo)');
  };

  const handlePreview = (id) => {
    alert(`Preview job ${id} (Demo)`);
  };

  const handleDownload = (id) => {
    alert(`Download job ${id} (Demo)`);
  };

  const handleRetry = (id) => {
    alert(`Retry job ${id} (Demo)`);
  };

  const handleDetails = (id) => {
    alert(`Details for job ${id} (Demo)`);
  };

  const handleViewFullHistory = () => {
    navigate('/history');
  };

  const handleUpgradePremium = () => {
    alert('Upgrade to Premium (Demo)');
  };

  return (
    <div className="dashboard-page">
      <BackgroundDecorations />
      <Navbar />
      
      <div className="main-container">
        {/* Welcome Section */}
        <div className="welcome-section">
          <div className="welcome-content">
            <div className="welcome-text">
              <h1>{t('dashboard.welcome')}</h1>
              <p>{t('dashboard.creditsRemaining')}</p>
            </div>
            <button 
              className="btn-upgrade" 
              onClick={handleUpgradePremium}
            >
              {t('dashboard.upgradePremium')}
            </button>
          </div>
        </div>

        {/* Upload Content */}
        <div className="card">
          <h2 className="card-title">
            <span>📤</span>
            <span>{t('dashboard.uploadContent')}</span>
          </h2>

          {/* Tabs */}
          <div className="tabs">
            <button 
              className={`tab ${activeTab === 'video' ? 'active' : ''}`}
              onClick={() => setActiveTab('video')}
            >
              {t('dashboard.tabVideo')}
            </button>
            <button 
              className={`tab ${activeTab === 'audio' ? 'active' : ''}`}
              onClick={() => setActiveTab('audio')}
            >
              {t('dashboard.tabAudio')}
            </button>
            <button 
              className={`tab ${activeTab === 'text' ? 'active' : ''}`}
              onClick={() => setActiveTab('text')}
            >
              {t('dashboard.tabText')}
            </button>
          </div>

          {/* Upload Area */}
          {(activeTab === 'video' || activeTab === 'audio') && (
            <div 
              className={`upload-area ${isDragOver ? 'drag-over' : ''}`}
              onClick={handleFileSelect}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <div className="upload-icon">📁</div>
              <div className="upload-text">
                <h3>{t('dashboard.uploadTitle')}</h3>
                <p>{t('dashboard.uploadSubtitle')}</p>
              </div>
              <div className="upload-formats">
                <span>{t('dashboard.supportedFormats')}</span>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                hidden
                accept={activeTab === 'video' ? 'video/*' : 'audio/*'}
                onChange={handleFileChange}
              />
            </div>
          )}

          {/* Text Input */}
          {(activeTab === 'text' || activeTab === 'video' || activeTab === 'audio') && (
            <div className="text-input-area">
              <p className="text-input-label">{t('dashboard.orDirectText')}</p>
              <textarea
                name="textInput"
                value={formData.textInput}
                onChange={handleInputChange}
                placeholder={t('dashboard.textPlaceholder')}
              />
            </div>
          )}
        </div>

        {/* Processing Options */}
        <div className="card">
          <h2 className="card-title">
            <span>⚙️</span>
            <span>{t('dashboard.processingOptions')}</span>
          </h2>

          <div className="options-grid">
            {/* Left Column */}
            <div>
              {/* Output Type */}
              <div className="option-group">
                <label className="option-label">{t('dashboard.outputType')}</label>
                <div className="radio-group">
                  <div className="radio-item">
                    <input
                      type="radio"
                      id="dubbing"
                      name="outputType"
                      value="dubbing"
                      checked={formData.outputType === 'dubbing'}
                      onChange={handleInputChange}
                    />
                    <label htmlFor="dubbing">{t('dashboard.dubbingOnly')}</label>
                  </div>
                  <div className="radio-item">
                    <input
                      type="radio"
                      id="subtitles"
                      name="outputType"
                      value="subtitles"
                      checked={formData.outputType === 'subtitles'}
                      onChange={handleInputChange}
                    />
                    <label htmlFor="subtitles">{t('dashboard.subtitlesOnly')}</label>
                  </div>
                  <div className="radio-item">
                    <input
                      type="radio"
                      id="both"
                      name="outputType"
                      value="both"
                      checked={formData.outputType === 'both'}
                      onChange={handleInputChange}
                    />
                    <label htmlFor="both">{t('dashboard.both')}</label>
                  </div>
                </div>
              </div>

              {/* Domain */}
              <div className="option-group" style={{marginTop: '24px'}}>
                <label className="option-label">{t('dashboard.domain')}</label>
                <select
                  className="form-select"
                  name="domain"
                  value={formData.domain}
                  onChange={handleInputChange}
                >
                  <option value="general">{t('dashboard.domainGeneral')}</option>
                  <option value="medical">{t('dashboard.domainMedical')}</option>
                  <option value="legal">{t('dashboard.domainLegal')}</option>
                  <option value="technical">{t('dashboard.domainTechnical')}</option>
                  <option value="education">{t('dashboard.domainEducation')}</option>
                </select>
              </div>
            </div>

            {/* Right Column */}
            <div>
              {/* Voice Selection */}
              <div className="option-group">
                <label className="option-label">{t('dashboard.voiceSelection')}</label>
                <select
                  className="form-select"
                  name="voice"
                  value={formData.voice}
                  onChange={handleInputChange}
                >
                  <option value="male1">{t('dashboard.voiceMale1')}</option>
                  <option value="male2">{t('dashboard.voiceMale2')}</option>
                  <option value="female1">{t('dashboard.voiceFemale1')}</option>
                  <option value="female2">{t('dashboard.voiceFemale2')}</option>
                  <option value="clone">{t('dashboard.voiceClone')}</option>
                </select>
              </div>

              {/* Translation Style */}
              <div className="option-group" style={{marginTop: '24px'}}>
                <label className="option-label">{t('dashboard.translationStyle')}</label>
                <select
                  className="form-select"
                  name="translationStyle"
                  value={formData.translationStyle}
                  onChange={handleInputChange}
                >
                  <option value="neutral">{t('dashboard.styleNeutral')}</option>
                  <option value="literal">{t('dashboard.styleLiteral')}</option>
                  <option value="casual">{t('dashboard.styleCasual')}</option>
                  <option value="formal">{t('dashboard.styleFormal')}</option>
                </select>
              </div>
            </div>
          </div>

          {/* Credits Info */}
          <div className="credits-info">
            <span className="credits-required">
              <span>{t('dashboard.creditsRequired')}</span> 5
            </span>
            <span className="credits-required">
              <span>{t('dashboard.yourCredits')}</span> 25
            </span>
          </div>

          {/* Start Button */}
          <button className="btn btn-primary" onClick={handleStartProcessing}>
            <span>{t('dashboard.startProcessing')}</span>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M6 4l8 6-8 6V4z" fill="currentColor"/>
            </svg>
          </button>
        </div>

        {/* Current Processing Queue */}
        <div className="card progress-container">
          <h2 className="card-title">
            <span>⏳</span>
            <span>{t('dashboard.currentQueue')}</span>
          </h2>

          {processingJobs.length > 0 ? (
            processingJobs.map((job) => (
              <div key={job.id} className="job-item">
                <div className="job-header">
                  <span className="job-name">{job.name}</span>
                  <span className="job-status">
                    {t('dashboard.processing')} {job.progress}%
                  </span>
                </div>
                <div className="progress-bar">
                  <div className="progress-fill" style={{width: `${job.progress}%`}}></div>
                </div>
                <div className="job-time">
                  <span>{t('dashboard.estTime')}</span> {job.estTime}
                </div>
              </div>
            ))
          ) : (
            <p style={{color: 'var(--text-light)', textAlign: 'center', padding: '20px'}}>
              {t('dashboard.noProcessingJobs')}
            </p>
          )}
        </div>

        {/* Recent Jobs */}
        <div className="card">
          <h2 className="card-title">
            <span>📋</span>
            <span>{t('dashboard.recentJobs')}</span>
          </h2>

          <div className="recent-jobs">
            {recentJobs.map((job) => (
              <div key={job.id} className="recent-job-item">
                <div className="job-info">
                  <div className={`job-icon ${job.type}`}>
                    {job.type === 'success' ? '✓' : '✗'}
                  </div>
                  <div className="job-details">
                    <h4>{job.name}</h4>
                    <p>{t(`dashboard.${job.status}`)}</p>
                  </div>
                </div>
                <div className="job-actions">
                  {job.status === 'completed' ? (
                    <>
                      <button 
                        className="btn btn-secondary"
                        onClick={() => handlePreview(job.id)}
                      >
                        {t('dashboard.preview')}
                      </button>
                      <button 
                        className="btn btn-secondary"
                        onClick={() => handleDownload(job.id)}
                      >
                        {t('dashboard.download')}
                      </button>
                    </>
                  ) : (
                    <>
                      <button 
                        className="btn btn-secondary"
                        onClick={() => handleRetry(job.id)}
                      >
                        {t('dashboard.retry')}
                      </button>
                      <button 
                        className="btn btn-secondary"
                        onClick={() => handleDetails(job.id)}
                      >
                        {t('dashboard.details')}
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>

          <button 
            className="btn btn-primary" 
            style={{marginTop: '24px'}}
            onClick={handleViewFullHistory}
          >
            {t('dashboard.viewFullHistory')}
          </button>
        </div>
      </div>
      <Footer />
    </div>
  );
};

export default Dashboard;

