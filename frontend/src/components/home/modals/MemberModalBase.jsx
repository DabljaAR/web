import React, { useEffect } from 'react';
import PropTypes from 'prop-types';

const SKILL_STYLES = {
  // Frontend
  React:               { bg: '#dbeafe', color: '#1d4ed8' },
  JavaScript:          { bg: '#fef9c3', color: '#92400e' },
  TypeScript:          { bg: '#e0e7ff', color: '#3730a3' },
  CSS:                 { bg: '#e0f2fe', color: '#0369a1' },
  Tailwind:            { bg: '#cffafe', color: '#0e7490' },
  Figma:               { bg: '#fce7f3', color: '#9d174d' },
  HTML:                { bg: '#ffedd5', color: '#c2410c' },
  // Backend
  Python:              { bg: '#dcfce7', color: '#15803d' },
  Django:              { bg: '#d1fae5', color: '#065f46' },
  FastAPI:             { bg: '#d1fae5', color: '#065f46' },
  'REST APIs':         { bg: '#f0fdf4', color: '#166534' },
  // ML / AI
  PyTorch:             { bg: '#fee2e2', color: '#b91c1c' },
  NLP:                 { bg: '#ede9fe', color: '#5b21b6' },
  'Computer Vision':   { bg: '#ede9fe', color: '#5b21b6' },
  LLMs:                { bg: '#f3e8ff', color: '#6b21a8' },
  LangChain:           { bg: '#ede9fe', color: '#4c1d95' },
  RAG:                 { bg: '#f5f3ff', color: '#5b21b6' },
  'Vector DBs':        { bg: '#e0e7ff', color: '#3730a3' },
  // DevOps
  Docker:              { bg: '#dbeafe', color: '#1d4ed8' },
  Kubernetes:          { bg: '#dbeafe', color: '#1e40af' },
  'CI/CD':             { bg: '#ffedd5', color: '#c2410c' },
  AWS:                 { bg: '#fff7ed', color: '#9a3412' },
  Linux:               { bg: '#fef9c3', color: '#713f12' },
  GCP:                 { bg: '#dbeafe', color: '#1d4ed8' },
  // DB
  PostgreSQL:          { bg: '#dbeafe', color: '#1e40af' },
  MySQL:               { bg: '#fff7ed', color: '#9a3412' },
  MongoDB:             { bg: '#dcfce7', color: '#15803d' },
};
const DEFAULT_SKILL = { bg: '#f1f5f9', color: '#475569' };

const GithubIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
  </svg>
);

const LinkedinIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
  </svg>
);

const DownloadIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

/**
 * data shape:
 * {
 *   initials, name, role, gradient, accentColor,
 *   bio, highlights: [{icon, label}],
 *   skills: string[],
 *   github?, linkedin?, cvUrl?
 * }
 */
const MemberModalBase = ({ data, onClose }) => {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  return (
    <div className="fmodal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="fmodal">

        {/* ── Hero ── */}
        <div className="fmodal-hero" style={{ backgroundImage: data.gradient }}>
          <div className="fmodal-hero-blob fmodal-hero-blob--1" />
          <div className="fmodal-hero-blob fmodal-hero-blob--2" />
          <div className="fmodal-hero-blob fmodal-hero-blob--3" />

          <button className="fmodal-close" onClick={onClose} aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>

          <div className="fmodal-avatar">
            {data.avatarImage ? (
              <img
                className="fmodal-avatar-image"
                src={data.avatarImage}
                alt={data.name}
                loading="lazy"
              />
            ) : (
              data.initials
            )}
          </div>
          <h2 className="fmodal-name">{data.name}</h2>
          <span className="fmodal-role-pill">{data.role}</span>
        </div>

        {/* ── Highlights strip ── */}
        {data.highlights && data.highlights.length > 0 && (
          <div className="fmodal-highlights">
            {data.highlights.map((h, i) => (
              <div key={i} className="fmodal-highlight-item">
                <span className="fmodal-highlight-icon">{h.icon}</span>
                <span className="fmodal-highlight-label">{h.label}</span>
              </div>
            ))}
          </div>
        )}

        {/* ── Body ── */}
        <div className="fmodal-body">

          {/* About */}
          <div className="fmodal-section">
            <span className="fmodal-section-label">About Me</span>
            <p className="fmodal-about" style={{ borderLeftColor: data.accentColor }}>
              {data.bio}
            </p>
          </div>

          {/* Skills */}
          <div className="fmodal-section">
            <span className="fmodal-section-label">Skills & Tech</span>
            <div className="fmodal-skills">
              {data.skills.map((skill, i) => {
                const s = SKILL_STYLES[skill] || DEFAULT_SKILL;
                return (
                  <span key={i} className="fmodal-skill-tag" style={{ background: s.bg, color: s.color }}>
                    {skill}
                  </span>
                );
              })}
            </div>
          </div>

          {/* Connect */}
          {(data.github || data.linkedin) && (
            <div className="fmodal-section">
              <span className="fmodal-section-label">Connect</span>
              <div className="fmodal-socials">
                {data.github && (
                  <a href={data.github} target="_blank" rel="noopener noreferrer" className="fmodal-social fmodal-social--gh">
                    <GithubIcon /> GitHub
                  </a>
                )}
                {data.linkedin && (
                  <a href={data.linkedin} target="_blank" rel="noopener noreferrer" className="fmodal-social fmodal-social--li">
                    <LinkedinIcon /> LinkedIn
                  </a>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ── CV Footer ── */}
        <div className="fmodal-footer">
          {data.cvUrl ? (
            <a
              href={data.cvUrl}
              download
              className="fmodal-cv-btn"
              style={{
                backgroundImage: `linear-gradient(110deg, ${data.accentColor} 0%, ${data.accentColor2 || data.accentColor} 45%, #fff6 50%, ${data.accentColor2 || data.accentColor} 55%, ${data.accentColor} 100%)`,
                boxShadow: `0 8px 28px ${data.accentColor}55`,
              }}
            >
              <DownloadIcon /> Download CV
            </a>
          ) : (
            <span className="fmodal-cv-btn fmodal-cv-btn--disabled">
              <DownloadIcon /> CV Coming Soon
            </span>
          )}
        </div>

      </div>
    </div>
  );
};

MemberModalBase.propTypes = {
  data: PropTypes.shape({
    initials: PropTypes.string.isRequired,
    name: PropTypes.string.isRequired,
    role: PropTypes.string.isRequired,
    gradient: PropTypes.string,
    accentColor: PropTypes.string,
    accentColor2: PropTypes.string,
    bio: PropTypes.string.isRequired,
    avatarImage: PropTypes.string,
    highlights: PropTypes.arrayOf(PropTypes.shape({
      icon: PropTypes.string,
      label: PropTypes.string,
    })),
    skills: PropTypes.arrayOf(PropTypes.string).isRequired,
    github: PropTypes.string,
    linkedin: PropTypes.string,
    cvUrl: PropTypes.string,
  }).isRequired,
  onClose: PropTypes.func.isRequired,
};

export default MemberModalBase;
