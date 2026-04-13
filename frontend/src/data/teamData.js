/**
 * Team members data for the Home page
 * Shape matches MemberCard and MemberModalBase requirements:
 * { initials, name, role, gradient, accentColor, bio, highlights, skills, github?, linkedin?, cvUrl? }
 */

export const teamMembers = [
  {
    id: 1,
    initials: 'AA',
    name: 'Abdallah Aladdin',
    role: 'Lead Developer & Founder',
    gradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    accentColor: '#667eea',
    bio: 'Full-stack engineer passionate about AI, video processing, and building scalable solutions. Leads architecture and backend development.',
    highlights: [
      { icon: '🚀', label: 'AI & ML Integration' },
      { icon: '⚙️', label: 'System Architecture' },
      { icon: '🎯', label: 'Backend Development' }
    ],
    skills: ['Python', 'FastAPI', 'PostgreSQL', 'Docker', 'AWS', 'LLMs', 'PyTorch', 'NLP'],
    github: 'https://github.com',
    linkedin: 'https://linkedin.com',
    cvUrl: '/cv/abdallah.pdf',
    avatarImage: null
  },
  {
    id: 2,
    initials: 'FE',
    name: 'Frontend Engineer',
    role: 'UI/UX Developer',
    gradient: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
    accentColor: '#f093fb',
    bio: 'Creates beautiful, responsive user interfaces with React and modern web technologies. Focuses on user experience and performance.',
    highlights: [
      { icon: '✨', label: 'React & Modern JS' },
      { icon: '🎨', label: 'UI/UX Design' },
      { icon: '📱', label: 'Responsive Design' }
    ],
    skills: ['React', 'TypeScript', 'Tailwind', 'CSS', 'JavaScript', 'Vite', 'Vitest'],
    github: 'https://github.com',
    linkedin: 'https://linkedin.com',
    cvUrl: null,
    avatarImage: null
  },
  {
    id: 3,
    initials: 'DE',
    name: 'DevOps Engineer',
    role: 'Infrastructure & Deployment',
    gradient: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    accentColor: '#4facfe',
    bio: 'Manages deployment pipelines, infrastructure as code, and cloud operations. Ensures reliability and scalability.',
    highlights: [
      { icon: '🐳', label: 'Docker & Kubernetes' },
      { icon: '☁️', label: 'Cloud Infrastructure' },
      { icon: '🔧', label: 'CI/CD Pipelines' }
    ],
    skills: ['Docker', 'Kubernetes', 'GCP', 'Terraform', 'Linux', 'CI/CD', 'AWS'],
    github: 'https://github.com',
    linkedin: 'https://linkedin.com',
    cvUrl: null,
    avatarImage: null
  },
  {
    id: 4,
    initials: 'ML',
    name: 'ML Engineer',
    role: 'AI & Model Development',
    gradient: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
    accentColor: '#fa709a',
    bio: 'Develops and fine-tunes machine learning models for video processing, NMT, and speech synthesis tasks.',
    highlights: [
      { icon: '🤖', label: 'Machine Learning' },
      { icon: '🗣️', label: 'Speech Processing' },
      { icon: '🌐', label: 'NLP & Translation' }
    ],
    skills: ['Python', 'PyTorch', 'NLP', 'LLMs', 'Computer Vision', 'HuggingFace', 'TensorFlow'],
    github: 'https://github.com',
    linkedin: 'https://linkedin.com',
    cvUrl: null,
    avatarImage: null
  }
];
