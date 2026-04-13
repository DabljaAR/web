import React from 'react';
import MemberModalBase from './MemberModalBase';

const DATA = {
  initials: 'AB',
  name: 'Ali Bassam Almasri',
  role: 'DevOps Engineer',
  avatarImage: '/team/ali.jpeg',
  gradient: 'linear-gradient(135deg, #14b8a6 0%, #0891b2 60%, #38bdf8 100%)',
  accentColor: '#14b8a6',
  accentColor2: '#0891b2',
  bio: 'DevOps engineer who keeps infrastructure running smoothly and teams shipping fast. Experienced in designing CI/CD pipelines, containerizing applications, and managing cloud infrastructure on AWS and GCP.',
  highlights: [
    { icon: '🚀', label: 'CI / CD' },
    { icon: '☁️', label: 'Cloud Infra' },
    { icon: '📍', label: 'Egypt' },
  ],
  skills: ['Docker', 'Kubernetes', 'CI/CD', 'AWS', 'Linux', 'Python'],
  github: 'https://github.com',
  linkedin: 'https://linkedin.com',
  cvUrl: null,
};

const AliModal = ({ onClose }) => <MemberModalBase data={DATA} onClose={onClose} />;

export default AliModal;
