import React from 'react';
import MemberModalBase from './MemberModalBase';

const DATA = {
  initials: 'OS',
  name: 'Omar Mohamed Saied',
  role: 'AI Engineer',
  gradient: 'linear-gradient(135deg, #ec4899 0%, #f43f5e 60%, #fb7185 100%)',
  accentColor: '#ec4899',
  accentColor2: '#f43f5e',
  bio: 'AI engineer focused on integrating large language models into real-world products. Experienced in prompt engineering, RAG pipelines, and AI evaluation frameworks that make intelligent systems production-ready.',
  highlights: [
    { icon: '🧠', label: 'AI / LLMs' },
    { icon: '🔗', label: 'RAG Pipelines' },
    { icon: '📍', label: 'Egypt' },
  ],
  skills: ['Python', 'LLMs', 'LangChain', 'RAG', 'Vector DBs', 'FastAPI'],
  github: 'https://github.com',
  linkedin: 'https://linkedin.com',
  cvUrl: null,
};

const OmarModal = ({ onClose }) => <MemberModalBase data={DATA} onClose={onClose} />;

export default OmarModal;
