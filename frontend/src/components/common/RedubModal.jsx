import { useState } from 'react';
import { createPortal } from 'react-dom';
import './RedubModal.css';

const OUTPUT_TYPES = [
  {
    key: 'captionsOnly',
    icon: '📝',
    title: 'Captions Only',
    description: 'Transcribe the original audio and generate captions. No translation or voice synthesis.',
    tags: ['STT'],
  },
  {
    key: 'captionsAndTranslation',
    icon: '🌐',
    title: 'Captions + Translation',
    description: 'Transcribe and translate to Arabic. Produces both original and translated captions.',
    tags: ['STT', 'NMT'],
  },
  {
    key: 'translationAndTTS',
    icon: '🔊',
    title: 'Translation + Voice',
    description: 'Translate and synthesize Arabic speech. No background audio from the original video.',
    tags: ['STT', 'NMT', 'TTS'],
  },
  {
    key: 'fullDubbing',
    icon: '🎬',
    title: 'Full Dubbing',
    description: 'Complete dubbing: translated Arabic voice mixed with the original video sound effects.',
    tags: ['STT', 'NMT', 'TTS', 'SFX'],
  },
];

export default function RedubModal({ isOpen, onClose, videoId, videoTitle, onSubmit }) {
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    if (!selected) return;
    setLoading(true);
    setError(null);
    try {
      await onSubmit(videoId, selected);
      setSelected(null);
      onClose();
    } catch (e) {
      setError(e.message || 'Failed to start task.');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    if (loading) return;
    setSelected(null);
    setError(null);
    onClose();
  };

  return createPortal(
    <div className="rdm-backdrop" onClick={handleClose}>
      <div className="rdm-container" onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div className="rdm-header">
          <div className="rdm-header-left">
            <span className="rdm-icon">🔄</span>
            <div>
              <h2 className="rdm-title">Redub Video</h2>
              <p className="rdm-subtitle" title={videoTitle}>{videoTitle}</p>
            </div>
          </div>
          <button className="rdm-close" onClick={handleClose} disabled={loading}>✕</button>
        </div>

        {/* Body */}
        <div className="rdm-body">
          <p className="rdm-prompt">Choose what you want to generate:</p>

          <div className="rdm-grid">
            {OUTPUT_TYPES.map((opt) => (
              <button
                key={opt.key}
                className={`rdm-card ${selected === opt.key ? 'rdm-card-selected' : ''}`}
                onClick={() => setSelected(opt.key)}
                disabled={loading}
              >
                <div className="rdm-card-icon">{opt.icon}</div>
                <div className="rdm-card-title">{opt.title}</div>
                <div className="rdm-card-desc">{opt.description}</div>
                <div className="rdm-card-tags">
                  {opt.tags.map((tag) => (
                    <span key={tag} className="rdm-tag">{tag}</span>
                  ))}
                </div>
                {selected === opt.key && (
                  <div className="rdm-card-check">✓</div>
                )}
              </button>
            ))}
          </div>

          {error && <p className="rdm-error">{error}</p>}
        </div>

        {/* Footer */}
        <div className="rdm-footer">
          <button className="btn btn-secondary" onClick={handleClose} disabled={loading}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={!selected || loading}
          >
            {loading ? 'Starting…' : 'Start'}
          </button>
        </div>

      </div>
    </div>,
    document.body
  );
}
