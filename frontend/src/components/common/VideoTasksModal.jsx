import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import taskService from '../../services/taskService';
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

/* ── Text preview (single tab OR side-by-side compare) ──────────────────── */
function TextPreview({ task, onBack }) {
  const captionsOnly      = task.output_type === 'captionsOnly';
  const hasTranslation    = !captionsOnly && Boolean(task.translated_transcript);
  const [view, setView]   = useState('original'); // 'original' | 'translation' | 'compare'
  const isRtl = (view === 'translation') && task.target_lang?.includes('Arab');

  useEffect(() => { setView('original'); }, [task.id]);

  return (
    <div className="vtm-preview">
      {/* back + meta */}
      <div className="vtm-preview-header">
        <button className="btn btn-secondary vtm-back-btn" onClick={onBack}>← Back</button>
        <span className="vtm-meta">
          {OUTPUT_TYPE_LABEL[task.output_type] || task.output_type}
          {' · '}{fmt(task.created_at)}
        </span>
      </div>

      {/* tab bar */}
      {hasTranslation ? (
        <div className="tabs vtm-tabs">
          <button className={`tab ${view === 'original'    ? 'active' : ''}`} onClick={() => setView('original')}>
            Original
          </button>
          <button className={`tab ${view === 'translation' ? 'active' : ''}`} onClick={() => setView('translation')}>
            Translation
          </button>
          <button className={`tab ${view === 'compare'     ? 'active' : ''}`} onClick={() => setView('compare')}>
            ⇔ Compare
          </button>
        </div>
      ) : null}

      {/* body */}
      {view === 'compare' ? (
        <div className="vtm-compare-grid">
          <div className="vtm-compare-panel">
            <div className="vtm-compare-label">Original Transcript</div>
            <div className="vtm-compare-text" dir="ltr">{task.transcript || <em className="vtm-empty">No text.</em>}</div>
          </div>
          <div className="vtm-compare-panel">
            <div className="vtm-compare-label">Translation</div>
            <div
              className="vtm-compare-text"
              dir={task.target_lang?.includes('Arab') ? 'rtl' : 'ltr'}
              style={{ textAlign: task.target_lang?.includes('Arab') ? 'right' : 'left' }}
            >
              {task.translated_transcript || <em className="vtm-empty">No text.</em>}
            </div>
          </div>
        </div>
      ) : (
        <div
          className="vtm-text-body"
          dir={isRtl ? 'rtl' : 'ltr'}
          style={{ textAlign: isRtl ? 'right' : 'left' }}
        >
          {(view === 'translation' ? task.translated_transcript : task.transcript)
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
  if (loading) return <div className="vtm-state-msg">Loading tasks…</div>;
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
            {/* badge + label */}
            <div className="vtm-task-top">
              <span className={`vtm-status-badge vtm-status-${statusKey}`}>
                {icons[statusKey]} {task.status}
              </span>
              <span className="vtm-output-type">
                {OUTPUT_TYPE_LABEL[task.output_type] || task.output_type}
              </span>
            </div>

            {/* date / meta */}
            <div className="vtm-task-date">
              {fmt(task.created_at)}
              {task.completed_at && <> · done {fmt(task.completed_at)}</>}
              <> · {task.source_lang || 'auto'} → {task.target_lang}</>
            </div>

            {/* progress bar */}
            {task.status === 'PROCESSING' && (
              <div className="vtm-progress-bar">
                <div className="vtm-progress-fill" style={{ width: `${task.progress ?? 0}%` }} />
              </div>
            )}

            {/* action buttons */}
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
            <div className="vtm-state-msg">Loading…</div>
          ) : selected ? (
            <TextPreview task={selected} onBack={() => setSelected(null)} />
          ) : (
            <TaskList videoTitle={videoTitle} tasks={tasks} loading={loading} onSelect={handleSelect} />
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
