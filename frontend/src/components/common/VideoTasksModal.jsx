import { useState, useEffect, useRef } from 'react';
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

const fmtTime = (seconds) => {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  const s = Math.max(0, Number(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.floor((s - Math.floor(s)) * 1000);

  const hh = String(h).padStart(2, '0');
  const mm = String(m).padStart(2, '0');
  const ss = String(sec).padStart(2, '0');
  const mmm = String(ms).padStart(3, '0');

  // Keep it compact for UI: omit hours if not needed
  return h > 0 ? `${hh}:${mm}:${ss}.${mmm}` : `${mm}:${ss}.${mmm}`;
};

function toSrtTime(seconds) {
  const h  = Math.floor(seconds / 3600);
  const m  = Math.floor((seconds % 3600) / 60);
  const s  = Math.floor(seconds % 60);
  const ms = Math.round((seconds - Math.floor(seconds)) * 1000);
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')},${String(ms).padStart(3,'0')}`;
}

function downloadSrt(segments, filename, useTranslation = false) {
  const lines = [];
  let idx = 1;
  for (const seg of segments) {
    const text = useTranslation
      ? (seg.translated_text || seg.original_text)
      : seg.original_text;
    if (!text || seg.start == null || seg.end == null) continue;
    lines.push(`${idx++}\n${toSrtTime(seg.start)} --> ${toSrtTime(seg.end)}\n${text}\n`);
  }
  const blob = new Blob([lines.join('\n')], { type: 'application/x-subrip' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

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

/* ── Captioned video player ──────────────────────────────────────────────── */
function CaptionedVideoPlayer({ originalVideoUrl, dubbedVideoUrl, segments, hasTranslation, isArabicTarget }) {
  const hasDubbed = Boolean(dubbedVideoUrl);

  const videoRef     = useRef(null);
  const containerRef = useRef(null);
  const [activeSegment, setActiveSegment] = useState(null);
  const [captionMode, setCaptionMode]     = useState(hasTranslation ? 'translation' : 'original');
  const [videoSource, setVideoSource]     = useState(hasDubbed ? 'dubbed' : 'original');
  const [isFullscreen, setIsFullscreen]   = useState(false);
  const [panelOpen, setPanelOpen]         = useState(false);

  const activeUrl = videoSource === 'dubbed' && hasDubbed ? dubbedVideoUrl : originalVideoUrl;

  // ── caption sync ──────────────────────────────────────────────────────────
  const syncCaption = () => {
    const t = videoRef.current?.currentTime ?? 0;
    setActiveSegment((segments ?? []).find(s => t >= s.start && t < s.end) ?? null);
  };
  useEffect(() => {
    const id = setInterval(syncCaption, 100);
    return () => clearInterval(id);
  }, [segments]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { syncCaption(); }, [captionMode, segments]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── fullscreen ────────────────────────────────────────────────────────────
  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      containerRef.current?.requestFullscreen().catch(() => {});
    }
  };

  useEffect(() => {
    const onFsChange = () => {
      const fs = Boolean(document.fullscreenElement);
      setIsFullscreen(fs);
      if (!fs) setPanelOpen(false);
    };
    document.addEventListener('fullscreenchange', onFsChange);
    return () => document.removeEventListener('fullscreenchange', onFsChange);
  }, []);

  const captionText = activeSegment
    ? (captionMode === 'translation'
        ? (activeSegment.translated_text || activeSegment.original_text)
        : activeSegment.original_text)
    : null;
  const isRtl = captionMode === 'translation' && isArabicTarget;

  return (
    <div className="vtm-video-wrapper">
      <div className="vtm-video-area" ref={containerRef}>
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video
          key={activeUrl}
          ref={videoRef}
          className="vtm-video"
          controls
  controlsList="nofullscreen nodownload noremoteplayback"
          disablePictureInPicture
          onTimeUpdate={syncCaption}
          onSeeked={syncCaption}
          src={activeUrl}
        />

        {/* caption overlay */}
        {captionMode !== 'off' && captionText && (
          <div className="vtm-caption-overlay" dir={isRtl ? 'rtl' : 'ltr'}>
            <span className="vtm-caption-text">{captionText}</span>
          </div>
        )}

        {/* settings widget (top-right in normal, bottom-right in fullscreen) */}
        <div className={`vtm-fs-widget ${isFullscreen ? 'vtm-fs-widget--fs' : 'vtm-fs-widget--inline'}`}>
          {panelOpen && (
            <div className="vtm-fs-panel">
              <div className="vtm-fs-panel-section">
                <span className="vtm-fs-panel-label">Captions</span>
                <div className="vtm-fs-panel-btns">
                  <button className={`vtm-fs-option-btn ${captionMode === 'original' ? 'active' : ''}`} onClick={() => setCaptionMode('original')}>Original</button>
                  {hasTranslation && (
                    <button className={`vtm-fs-option-btn ${captionMode === 'translation' ? 'active' : ''}`} onClick={() => setCaptionMode('translation')}>Translation</button>
                  )}
                  <button className={`vtm-fs-option-btn ${captionMode === 'off' ? 'active' : ''}`} onClick={() => setCaptionMode('off')}>Off</button>
                </div>
              </div>
              {hasDubbed && (
                <div className="vtm-fs-panel-section">
                  <span className="vtm-fs-panel-label">Video</span>
                  <div className="vtm-fs-panel-btns">
                    <button className={`vtm-fs-option-btn ${videoSource === 'original' ? 'active' : ''}`} onClick={() => setVideoSource('original')}>Original</button>
                    <button className={`vtm-fs-option-btn ${videoSource === 'dubbed' ? 'active' : ''}`} onClick={() => setVideoSource('dubbed')}>Dubbed</button>
                  </div>
                </div>
              )}
            </div>
          )}
          <button
            className={`vtm-fs-settings-btn${panelOpen ? ' open' : ''}`}
            onClick={() => setPanelOpen((p) => !p)}
            title="Settings"
            aria-label="Settings"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
        </div>
      </div>

      {/* ── bottom bar ── */}
      <div className="vtm-caption-bar">
        <span className="vtm-caption-label">CC</span>
        <button className={`vtm-cc-btn ${captionMode === 'original' ? 'active' : ''}`} onClick={() => setCaptionMode('original')}>Original</button>
        {hasTranslation && (
          <button className={`vtm-cc-btn ${captionMode === 'translation' ? 'active' : ''}`} onClick={() => setCaptionMode('translation')}>Translation</button>
        )}
        <button className={`vtm-cc-btn ${captionMode === 'off' ? 'active' : ''}`} onClick={() => setCaptionMode('off')}>Off</button>

        {hasDubbed && (
          <>
            <span className="vtm-bar-divider" />
            <span className="vtm-caption-label">Video</span>
            <button className={`vtm-cc-btn ${videoSource === 'original' ? 'active' : ''}`} onClick={() => setVideoSource('original')}>Original</button>
            <button className={`vtm-cc-btn ${videoSource === 'dubbed' ? 'active' : ''}`} onClick={() => setVideoSource('dubbed')}>Dubbed</button>
          </>
        )}

        <span className="vtm-bar-divider" style={{ marginLeft: 'auto' }} />
        <button className="vtm-fs-toggle-btn" onClick={toggleFullscreen} title="Enter fullscreen">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/>
          </svg>
        </button>
      </div>
    </div>
  );
}

/* ── Task preview ─────────────────────────────────────────────────────────── */
function TaskPreview({ task, onBack }) {
  const captionsOnly   = task.output_type === 'captionsOnly';
  const hasTranslation = !captionsOnly && Boolean(task.translated_transcript);
  const originalVideoUrl = task.original_video_url || null;
  const dubbedVideoUrl   = task.dubbed_video_url   || null;
  const hasVideo         = Boolean(originalVideoUrl || dubbedVideoUrl) && Boolean(task.segments?.length);
  const hasTTS         = !hasVideo && Boolean(task.combined_audio_url || task.original_audio_url);
  const isArabicTarget = task.target_lang?.includes('Arab');

  const hasSegments = task.segments?.length > 0;
  const [tab, setTab] = useState('compare'); // 'original' | 'translation' | 'compare' | 'segments'

  useEffect(() => {
    setTab(hasTranslation ? 'compare' : hasSegments ? 'segments' : 'original');
  }, [task.id, hasTranslation, hasSegments]);

  return (
    <div className="vtm-preview">
      {/* ── header ── */}
      <div className="vtm-preview-header">
        <button className="btn btn-secondary vtm-back-btn" onClick={onBack}>← Back</button>
        <span className="vtm-meta">
          {OUTPUT_TYPE_LABEL[task.output_type] || task.output_type}
          {' · '}{fmt(task.created_at)}
        </span>
        {hasSegments && (
          <div className="vtm-srt-btns">
            <button
              className="btn btn-secondary vtm-srt-btn"
              title="Download original subtitles as SRT"
              onClick={() => downloadSrt(task.segments, `subtitles_original.srt`, false)}
            >
              ↓ SRT (original)
            </button>
            {hasTranslation && (
              <button
                className="btn btn-secondary vtm-srt-btn"
                title="Download translated subtitles as SRT"
                onClick={() => downloadSrt(task.segments, `subtitles_${task.target_lang}.srt`, true)}
              >
                ↓ SRT ({task.target_lang})
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── video player with caption overlay ── */}
      {hasVideo && (
        <CaptionedVideoPlayer
          originalVideoUrl={originalVideoUrl}
          dubbedVideoUrl={dubbedVideoUrl}
          segments={task.segments}
          hasTranslation={hasTranslation}
          isArabicTarget={isArabicTarget}
        />
      )}

      {/* ── audio comparison (fallback when no video) ── */}
      {hasTTS && (
        <div className="vtm-audio-row">
          <AudioPlayer src={task.original_audio_url} label="🎙 Original audio" />
          <AudioPlayer src={task.combined_audio_url} label="🔊 Translated audio" />
        </div>
      )}

      {/* ── text tabs ── */}
      {(hasTranslation || hasSegments) && (
        <div className="tabs vtm-tabs">
          {hasTranslation && (
            <>
              <button className={`tab ${tab === 'original'    ? 'active' : ''}`} onClick={() => setTab('original')}>
                Original
              </button>
              <button className={`tab ${tab === 'translation' ? 'active' : ''}`} onClick={() => setTab('translation')}>
                Translation
              </button>
              <button className={`tab ${tab === 'compare'     ? 'active' : ''}`} onClick={() => setTab('compare')}>
                ⇔ Compare
              </button>
            </>
          )}
          {hasSegments && (
            <button className={`tab ${tab === 'segments' ? 'active' : ''}`} onClick={() => setTab('segments')}>
              Segments
            </button>
          )}
        </div>
      )}

      {/* ── text body ── */}
      {tab === 'segments' ? (
        <div className="vtm-segments-list">
          {task.segments.map((seg, i) => (
            <div key={i} className="vtm-segment-row">
              <span className="vtm-segment-time">
                {fmtTime(seg.start)} → {fmtTime(seg.end)}
              </span>
              <div className="vtm-segment-texts">
                <span className="vtm-segment-original" dir="ltr">{seg.original_text}</span>
                {seg.translated_text && seg.translated_text !== seg.original_text && (
                  <span
                    className="vtm-segment-translation"
                    dir={isArabicTarget ? 'rtl' : 'ltr'}
                    style={{ textAlign: isArabicTarget ? 'right' : 'left' }}
                  >
                    {seg.translated_text}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : tab === 'compare' ? (
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

      {hasSegments && (
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
      if (import.meta.env.DEV) console.error(e);
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
          <h2 className="vtm-title">{selected ? 'Task Output' : 'Tasks'}</h2>
          <div className="vtm-header-controls">
            <button
              className={`vtm-ctrl-btn${maximized ? '' : ' vtm-disabled'}`}
              title="Minimize"
              aria-label="Minimize"
              disabled={!maximized}
              onClick={() => setMaximized(false)}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 18h12" />
              </svg>
            </button>

            <button
              className="vtm-ctrl-btn"
              title={maximized ? 'Restore' : 'Maximize'}
              aria-label={maximized ? 'Restore' : 'Maximize'}
              onClick={() => setMaximized((m) => !m)}
            >
              {maximized ? (
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M8 8h10v10H8z" />
                  <path d="M6 16H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v1" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M7 7h10v10H7z" />
                </svg>
              )}
            </button>

            <button className="vtm-ctrl-btn vtm-close" title="Close" aria-label="Close" onClick={onClose}>
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 6l12 12" />
                <path d="M18 6L6 18" />
              </svg>
            </button>
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
