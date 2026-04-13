import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import taskService from '../../services/taskService';
import LoadingSpinner from './LoadingSpinner';
import './VideoTasksModal.css';

const OUTPUT_TYPE_LABEL = {
  captionsOnly:           'Captions Only',
  captionsAndTranslation: 'Captions + Translation',
  translationAndTTS:      'Translation + TTS',
  fullDubbing:            'Full Dubbing',
};

const fmt = (iso) =>
  iso
    ? new Date(iso).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
    : '—';

/* ── Audio player ─────────────────────────────────────────────────────────── */
function AudioPlayer({ src, label }) {
  if (!src) return (
    <div className="vtm-audio-empty">
      <span className="vtm-audio-icon">🔇</span>
      <span>{label} — not available</span>
    </div>
  );
  return (
    <div className="vtm-audio-player">
      <div className="vtm-audio-label">{label}</div>
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio controls src={src} className="vtm-audio-element" />
    </div>
  );
}

/* ── Task preview ─────────────────────────────────────────────────────────── */
function TaskPreview({ task, onBack }) {
  const captionsOnly   = task.output_type === 'captionsOnly';
  const hasTranslation = !captionsOnly && Boolean(task.translated_transcript);
  const hasTTS         = Boolean(task.combined_audio_url || task.original_audio_url);
  const isArabicTarget = task.target_lang?.includes('Arab');

  const [tab, setTab] = useState('compare'); // 'original' | 'translation' | 'compare'

  useEffect(() => {
    setTab(hasTranslation ? 'compare' : 'original');
  }, [task.id, hasTranslation]);

  return (
    <div className="vtm-preview">
      {/* ── header ── */}
      <div className="vtm-preview-header">
        <button className="btn btn-secondary vtm-back-btn" onClick={onBack}>← Back</button>
        <span className="vtm-meta">
          {OUTPUT_TYPE_LABEL[task.output_type] || task.output_type}
          {' · '}{fmt(task.created_at)}
        </span>
      </div>

      {/* ── audio comparison ── */}
      {hasTTS && (
        <div className="vtm-audio-row">
          <AudioPlayer src={task.original_audio_url} label="🎙 Original audio" />
          <AudioPlayer src={task.combined_audio_url} label="🔊 Translated audio" />
        </div>
      )}

      {/* ── text tabs ── */}
      {hasTranslation && (
        <div className="tabs vtm-tabs">
          <button className={`tab ${tab === 'original'    ? 'active' : ''}`} onClick={() => setTab('original')}>
            Original
          </button>
          <button className={`tab ${tab === 'translation' ? 'active' : ''}`} onClick={() => setTab('translation')}>
            Translation
          </button>
          <button className={`tab ${tab === 'compare'     ? 'active' : ''}`} onClick={() => setTab('compare')}>
            ⇔ Compare
          </button>
        </div>
      )}

      {/* ── text body ── */}
      {tab === 'compare' ? (
        <div className="vtm-compare-grid">
          <div className="vtm-compare-panel">
            <div className="vtm-compare-label">Original Transcript</div>
            <div className="vtm-compare-text" dir="ltr">
              {task.transcript || <em className="vtm-empty">No text.</em>}
            </div>
          </div>
          <div className="vtm-compare-panel">
            <div className="vtm-compare-label">Translation</div>
            <div
              className="vtm-compare-text"
              dir={isArabicTarget ? 'rtl' : 'ltr'}
              style={{ textAlign: isArabicTarget ? 'right' : 'left' }}
            >
              {task.translated_transcript || <em className="vtm-empty">No text.</em>}
            </div>
          </div>
        </div>
      ) : (
        <div
          className="vtm-text-body"
          dir={(tab === 'translation' && isArabicTarget) ? 'rtl' : 'ltr'}
          style={{ textAlign: (tab === 'translation' && isArabicTarget) ? 'right' : 'left' }}
        >
          {(tab === 'translation' ? task.translated_transcript : task.transcript)
            || <span className="vtm-empty">No text available.</span>}
        </div>
      )}

      {task.segments?.length > 0 && (
        <div className="vtm-segments-meta">
          {task.segments.length} segments
          {task.stt_metadata?.language && <> · detected: <strong>{task.stt_metadata.language}</strong></>}
          {hasTranslation && <> → <strong>{task.target_lang}</strong></>}
        </div>
      )}
    </div>
  );
}

