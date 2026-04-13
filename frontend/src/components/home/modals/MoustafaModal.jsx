import React from 'react';
import MemberModalBase from './MemberModalBase';

const DATA = {
  initials: 'MM',
  name: 'Moustafa Mohamed Magdy',
  role: 'ML Engineer',
  avatarImage: '/team/Moustafa.jpeg',
  gradient: 'linear-gradient(135deg, #0ea5e9 0%, #06b6d4 60%, #22d3ee 100%)',
  accentColor: '#0ea5e9',
  accentColor2: '#06b6d4',
  bio: 'Machine learning engineer specializing in NLP and computer vision. Experienced in building and deploying production-grade ML pipelines that turn raw data into intelligent, impactful products.',
  highlights: [
    { icon: '🤖', label: 'ML & AI' },
    { icon: '🔬', label: 'Research-Driven' },
    { icon: '📍', label: 'Egypt' },
  ],
  skills: ['Python', 'PyTorch', 'NLP', 'Computer Vision', 'FastAPI'],
  github: 'https://github.com',
  linkedin: 'https://linkedin.com',
  cvUrl: null,
};

const MoustafaModal = ({ onClose }) => <MemberModalBase data={DATA} onClose={onClose} />;

export default MoustafaModal;
