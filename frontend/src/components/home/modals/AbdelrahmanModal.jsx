import React from 'react';
import MemberModalBase from './MemberModalBase';

const DATA = {
  initials: 'AH',
  name: 'Abdelrahman Hamdy Omran',
  role: 'Frontend Developer',
  avatarImage: '/team/Omran.jpeg',
  gradient: 'linear-gradient(135deg, #f59e0b 0%, #ef4444 60%, #f97316 100%)',
  accentColor: '#f59e0b',
  accentColor2: '#ef4444',
  bio: 'Frontend developer who crafts responsive, accessible, and visually engaging interfaces. Focused on building smooth user experiences with modern JavaScript frameworks and a strong eye for design details.',
  highlights: [
    { icon: '🎨', label: 'UI / UX' },
    { icon: '♿', label: 'Accessibility' },
    { icon: '📍', label: 'Egypt' },
  ],
  skills: ['React', 'JavaScript', 'TypeScript', 'CSS', 'Tailwind', 'Figma'],
  github: 'https://github.com',
  linkedin: 'https://linkedin.com',
  cvUrl: null,
};

const AbdelrahmanModal = ({ onClose }) => <MemberModalBase data={DATA} onClose={onClose} />;

export default AbdelrahmanModal;
