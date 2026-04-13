import React from 'react';
import MemberModalBase from './MemberModalBase';

const DATA = {
  initials: 'EA',
  name: 'Eslam Amr',
  role: 'Full Stack Developer',
  gradient: 'linear-gradient(135deg, #10b981 0%, #059669 60%, #34d399 100%)',
  accentColor: '#10b981',
  accentColor2: '#059669',
  bio: 'Full stack developer with a passion for clean code and great user experiences. Builds end-to-end solutions — from polished React frontends to high-performance FastAPI backends — with a focus on speed and reliability.',
  highlights: [
    { icon: '💻', label: 'Full Stack' },
    { icon: '⚡', label: 'Performance First' },
    { icon: '📍', label: 'Egypt' },
  ],
  skills: ['React', 'FastAPI', 'Python', 'TypeScript', 'PostgreSQL', 'Docker'],
  github: 'https://github.com/Eslam-Amr',
  linkedin: 'https://linkedin.com',
  cvUrl: null,
};

const EslamModal = ({ onClose }) => <MemberModalBase data={DATA} onClose={onClose} />;

export default EslamModal;