/* ── Task list ───────────────────────────────────────────────────────────── */
function TaskList({ videoTitle, tasks, onSelect, loading }) {
  if (loading) return <div className="vtm-state-msg"><LoadingSpinner size="small" /></div>;
  if (!tasks.length) return <div className="vtm-state-msg">No tasks found for this video.</div>;

  return (
    <div>
      <p className="vtm-list-subtitle">
        <strong>{tasks.length}</strong> task{tasks.length !== 1 ? 's' : ''} for{' '}
        <strong>{videoTitle}</strong>
      </p>

      {tasks.map((task) => {
        const statusKey = task.status.toLowerCase();
        const icons = { completed: '✓', processing: '⏳', failed: '✗', queued: '·' };
        const canOpen = task.status === 'COMPLETED';

        return (
          <div key={task.id} className="vtm-task-row">
            <div className="vtm-task-top">
              <span className={`vtm-status-badge vtm-status-${statusKey}`}>
                {icons[statusKey]} {task.status}
              </span>
              <span className="vtm-output-type">
                {OUTPUT_TYPE_LABEL[task.output_type] || task.output_type}
              </span>
            </div>

            <div className="vtm-task-date">
              {fmt(task.created_at)}
              {task.completed_at && <> · done {fmt(task.completed_at)}</>}
              <> · {task.source_lang || 'auto'} → {task.target_lang}</>
            </div>

            {task.status === 'PROCESSING' && (
              <div className="vtm-progress-bar">
                <div className="vtm-progress-fill" style={{ width: `${task.progress ?? 0}%` }} />
              </div>
            )}

            {canOpen && (
              <div className="vtm-task-actions">
                <button className="btn btn-secondary vtm-action-btn" onClick={() => onSelect(task.id)}>
                  Open
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Main modal ─────────────────────────────────────────────────────────── */
export default function VideoTasksModal({ isOpen, onClose, videoId, videoTitle }) {
  const [tasks,         setTasks]         = useState([]);
  const [loading,       setLoading]       = useState(false);
  const [selected,      setSelected]      = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [maximized,     setMaximized]     = useState(false);

  useEffect(() => {
    if (!isOpen || !videoId) return;
    setTasks([]);
    setSelected(null);
    setMaximized(false);
    setLoading(true);
    taskService.getTasksForVideo(videoId)
      .then(setTasks)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [isOpen, videoId]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  const handleSelect = async (taskId) => {
    setDetailLoading(true);
    try {
      setSelected(await taskService.getTask(taskId));
    } catch (e) {
      console.error(e);
    } finally {
      setDetailLoading(false);
    }
  };

  if (!isOpen) return null;

  return createPortal(
    <div className="vtm-backdrop" onClick={onClose}>
      <div
        className={`vtm-container${maximized ? ' vtm-maximized' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="vtm-header">
          <h2 className="vtm-title">{selected ? '📄 Task Output' : '📋 Tasks'}</h2>
          <div className="vtm-header-controls">
            <button className="vtm-ctrl-btn" title={maximized ? 'Restore' : 'Fullscreen'} onClick={() => setMaximized(m => !m)}>
              {maximized ? '⊡' : '⊞'}
            </button>
            <button className="vtm-ctrl-btn vtm-close" title="Close" onClick={onClose}>✕</button>
          </div>
        </div>

        <div className="vtm-body">
          {detailLoading ? (
            <div className="vtm-state-msg"><LoadingSpinner size="medium" /></div>
          ) : selected ? (
            <TaskPreview task={selected} onBack={() => setSelected(null)} />
          ) : (
            <TaskList videoTitle={videoTitle} tasks={tasks} loading={loading} onSelect={handleSelect} />
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
