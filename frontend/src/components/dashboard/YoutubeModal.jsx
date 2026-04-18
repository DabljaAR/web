import React from 'react';

const YoutubeModal = ({
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
  handleYoutubeImportOnly,
  handleYoutubeSelection,
  t,
  tx
}) => {
  if (!showYoutubeModal) return null;

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center'
      }}
      onClick={(e) => { if (e.target === e.currentTarget) setShowYoutubeModal(false); }}
    >
      <div className="card" style={{ width: '100%', maxWidth: '520px', padding: '32px', position: 'relative' }}>
        <button
          onClick={() => { setShowYoutubeModal(false); setYoutubeError(null); setYoutubeUrl(''); }}
          style={{
            position: 'absolute', top: '16px', right: '16px',
            background: 'none', border: 'none', fontSize: '1.2rem',
            cursor: 'pointer', color: 'var(--text-light)'
          }}
        >✕</button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '24px' }}>
          <span style={{ fontSize: '1.5rem' }}>▶️</span>
          <h2 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700 }}>{t('originalVideos.youtubeModalTitle') || 'YouTube Import'}</h2>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-medium)' }}>
            {t('originalVideos.youtubeUrlLabel') || 'YouTube URL'}
          </label>
          <input
            type="url"
            className="form-select"
            style={{ width: '100%', height: '42px', padding: '0 12px', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', color: 'white' }}
            placeholder={t('originalVideos.youtubeUrlPlaceholder') || 'Paste YouTube link here'}
            value={youtubeUrl}
            onChange={(e) => { setYoutubeUrl(e.target.value); setYoutubeError(null); }}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-medium)' }}>
              {t('originalVideos.youtubeFormatLabel') || 'Format'}
            </label>
            <select
              className="form-select"
              value={youtubeFormat}
              onChange={(e) => setYoutubeFormat(e.target.value)}
              style={{ width: '100%' }}
            >
              <option value="video">🎬 {t('originalVideos.youtubeFormatVideo') || 'Video'}</option>
              <option value="audio">🎵 {t('originalVideos.youtubeFormatAudio') || 'Audio only'}</option>
            </select>
          </div>
          {youtubeFormat === 'video' && (
            <div>
              <label style={{ display: 'block', marginBottom: '6px', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-medium)' }}>
                {t('originalVideos.youtubeQualityLabel') || 'Quality'}
              </label>
              <select
                className="form-select"
                value={youtubeQuality}
                onChange={(e) => setYoutubeQuality(e.target.value)}
                style={{ width: '100%' }}
              >
                <option value="1080p">1080p</option>
                <option value="720p">720p</option>
                <option value="480p">480p</option>
                <option value="360p">360p</option>
              </select>
            </div>
          )}
        </div>

        {youtubeError && (
          <div style={{ marginBottom: '16px', color: '#ff4d4d', fontSize: '0.875rem' }}>
            {youtubeError}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: '12px' }}>
          <button
            className="btn btn-secondary"
            onClick={() => handleYoutubeImportOnly(youtubeUrl)}
            disabled={!youtubeUrl.trim() || isYoutubeDownloading}
            style={{ height: '48px', justifyContent: 'center' }}
          >
            {isYoutubeDownloading ? '...' : tx('dashboard.importOnly', 'Import Only')}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleYoutubeSelection}
            disabled={!youtubeUrl.trim() || isYoutubeDownloading}
            style={{ height: '48px', justifyContent: 'center' }}
          >
            {t('originalVideos.youtubeDownloadBtn') || 'Download & Import'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default YoutubeModal;
