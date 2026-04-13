import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useTranslation } from '../../hooks/useTranslation';
import { useAuth } from '../../hooks/useAuth';
import { mediaService } from '../../services/mediaService';
import BackgroundDecorations from '../../components/home/BackgroundDecorations';
import Navbar from '../../components/layout/Navbar';
import Footer from '../../components/layout/Footer';
import MediaPreviewModal from '../../components/common/MediaPreviewModal';
import FileSelectorModal from '../../components/dashboard/FileSelectorModal';
import '../../styles/dashboard.css';
import '../../styles/dashboard-job-item.css'; // New styles

// Sub-component for Job Item to handle menu state locally
const JobItem = ({ job, t, onPreview, onDownload, onDelete, onRetry, onDetails, onPreviewAudio, onDownloadAudio, onPreviewTranscript, onPreviewTranslation }) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const toggleMenu = (e) => {
    e.stopPropagation();
    setMenuOpen(!menuOpen);
  };

  const isVideo = job.mediaType === 'VIDEO' || (!job.mediaType && job.name.match(/\.(mp4|mov|avi|mkv)$/i));
  const isAudio = job.mediaType === 'AUDIO' || (!job.mediaType && job.name.match(/\.(mp3|wav|m4a)$/i));
  const isText = job.mediaType === 'TEXT' || (!job.mediaType && job.name.match(/\.(txt)$/i));

  // Determine Icon/Thumbnail
  let thumbnailContent;
  if (job.thumbnailUrl) {
    thumbnailContent = <img src={job.thumbnailUrl} alt={job.name} className="job-thumbnail-img" onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }} />;
  }

  // Fallback icon
  const fallbackIcon = (
    <div className="job-type-icon">
      {isVideo ? '🎬' : isAudio ? '🎵' : '📄'}
    </div>
  );

  return (
    <div className="job-item-container">
      {/* Thumbnail / Icon */}
      <div className="job-thumbnail-wrapper" onClick={() => onPreview(job.id)}>
        {thumbnailContent}
        {!job.thumbnailUrl && fallbackIcon}

        {/* Play Overlay for previewable content */}
        {(isVideo || isAudio) && job.status === 'completed' && (
          <div className="thumbnail-overlay">
            <span className="play-icon-overlay">▶</span>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="job-info-content">
        <div className="job-title" title={job.name}>{job.name}</div>
        <div className="job-meta">
          <span className={`status-badge ${job.status}`}>
            {t(`dashboard.${job.status}`) || job.status}
          </span>
          {/* Add date or size here if available later */}
        </div>
      </div>

      {/* Actions */}
      <div className="job-actions-container" ref={menuRef}>
        <button className="btn-icon-menu" onClick={toggleMenu} title="Options">
          {/* Kebab Icon (Vertical Dots) */}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="1"></circle>
            <circle cx="12" cy="5" r="1"></circle>
            <circle cx="12" cy="19" r="1"></circle>
          </svg>
        </button>

        {menuOpen && (
          <div className="action-menu-dropdown">
            {job.status === 'completed' ? (
              <>
                <button className="action-menu-item" onClick={() => { onPreview(job.id); setMenuOpen(false); }}>
                  <span>👁️</span> {t('dashboard.preview')}
                </button>
                <button className="action-menu-item" onClick={() => { onDownload(job.id); setMenuOpen(false); }}>
                  <span>⬇️</span> {t('dashboard.download')}
                </button>
                {/* Audio Option */}
                {job.audioUrl && (
                  <>
                    <button className="action-menu-item" onClick={() => { onPreviewAudio(job.id); setMenuOpen(false); }}>
                      <span>🎵</span> {t('dashboard.previewAudio') || 'Preview Audio'}
                    </button>
                    <button className="action-menu-item" onClick={() => { onDownloadAudio(job.id); setMenuOpen(false); }}>
                      <span>⬇️</span> {t('dashboard.downloadAudio') || 'Download Audio'}
                    </button>
                  </>
                )}
                {/* Transcript Option */}
                {job.transcriptUrl && (
                  <button className="action-menu-item" onClick={() => { onPreviewTranscript(job.id); setMenuOpen(false); }}>
                    <span>📄</span> {t('dashboard.previewTranscript') || 'Preview Transcript'}
                  </button>
                )}
                {/* Translation Option */}
                {job.translationUrl && (
                  <button className="action-menu-item" onClick={() => { onPreviewTranslation(job.id); setMenuOpen(false); }}>
                    <span>🌍</span> {t('dashboard.previewTranslation') || 'Preview Translation'}
                  </button>
                )}
              </>
            ) : (
              <>
                <button className="action-menu-item" onClick={() => { onRetry(job.id); setMenuOpen(false); }}>
                  <span>🔄</span> {t('dashboard.retry')}
                </button>
                <button className="action-menu-item" onClick={() => { onDetails(job.id); setMenuOpen(false); }}>
                  <span>ℹ️</span> {t('dashboard.details')}
                </button>
              </>
            )}
            <div style={{ height: '1px', background: '#eee', margin: '4px 0' }}></div>
            <button className="action-menu-item danger" onClick={() => { onDelete(job.id); setMenuOpen(false); }}>
              <span>🗑️</span> {t('dashboard.delete')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

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
  const [processingJobs, setProcessingJobs] = useState([]);
  const [recentJobs, setRecentJobs] = useState([]);
  const [isPolling, setIsPolling] = useState(true);
  const [isLoading, setIsLoading] = useState(true);

  // Preview Modal State
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewJob, setPreviewJob] = useState(null);

  // Library Selection State
  const [isLibraryModalOpen, setIsLibraryModalOpen] = useState(false);
  const [selectedLibraryFile, setSelectedLibraryFile] = useState(null);

  // Track deleting items to prevent flickering during polling
  const deletingIds = useRef(new Set());

  // Fetch jobs
  const fetchJobs = async () => {
    try {
      const data = await mediaService.getDashboardData();

      const active = data.active || [];
      const recent = data.recent || [];

      const pending = active.map(v => ({
        id: v.id,
        name: v.name,
        status: v.status.toLowerCase(),
        type: v.type,
        progress: v.progress,
        estTime: v.progress > 0 ? `${v.progress.toFixed(0)}%` : 'Processing...'
      }));

      const completed = recent.map(v => {
        // Find transcript and translation URLs from the jobs array
        const transcriptUrl = v.jobs?.find(j => j.transcript_url)?.transcript_url;
        const translationUrl = v.jobs?.find(j => j.translation_url)?.translation_url;

        return {
          id: v.id,
          name: v.title || v.original_filename,
          status: v.status.toLowerCase(),
          url: v.url,
          thumbnailUrl: v.thumbnail_url,
          audioUrl: v.audio_url,
          transcriptUrl: transcriptUrl,
          translationUrl: translationUrl,
          mediaType: v.media_type,
          type: v.status === 'COMPLETED' ? 'success' : 'failed'
        };
      });

      // Filter out items that are currently marked for deletion
      const safePending = pending.filter(job => !deletingIds.current.has(job.id));
      const safeCompleted = completed.filter(job => !deletingIds.current.has(job.id));

      setProcessingJobs(safePending);
      setRecentJobs(safeCompleted);

      // Poll only if there are pending jobs
      setIsPolling(pending.length > 0);

    } catch (error) {
      console.error("Error fetching jobs:", error);
      setIsPolling(false);
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
    if (activeTab === 'text' && !formData.textInput && !selectedFile && !selectedLibraryFile) {
      // Correct check logic for text tab
      if (!selectedFile && !selectedLibraryFile && !formData.textInput) {
        toast.error(t('dashboard.textPlaceholder'));
        return;
      }
    }

    if ((activeTab === 'video' || activeTab === 'audio') && !selectedFile && !selectedLibraryFile) {
      toast.error(t('dashboard.selectFileError') || "Please select or upload a file first.");
      return;
    }

    // library selection
    if (selectedLibraryFile) {
      setIsUploading(true);
      setUploadError(null);

      try {
        const payload = {
          output_type: formData.outputType,
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

    // If it's a file upload
    if (selectedFile) {
      // Validate file type
      if (activeTab === 'video' && !selectedFile.type.startsWith('video/')) {
        toast.error("Please upload a valid Video file.");
        return;
      }
      if (activeTab === 'audio') {
        const validAudioTypes = ['audio/mpeg', 'audio/wav', 'audio/mp4', 'audio/x-m4a', 'audio/mp3'];
        const validExtensions = ['.mp3', '.wav', '.m4a'];
        const fileExtension = selectedFile.name.toLowerCase().substring(selectedFile.name.lastIndexOf('.'));

        if (!validAudioTypes.some(type => selectedFile.type.includes(type)) && !validExtensions.includes(fileExtension)) {
          toast.error("Please upload a valid Audio file (MP3, WAV, M4A).");
          return;
        }
      }
      if (activeTab === 'text' && !selectedFile.type.startsWith('text/') && !selectedFile.name.endsWith('.txt')) {
        toast.error("Please upload a valid Text file (.txt).");
        return;
      }

      setIsUploading(true);
      setUploadError(null);

      try {
        const uploadFormData = new FormData();
        // Append user ID or handle in backend via token
        uploadFormData.append('file', selectedFile);

        // Append processing options
        uploadFormData.append('output_type', formData.outputType);
        uploadFormData.append('domain', formData.domain);
        uploadFormData.append('voice', formData.voice);
        uploadFormData.append('translation_style', formData.translationStyle);

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

        toast.success(t('dashboard.uploadSuccess') || 'Upload successful! Processing started.');
        setSelectedFile(null); // Clear selected file
        if (fileInputRef.current) fileInputRef.current.value = '';

      } catch (error) {
        console.error("Upload failed", error);
        const errMsg = error.message || "Unknown error";
        setUploadError("Upload failed: " + errMsg);
        toast.error("Upload failed: " + errMsg);
      } finally {
        setIsUploading(false);
      }
    } else if (activeTab === 'text' && formData.textInput) {
      // Handle direct text input (demo for now, or use a text upload endpoint with blob)
      toast.success(t('dashboard.textDirectSuccess') || 'Direct text processing started! (Demo)');
    } else {
      // Fallback
      if (!selectedFile && activeTab !== 'text') {
        toast.error(t('dashboard.selectFileError') || "Please select a file.");
      }
    }
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
    if (window.confirm(t('dashboard.deleteConfirm') || "Are you sure you want to delete this job?")) {
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
          {(activeTab === 'video' || activeTab === 'audio' || activeTab === 'text') && !selectedFile && !selectedLibraryFile && (
            <>
              <div className="upload-split-container">
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
                    onChange={handleFileChange}
                  />
                </div>

                {/* Option 2: Choose Existing */}
                <div
                  className="choose-existing-area"
                  onClick={() => setIsLibraryModalOpen(true)}
                >
                  <div className="upload-icon">📚</div>
                  <div className="upload-text">
                    <h3>{t('dashboard.chooseExisting')}</h3>
                    <p>{t('dashboard.chooseExistingSubtitle')}</p>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'center', marginTop: '12px' }}>
                <button className="btn btn-secondary" onClick={handleFileSelect}>
                  {activeTab === 'video' ? '⬆️ Upload Video' : activeTab === 'audio' ? '⬆️ Upload Audio' : '⬆️ Upload Text'}
                </button>
              </div>
            </>
          )}

          {/* Selected File Display (For both Upload and Library) */}
          {(selectedFile || selectedLibraryFile) && (
            <div className="selected-file-info">
              <div className="selected-file-details">
                <span style={{ fontSize: '1.5rem' }}>
                  {activeTab === 'video' ? '🎬' : activeTab === 'audio' ? '🎵' : '📄'}
                </span>
                <div>
                  <div className="selected-file-name">
                    {selectedFile ? selectedFile.name : (selectedLibraryFile.title || selectedLibraryFile.original_filename)}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-light)' }}>
                    {selectedFile ? `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB` : t('dashboard.selectedFile')}
                  </div>
                </div>
              </div>
              <button
                className="selected-file-clear"
                onClick={() => {
                  setSelectedFile(null);
                  setSelectedLibraryFile(null);
                  if (fileInputRef.current) fileInputRef.current.value = '';
                }}
                title="Change selection"
              >
                ✕
              </button>
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

          {/* Start Button */}
          <button
            className="btn btn-primary"
            onClick={handleStartProcessing}
            disabled={isUploading}
            style={{ opacity: isUploading ? 0.7 : 1, cursor: isUploading ? 'not-allowed' : 'pointer' }}
          >
            <span>{isUploading ? (t('dashboard.processing') || 'Processing...') : t('dashboard.startProcessing')}</span>
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
              <span>{t('dashboard.refresh')}</span>
            </button>
          </div>

          {isLoading ? (
            <p style={{ textAlign: 'center', padding: '20px', color: 'var(--text-light)' }}>{t('common.loading') || 'Loading...'}</p>
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
              <JobItem
                key={job.id}
                job={job}
                t={t}
                onPreview={handlePreview}
                onDownload={handleDownload}
                onDelete={handleDelete}
                onRetry={handleRetry}
                onDetails={handleDetails}
                onPreviewAudio={handlePreviewAudio}
                onDownloadAudio={handleDownloadAudio}
                onPreviewTranscript={handlePreviewTranscript}
                onPreviewTranslation={handlePreviewTranslation}
              />
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
          setSelectedFile(null); // Clear manual upload selection
          setIsLibraryModalOpen(false);
        }}
      />
    </div >
  );
};

export default Dashboard;

