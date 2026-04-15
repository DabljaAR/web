import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import Swal from 'sweetalert2';
import { useTranslation } from '../../hooks/useTranslation';
import { useAuth } from '../../hooks/useAuth';
import { useJobPolling } from '../../hooks/useJobPolling';
import { useYoutubeImport } from '../../hooks/useYoutubeImport';
import { mediaService } from '../../services/mediaService';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import MediaPreviewModal from '../../components/common/MediaPreviewModal';
import FileSelectorModal from '../../components/dashboard/FileSelectorModal';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import JobList from '../../components/dashboard/JobList';
import YoutubeModal from '../../components/dashboard/YoutubeModal';
import ProcessingQueue from '../../components/dashboard/ProcessingQueue';
import '../../styles/home.css';
import '../../styles/dashboard.css';
import '../../styles/dashboard-job-item.css';



const Dashboard = () => {
  const { t } = useTranslation();
  const tx = (key, fallback) => {
    const value = t(key);
    return value && value !== key ? value : fallback;
  };
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
    setSelectedFile(null);
    setSelectedLibraryFile(null); // Clear selected library file
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const [isDragOver, setIsDragOver] = useState(false);

  // Upload states
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  const [formData, setFormData] = useState({
    outputType: 'fullDubbing',
    domain: 'general',
    voice: 'male1',
    translationStyle: 'neutral',
    textInput: ''
  });
  const {
    processingJobs,
    setProcessingJobs,
    recentJobs,
    setRecentJobs,
    isPolling,
    setIsPolling,
    isLoading,
    deletingIds,
    fetchJobs
  } = useJobPolling();

  // Preview Modal State
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewJob, setPreviewJob] = useState(null);

  // Library Selection State
  const [isLibraryModalOpen, setIsLibraryModalOpen] = useState(false);
  const [selectedLibraryFile, setSelectedLibraryFile] = useState(null);

  // YouTube Selection State
  const {
    showYoutubeModal,
    setShowYoutubeModal,
    youtubeUrl,
    setYoutubeUrl,
    youtubeFormat,
    setYoutubeFormat,
    youtubeQuality,
    setYoutubeQuality,
    isYoutubeDownloading,
    youtubeError,
    setYoutubeError,
    selectedYoutubeInfo,
    setSelectedYoutubeInfo,
    handleYoutubeImportOnly,
    handleYoutubeSelection
  } = useYoutubeImport(fetchJobs, () => {
    setSelectedFile(null);
    setSelectedLibraryFile(null);
  });

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const getRequestOutputType = () => {
    if (activeTab === 'video') {
      return formData.outputType || 'fullDubbing';
    }
    return formData.outputType;
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
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
      setSelectedLibraryFile(null);
      setSelectedYoutubeInfo(null);
    }
  };



  // Upload a file to library only (no processing job)
  const handleUploadOnlyWithFile = async (file) => {
    if (!file) return;
    if (activeTab === 'video' && !file.type.startsWith('video/')) {
      toast.error("Please upload a valid Video file.");
      return;
    }
    if (activeTab === 'audio') {
      const validAudioTypes = ['audio/mpeg', 'audio/wav', 'audio/mp4', 'audio/x-m4a', 'audio/mp3'];
      const validExtensions = ['.mp3', '.wav', '.m4a'];
      const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
      if (!validAudioTypes.some(type => file.type.includes(type)) && !validExtensions.includes(fileExtension)) {
        toast.error("Please upload a valid Audio file (MP3, WAV, M4A).");
        return;
      }
    }

    setIsUploading(true);
    setUploadError(null);
    try {
      const uploadFormData = new FormData();
      uploadFormData.append('file', file);
      uploadFormData.append('output_type', 'uploadOnly');

      let response;
      if (activeTab === 'video') response = await mediaService.uploadVideo(uploadFormData);
      else if (activeTab === 'audio') response = await mediaService.uploadAudio(uploadFormData);
      else if (activeTab === 'text') response = await mediaService.uploadText(uploadFormData);

      const newJob = {
        id: response.id || 'temp-id',
        name: file.name,
        status: (response.status || 'completed').toLowerCase(),
        url: response.url,
        thumbnailUrl: response.thumbnail_url,
        audioUrl: response.audio_url,
        mediaType: activeTab.toUpperCase(),
        type: 'success'
      };

      setRecentJobs(prev => [newJob, ...prev]);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      toast.success('File uploaded successfully.');
    } catch (error) {
      const errMsg = error.message || 'Unknown error';
      setUploadError('Upload failed: ' + errMsg);
      toast.error('Upload failed: ' + errMsg);
    } finally {
      setIsUploading(false);
    }
  };

  // Upload a file and immediately start a dubbing job
  const handleStartProcessingWithFile = async (file) => {
    if (!file) return;
    if (activeTab === 'video' && !file.type.startsWith('video/')) {
      toast.error("Please upload a valid Video file.");
      return;
    }
    if (activeTab === 'audio') {
      const validAudioTypes = ['audio/mpeg', 'audio/wav', 'audio/mp4', 'audio/x-m4a', 'audio/mp3'];
      const validExtensions = ['.mp3', '.wav', '.m4a'];
      const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
      if (!validAudioTypes.some(type => file.type.includes(type)) && !validExtensions.includes(fileExtension)) {
        toast.error("Please upload a valid Audio file (MP3, WAV, M4A).");
        return;
      }
    }

    setIsUploading(true);
    setUploadError(null);
    try {
      const uploadFormData = new FormData();
      uploadFormData.append('file', file);
      uploadFormData.append('output_type', getRequestOutputType());
      uploadFormData.append('domain', formData.domain);
      uploadFormData.append('voice', formData.voice);
      uploadFormData.append('translation_style', formData.translationStyle);

      let response;
      if (activeTab === 'video') response = await mediaService.uploadVideo(uploadFormData);
      else if (activeTab === 'audio') response = await mediaService.uploadAudio(uploadFormData);
      else if (activeTab === 'text') response = await mediaService.uploadText(uploadFormData);

      const newJob = {
        id: response.id || 'temp-id',
        name: file.name,
        status: (response.status || 'queued').toLowerCase(),
        estTime: 'Processing...'
      };

      setProcessingJobs(prev => [newJob, ...prev]);
      setIsPolling(true);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      toast.success(t('dashboard.uploadSuccess') || 'Upload successful! Processing started.');
    } catch (error) {
      const errMsg = error.message || "Unknown error";
      setUploadError("Upload failed: " + errMsg);
      toast.error("Upload failed: " + errMsg);
    } finally {
      setIsUploading(false);
    }
  };

  // YouTube start processing
  const handleStartProcessingWithYoutube = async (ytInfo) => {
    setIsUploading(true);
    setUploadError(null);
    try {
      const response = await mediaService.downloadFromYoutube({
        youtube_url: (ytInfo.url || '').trim(),
        format: ytInfo.format,
        quality: ytInfo.quality,
        output_type: getRequestOutputType(),
        domain: formData.domain,
        voice: formData.voice,
        translation_style: formData.translationStyle
      });
      
      const newJob = {
        id: response.id || 'temp-yt-id',
        name: `Dubbing: YouTube Video`,
        status: 'queued',
        estTime: 'Processing...'
      };

      setProcessingJobs(prev => [newJob, ...prev]);
      setIsPolling(true);
      setSelectedYoutubeInfo(null);
      toast.success(t('dashboard.uploadSuccess') || 'YouTube import and dubbing started!');
    } catch (error) {
      const errMsg = error.message || "Unknown error";
      setUploadError("YouTube download failed: " + errMsg);
      toast.error("YouTube download failed: " + errMsg);
    } finally {
      setIsUploading(false);
    }
  };

  // "Start Dubbing" button handler
  const handleStartDubbingClick = async () => {
    // YouTube selected
    if (selectedYoutubeInfo) {
      await handleStartProcessingWithYoutube(selectedYoutubeInfo);
      return;
    }

    // New file selected: upload + start job
    if (selectedFile) {
      await handleStartProcessingWithFile(selectedFile);
      return;
    }

    // Text tab direct input
    if (activeTab === 'text' && formData.textInput && !selectedLibraryFile) {
      toast.success(t('dashboard.textDirectSuccess') || 'Direct text processing started! (Demo)');
      return;
    }

    // Library file: reprocess
    if (selectedLibraryFile) {
      setIsUploading(true);
      setUploadError(null);
      try {
        const payload = {
          output_type: getRequestOutputType(),
          domain: formData.domain,
          voice: formData.voice,
          translation_style: formData.translationStyle
        };
        const response = await mediaService.reprocessMedia(selectedLibraryFile.id, payload);
        const newJob = {
          id: response.id || selectedLibraryFile.id,
          name: selectedLibraryFile.title || selectedLibraryFile.original_filename,
          status: (response.status || 'queued').toLowerCase(),
          estTime: 'Processing...'
        };
        setProcessingJobs(prev => [newJob, ...prev]);
        setIsPolling(true);
        setSelectedLibraryFile(null);
        toast.success(t('dashboard.uploadSuccess') || 'Processing started.');
      } catch (error) {
        console.error("Reprocess failed", error);
        setUploadError("Failed to start processing: " + (error.message || "Unknown error"));
        toast.error(t('dashboard.uploadError') || "Failed to start processing. Please try again.");
      } finally {
        setIsUploading(false);
      }
      return;
    }

    // No file selected
    toast.error(t('dashboard.selectFileError') || "Please select or upload a file first.");
  };

  const handlePreview = (id) => {
    const job = recentJobs.find(j => j.id === id);
    if (job && job.url) {
      setPreviewJob(job);
      setPreviewModalOpen(true);
    } else {
      toast.error(t('dashboard.noPreviewError') || "No preview URL available.");
    }
  };

  const handleDownload = (id) => {
    const job = recentJobs.find(j => j.id === id);
    if (job && job.url) {
      const link = document.createElement('a');
      link.href = job.url;
      link.download = job.name || 'download';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else {
      toast.error(t('dashboard.noDownloadError') || "No download URL available.");
    }
  };

  const handlePreviewAudio = (id) => {
    const job = recentJobs.find(j => j.id === id);
    if (job && job.audioUrl) {
      // Create a specific object for audio preview from this job
      setPreviewJob({
        ...job,
        url: job.audioUrl,
        mediaType: 'AUDIO',
        name: `${job.name} (Audio)`
      });
      setPreviewModalOpen(true);
    } else {
      toast.error(t('dashboard.noAudioError') || "No audio URL available for this job.");
    }
  };

  const handleDownloadAudio = (id) => {
    const job = recentJobs.find(j => j.id === id);
    if (job && job.audioUrl) {
      const link = document.createElement('a');
      link.href = job.audioUrl;
      link.download = `${job.name}_audio.mp3`; // Assuming mp3
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else {
      toast.error(t('dashboard.noAudioError') || "No audio URL available.");
    }
  };
  const handlePreviewTranscript = (id) => {
    const job = recentJobs.find(j => j.id === id);
    if (job && job.transcriptUrl) {
      setPreviewJob({
        ...job,
        url: job.transcriptUrl,
        mediaType: 'TEXT',
        name: `${job.name} (Transcript)`
      });
      setPreviewModalOpen(true);
    }
  };

  const handlePreviewTranslation = (id) => {
    const job = recentJobs.find(j => j.id === id);
    if (job && job.translationUrl) {
      setPreviewJob({
        ...job,
        url: job.translationUrl,
        mediaType: 'TEXT',
        name: `${job.name} (Translation)`
      });
      setPreviewModalOpen(true);
    }
  };

  const handleDelete = async (id) => {
    const confirmResult = await Swal.fire({
      title: t('common.warning') || 'Are you sure?',
      text: t('dashboard.deleteConfirm') || "Are you sure you want to delete this job?",
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#d33',
      cancelButtonColor: '#3085d6',
      confirmButtonText: t('common.delete') || 'Yes, delete it!'
    });

    if (confirmResult.isConfirmed) {
      try {
        // Mark as deleting
        deletingIds.current.add(id);

        // Optimistically remove from UI
        setRecentJobs(prev => prev.filter(job => job.id !== id));
        setProcessingJobs(prev => prev.filter(job => job.id !== id));

        await mediaService.deleteVideo(id);
        toast.success(t('dashboard.deleteSuccess') || "Deleted successfully.");
      } catch (error) {
        console.error("Delete failed", error);

        toast.error(t('dashboard.deleteError') || "Failed to delete job.");

        // If failed, remove from deleting set so it can reappear/be retried
        deletingIds.current.delete(id);

        // Revert by fetching again
        fetchJobs();
      } finally {
        // We keep it in deletingIds if success, so next polls don't show it 
        // regardless of race conditions, until it's truly gone from backend.
        // Actually, if we successfully deleted, we don't need to remove it from the set immediately.
        // But eventually we should to avoid memory leaks if ids are reused (unlikely UUIDs).
        // Let's remove it after a delay just to be safe, or assume backend is consistent now.
        // Better: Remove from set only on error. On success, it's gone forever.
        // To be safe against memory leaks:
        setTimeout(() => {
          deletingIds.current.delete(id);
        }, 10000);
      }
    }
  };

  const handleRetry = (id) => {
    toast(`${t('dashboard.retryDemo')} ${id} (Demo)`);
  };

  const handleDetails = (id) => {
    toast(`${t('dashboard.detailsDemo')} ${id} (Demo)`);
  };

  const handleViewFullHistory = () => {
    navigate('/history');
  };

  const handleUpgradePremium = () => {
    toast(t('dashboard.upgradePremiumDemo') || 'Upgrade to Premium (Demo)');
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

          {/* Upload Area Split */}
          {(activeTab === 'video' || activeTab === 'audio' || activeTab === 'text') && !selectedFile && !selectedLibraryFile && !selectedYoutubeInfo && (
            <>
              <div className="upload-split-container triple">
                {/* Option 1: New Upload */}
                <div
                  className={`upload-area ${isDragOver ? 'drag-over' : ''}`}
                  onClick={handleFileSelect}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                  <div className="upload-icon">📤</div>
                  <div className="upload-text">
                    <h3>{t('dashboard.uploadTitle')}</h3>
                    <p>{t('dashboard.uploadSubtitle')}</p>
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
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        setSelectedFile(file);
                        setSelectedLibraryFile(null);
                        setSelectedYoutubeInfo(null);
                      }
                    }}
                  />
                </div>

                {/* Option 2: Choose Existing */}
                <div
                  className="choose-existing-area"
                  onClick={() => {
                    setSelectedFile(null);
                    setSelectedYoutubeInfo(null);
                    setIsLibraryModalOpen(true);
                  }}
                >
                  <div className="upload-icon">📚</div>
                  <div className="upload-text">
                    <h3>{t('dashboard.chooseExisting')}</h3>
                    <p>{t('dashboard.chooseExistingSubtitle')}</p>
                  </div>
                </div>

                {/* Option 3: YouTube */}
                <div
                  className="youtube-import-area"
                  onClick={() => {
                    setSelectedFile(null);
                    setSelectedLibraryFile(null);
                    setShowYoutubeModal(true);
                  }}
                >
                  <div className="upload-icon">▶️</div>
                  <div className="upload-text">
                    <h3>YouTube</h3>
                    <p>Import from YouTube URL</p>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Selected File Display (for both new upload, library, and youtube) */}
          {(selectedFile || selectedLibraryFile || selectedYoutubeInfo) && (
            <div className="selected-file-info">
              <div className="selected-file-details">
                <span style={{ fontSize: '1.5rem' }}>
                  {selectedYoutubeInfo ? '▶️' : (activeTab === 'video' ? '🎬' : activeTab === 'audio' ? '🎵' : '📄')}
                </span>
                <div>
                  <div className="selected-file-name">
                    {selectedFile ? selectedFile.name :
                      selectedLibraryFile ? (selectedLibraryFile.title || selectedLibraryFile.original_filename) :
                        selectedYoutubeInfo.url}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-light)' }}>
                    {selectedFile ? `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB` :
                      selectedLibraryFile ? t('dashboard.selectedFromLibrary') || 'Selected from library' :
                        'YouTube Video'}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  className="selected-file-clear"
                  onClick={() => {
                    setSelectedFile(null);
                    setSelectedLibraryFile(null);
                    setSelectedYoutubeInfo(null);
                    if (fileInputRef.current) fileInputRef.current.value = '';
                  }}
                  title="Change selection"
                >
                  ✕
                </button>
              </div>
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
                <div className="output-options-grid">
                  {/* Captions Only */}
                  <div
                    className={`output-option-card ${formData.outputType === 'captionsOnly' ? 'selected' : ''}`}
                    onClick={() => setFormData(prev => ({ ...prev, outputType: 'captionsOnly' }))}
                  >
                    <div className="output-option-icon">📄</div>
                    <div className="output-option-info">
                      <h4>{t('dashboard.captionsOnly')}</h4>
                      <p>{t('dashboard.captionsOnlyDesc') || "Fast transcription of any audio/video into text in the original language."}</p>
                    </div>
                  </div>

                  {/* Captions & Translation */}
                  <div
                    className={`output-option-card ${formData.outputType === 'captionsAndTranslation' ? 'selected' : ''}`}
                    onClick={() => setFormData(prev => ({ ...prev, outputType: 'captionsAndTranslation' }))}
                  >
                    <div className="output-option-icon">🌍</div>
                    <div className="output-option-info">
                      <h4>{t('dashboard.captionsAndTranslation')}</h4>
                      <p>{t('dashboard.captionsAndTranslationDesc') || "Translate transcribed content into high-quality Arabic text/subtitles."}</p>
                    </div>
                  </div>

                  {/* Translation & TTS */}
                  <div
                    className={`output-option-card ${formData.outputType === 'translationAndTTS' ? 'selected' : ''}`}
                    onClick={() => setFormData(prev => ({ ...prev, outputType: 'translationAndTTS' }))}
                  >
                    <div className="output-option-icon">🔊</div>
                    <div className="output-option-info">
                      <h4>{t('dashboard.translationAndTTS')}</h4>
                      <p>{t('dashboard.translationAndTTSDesc') || "Generate natural Arabic speech audio from the translated content."}</p>
                    </div>
                  </div>

                  {/* Full Dubbing */}
                  <div
                    className={`output-option-card ${formData.outputType === 'fullDubbing' ? 'selected' : ''}`}
                    onClick={() => setFormData(prev => ({ ...prev, outputType: 'fullDubbing' }))}
                  >
                    <div className="output-option-icon">🎬</div>
                    <div className="output-option-info">
                      <h4>{t('dashboard.fullDubbing')}</h4>
                      <p>{t('dashboard.fullDubbingDesc') || "A complete package: original video integrated with new Arabic audio and subtitles."}</p>
                    </div>
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

          {/* Start Dubbing Button */}
          {/* Combined Action Buttons */}
          <div style={{ display: 'flex', gap: '16px', marginTop: '32px' }}>
            {(selectedFile || selectedYoutubeInfo) && (
              <button
                className="btn btn-secondary"
                onClick={selectedFile ? () => handleUploadOnlyWithFile(selectedFile) : () => handleYoutubeImportOnly()}
                disabled={isUploading || isYoutubeDownloading}
                style={{ flex: 1, height: '56px', display: 'flex', justifyContent: 'center' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {isUploading || isYoutubeDownloading ? (
                    <>
                      <LoadingSpinner size="small" color="white" />
                      <span>{tx('common.uploading', 'Uploading...')}</span>
                    </>
                  ) : (
                    <span>{tx('dashboard.importOnly', 'Import Only')}</span>
                  )}
                </div>
              </button>
            )}

            <button
              className="btn btn-primary"
              onClick={handleStartDubbingClick}
              disabled={isUploading}
              style={{
                flex: (selectedFile || selectedYoutubeInfo) ? 2 : 1,
                opacity: isUploading ? 0.7 : 1,
                cursor: isUploading ? 'not-allowed' : 'pointer',
                height: '56px'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {isUploading ? (
                  <>
                    <LoadingSpinner size="small" color="white" />
                    <span>{tx('dashboard.processing', 'Processing...')}</span>
                  </>
                ) : (
                  <>
                    <span>{tx('dashboard.startDubbing', 'Start Dubbing')}</span>
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M6 4l8 6-8 6V4z" fill="currentColor" />
                    </svg>
                  </>
                )}
              </div>
            </button>
          </div>
        </div>

        {/* Current Processing Queue */}
        <ProcessingQueue 
          processingJobs={processingJobs}
          isLoading={isLoading}
          fetchJobs={fetchJobs}
          t={t}
        />

        {/* Recent Jobs */}
        <JobList 
          recentJobs={recentJobs}
          t={t}
          handlePreview={handlePreview}
          handleDownload={handleDownload}
          handleDelete={handleDelete}
          handleRetry={handleRetry}
          handleDetails={handleDetails}
          handlePreviewAudio={handlePreviewAudio}
          handleDownloadAudio={handleDownloadAudio}
          handlePreviewTranscript={handlePreviewTranscript}
          handlePreviewTranslation={handlePreviewTranslation}
          handleViewFullHistory={handleViewFullHistory}
        />
      </div>
      <Footer />

      {/* Media Preview Modal */}
      {
        previewJob && (
          <MediaPreviewModal
            isOpen={previewModalOpen}
            onClose={() => setPreviewModalOpen(false)}
            url={previewJob.url}
            type={previewJob.mediaType}
            title={previewJob.name}
          />
        )
      }

      {/* File Selector Modal */}
      <FileSelectorModal
        isOpen={isLibraryModalOpen}
        onClose={() => setIsLibraryModalOpen(false)}
        activeTab={activeTab}
        onSelect={(file) => {
          setSelectedLibraryFile(file);
          setSelectedFile(null);
          setSelectedYoutubeInfo(null);
          setIsLibraryModalOpen(false);
        }}
      />

      {/* YouTube Modal */}
      <YoutubeModal 
        showYoutubeModal={showYoutubeModal}
        setShowYoutubeModal={setShowYoutubeModal}
        youtubeUrl={youtubeUrl}
        setYoutubeUrl={setYoutubeUrl}
        youtubeFormat={youtubeFormat}
        setYoutubeFormat={setYoutubeFormat}
        youtubeQuality={youtubeQuality}
        setYoutubeQuality={setYoutubeQuality}
        isYoutubeDownloading={isYoutubeDownloading}
        youtubeError={youtubeError}
        setYoutubeError={setYoutubeError}
        handleYoutubeImportOnly={handleYoutubeImportOnly}
        handleYoutubeSelection={handleYoutubeSelection}
        t={t}
        tx={tx}
      />
    </div >
  );
};

export default Dashboard;
