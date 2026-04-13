import React from 'react';
import MemberModalBase from './MemberModalBase';

const DATA = {
  initials: 'AI',
  name: 'Abdallah Ibrahim Ismail',
  role: 'Backend Developer',
  gradient: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 60%, #a78bfa 100%)',
  accentColor: '#6366f1',
  accentColor2: '#8b5cf6',
  bio: 'Passionate backend developer focused on building scalable, maintainable APIs and robust server-side architectures. Loves clean code, strong typing, and making complex systems simple.',
  highlights: [
    { icon: '🎓', label: 'CS Graduate' },
    { icon: '🔧', label: 'Backend Focus' },
    { icon: '📍', label: 'Egypt' },
  ],
  skills: ['Python', 'Django', 'REST APIs', 'PostgreSQL', 'Docker'],
  github: 'https://github.com',
  linkedin: 'https://linkedin.com',
  cvUrl: null,
};

const AbdallahModal = ({ onClose }) => <MemberModalBase data={DATA} onClose={onClose} />;

export default AbdallahModal;
