import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../../hooks/useTranslation';
import { useAuth } from '../../hooks/useAuth';
import { mediaService } from '../../services/mediaService';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import '../../styles/dashboard.css';

const Dashboard = () => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  // Persist active tab in localStorage
  const [activeTab, setActiveTab] = useState(() => {
    return localStorage.getItem('dashboardActiveTab') || 'video';
  });

  const handleTabChange = (tabName) => {
    setActiveTab(tabName);
    localStorage.setItem('dashboardActiveTab', tabName);
    setSelectedFile(null); // Clear selected file when switching tabs
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const [isDragOver, setIsDragOver] = useState(false);

  // Upload states
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  const [formData, setFormData] = useState({
    outputType: 'both',
    domain: 'general',
    voice: 'male1',
    translationStyle: 'neutral',
    textInput: ''
  });
  const [processingJobs, setProcessingJobs] = useState([]);
  const [recentJobs, setRecentJobs] = useState([]);
  const [isPolling, setIsPolling] = useState(true);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch jobs
  const fetchJobs = async () => {
    try {
      const videos = await mediaService.getVideos();

      const pending = videos.filter(v => v.status === 'PENDING' || v.status === 'PROCESSING').map(v => ({
        id: v.id,
        name: v.title || v.original_filename,
        status: v.status.toLowerCase(),
        estTime: 'Processing...'
      }));

      const completed = videos.filter(v => v.status === 'COMPLETED' || v.status === 'FAILED').map(v => ({
        id: v.id,
        name: v.title || v.original_filename,
        status: v.status.toLowerCase(),
        type: v.status === 'COMPLETED' ? 'success' : 'failed'
      }));

      setProcessingJobs(pending);
      setRecentJobs(completed);

      // Poll only if there are pending jobs
      setIsPolling(pending.length > 0);

    } catch (error) {
      console.error("Error fetching jobs:", error);
      setIsPolling(false); // Stop polling on error to avoid loops? Or retry? Safer to stop or keep trying. Let's stop.
    } finally {
      setIsLoading(false);
    }
  };

  // Initial fetch on mount
  useEffect(() => {
    fetchJobs();
  }, []);

  // Polling effect
  useEffect(() => {
    let intervalId;
    if (isPolling) {
      intervalId = setInterval(fetchJobs, 5000); // 5 seconds
    }
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [isPolling]);

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
      setSelectedFile(file);
      // alert(`File selected: ${file.name}`);
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
      setSelectedFile(file);
      // alert(`File dropped: ${file.name}`);
    }
  };

  const handleStartProcessing = async () => {
    if (activeTab === 'text' && !formData.textInput && !selectedFile) {
      // Correct check logic for text tab
      if (!selectedFile && !formData.textInput) {
        alert(t('dashboard.textPlaceholder'));
        return;
      }
    }

    if ((activeTab === 'video' || activeTab === 'audio') && !selectedFile) {
      alert("Please select a file first.");
      return;
    }

    // If it's a file upload
    if (selectedFile) {
      // Validate file type
      if (activeTab === 'video' && !selectedFile.type.startsWith('video/')) {
        alert("Please upload a valid Video file.");
        return;
      }
      if (activeTab === 'audio') {
        const validAudioTypes = ['audio/mpeg', 'audio/wav', 'audio/mp4', 'audio/x-m4a', 'audio/mp3'];
        const validExtensions = ['.mp3', '.wav', '.m4a'];
        const fileExtension = selectedFile.name.toLowerCase().substring(selectedFile.name.lastIndexOf('.'));

        if (!validAudioTypes.some(type => selectedFile.type.includes(type)) && !validExtensions.includes(fileExtension)) {
          alert("Please upload a valid Audio file (MP3, WAV, M4A).");
          return;
        }
      }
      if (activeTab === 'text' && !selectedFile.type.startsWith('text/') && !selectedFile.name.endsWith('.txt')) {
        alert("Please upload a valid Text file (.txt).");
        return;
      }

      setIsUploading(true);
      setUploadError(null);

      try {
        const uploadFormData = new FormData();
        // Append user ID or handle in backend via token
        uploadFormData.append('file', selectedFile);

        let response;
        if (activeTab === 'video') {
          response = await mediaService.uploadVideo(uploadFormData);
        } else if (activeTab === 'audio') {
          response = await mediaService.uploadAudio(uploadFormData);
        } else if (activeTab === 'text') {
          response = await mediaService.uploadText(uploadFormData);
        }

        // Add to processing jobs
        const newJob = {
          id: response.id || 'temp-id',
          name: selectedFile.name,
          status: (response.status || 'queued').toLowerCase(),
          estTime: 'Processing...'
        };

        setProcessingJobs(prev => [newJob, ...prev]);
        setIsPolling(true);

        alert('Upload successful! Processing started.');
        setSelectedFile(null); // Clear selected file
        if (fileInputRef.current) fileInputRef.current.value = '';

      } catch (error) {
        console.error("Upload failed", error);
        setUploadError("Upload failed: " + (error.message || "Unknown error"));
        alert("Upload failed. Please try again.");
      } finally {
        setIsUploading(false);
      }
    } else if (activeTab === 'text' && formData.textInput) {
      // Handle direct text input (demo for now, or use a text upload endpoint with blob)
      alert('Direct text processing started! (Demo)');
    } else {
      // Fallback
      if (!selectedFile && activeTab !== 'text') {
        alert("Please select a file.");
      }
    }
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
              <h1>{t('dashboard.welcome')}{user ? `, ${user.first_name || user.username}!` : '!'}</h1>
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
              onClick={() => handleTabChange('video')}
            >
              {t('dashboard.tabVideo')}
            </button>
            <button
              className={`tab ${activeTab === 'audio' ? 'active' : ''}`}
              onClick={() => handleTabChange('audio')}
            >
              {t('dashboard.tabAudio')}
            </button>
            <button
              className={`tab ${activeTab === 'text' ? 'active' : ''}`}
              onClick={() => handleTabChange('text')}
            >
              {t('dashboard.tabText')}
            </button>
          </div>

          {/* Upload Area */}
          {(activeTab === 'video' || activeTab === 'audio' || activeTab === 'text') && (
            <div
              className={`upload-area ${isDragOver ? 'drag-over' : ''}`}
              onClick={handleFileSelect}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <div className="upload-icon">📁</div>
              <div className="upload-text">
                <h3>{selectedFile ? selectedFile.name : t('dashboard.uploadTitle')}</h3>
                <p>{selectedFile ? `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB` : t('dashboard.uploadSubtitle')}</p>
              </div>
              <div className="upload-formats">
                <span>{
                  activeTab === 'video' ? 'Supported: MP4, MOV, AVI' :
                    activeTab === 'audio' ? 'Supported: MP3, WAV' :
                      'Supported: TXT'
                }</span>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                hidden
                accept={
                  activeTab === 'video' ? 'video/*,.mp4,.mov,.avi,.mkv' :
                    activeTab === 'audio' ? '.mp3,.wav,.m4a,audio/mpeg,audio/wav,audio/mp4,audio/x-m4a' :
                      '.txt,text/plain'
                }
                onChange={handleFileChange}
              />
            </div>
          )}

          {/* Text Input - Only for text tab as option */}
          {(activeTab === 'text' && !selectedFile) && (
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
              <div className="option-group" style={{ marginTop: '24px' }}>
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
              <div className="option-group" style={{ marginTop: '24px' }}>
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
          <button
            className="btn btn-primary"
            onClick={handleStartProcessing}
            disabled={isUploading}
            style={{ opacity: isUploading ? 0.7 : 1, cursor: isUploading ? 'not-allowed' : 'pointer' }}
          >
            <span>{isUploading ? t('dashboard.processing') : t('dashboard.startProcessing')}</span>
            {!isUploading && (
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M6 4l8 6-8 6V4z" fill="currentColor" />
              </svg>
            )}
          </button>
        </div>

        {/* Current Processing Queue */}
        <div className="card progress-container">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h2 className="card-title" style={{ marginBottom: 0 }}>
              <span>⏳</span>
              <span>{t('dashboard.currentQueue')}</span>
            </h2>
            <button
              onClick={fetchJobs}
              className="btn btn-secondary"
              style={{ padding: '8px 16px', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <span>↻</span>
              <span>Refresh</span>
            </button>
          </div>

          {isLoading ? (
            <p style={{ textAlign: 'center', padding: '20px', color: 'var(--text-light)' }}>Loading...</p>
          ) : processingJobs.length > 0 ? (
            processingJobs.map((job) => (
              <div key={job.id} className="job-item">
                <div className="job-header">
                  <span className="job-name">{job.name}</span>
                  <span className="job-status">
                    {t('dashboard.processing')}
                  </span>
                </div>
                <div className="job-time">
                  <span>{t('dashboard.estTime')}</span> {job.estTime}
                </div>
              </div>
            ))
          ) : (
            <p style={{ color: 'var(--text-light)', textAlign: 'center', padding: '20px' }}>
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
            style={{ marginTop: '24px' }}
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

