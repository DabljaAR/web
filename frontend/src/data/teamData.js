/**
 * Team members data for the Home page
 * Shape matches MemberCard and MemberModalBase requirements:
 * { initials, name, role, gradient, accentColor, bio, highlights, skills, github?, linkedin?, cvUrl? }
 */

export const teamMembers =  [
  {
    id: 1,
    initials: 'AI',
    name: 'Abdallah Ibrahim',
    role: 'Software Engineer & Project Team Lead',
    gradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    accentColor: '#667eea',
    bio: 'Project team lead and software engineer driving the vision and coordination of the team. Oversees architecture decisions and ensures seamless collaboration across all workstreams.',
    highlights: [
      { icon: '🚀', label: 'Project Leadership' },
      { icon: '⚙️', label: 'System Architecture' },
      { icon: '🎯', label: 'Software Engineering' }
    ],
    skills: ['Python', 'FastAPI', 'PostgreSQL', 'Docker', 'AWS', 'LLMs', 'PyTorch', 'NLP'],
    github: 'https://github.com',
    linkedin: 'https://linkedin.com',
    cvUrl: null,
    avatarImage: '/team/abdallah.jpeg'
  },
  {
    id: 2,
    initials: 'MM',
    name: 'Moustafa Magdy',
    role: 'Software Engineer — Full Stack',
    gradient: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
    accentColor: '#f093fb',
    bio: 'Full-stack software engineer with a passion for building robust, scalable web applications. Bridges the gap between intuitive frontends and powerful backend systems.',
    highlights: [
      { icon: '✨', label: 'React & Modern JS' },
      { icon: '🎨', label: 'UI/UX Design' },
      { icon: '📱', label: 'Responsive Design' }
    ],
    skills: ['React', 'TypeScript', 'Tailwind', 'CSS', 'JavaScript', 'Node.js', 'REST APIs'],
    github: 'https://github.com',
    linkedin: 'https://linkedin.com',
    cvUrl: null,
    avatarImage: '/team/moustafa.jpeg'
  },
  {
    id: 3,
    initials: 'EA',
    name: 'Eslam Amr',
    role: 'Software Engineer — Full Stack',
    gradient: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    accentColor: '#4facfe',
    bio: 'Full-stack engineer focused on delivering clean, performant code across the entire stack. Passionate about developer experience and building features that users love.',
    highlights: [
      { icon: '🖥️', label: 'Full Stack Development' },
      { icon: '🔧', label: 'API Design' },
      { icon: '⚡', label: 'Performance Optimization' }
    ],
    skills: ['React', 'Node.js', 'PostgreSQL', 'Docker', 'TypeScript', 'GraphQL', 'CI/CD'],
    github: 'https://github.com',
    linkedin: 'https://linkedin.com',
    cvUrl: null,
    avatarImage: '/team/eslam.jpeg'
  },
  {
    id: 4,
    initials: 'OM',
    name: 'Omar Mohamed',
    role: 'AI Engineer',
    gradient: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
    accentColor: '#fa709a',
    bio: 'AI engineer specializing in developing and integrating intelligent models into real-world applications. Focuses on NLP, computer vision, and production-ready ML pipelines.',
    highlights: [
      { icon: '🤖', label: 'Machine Learning' },
      { icon: '🗣️', label: 'Speech Processing' },
      { icon: '🌐', label: 'NLP & Translation' }
    ],
    skills: ['Python', 'PyTorch', 'NLP', 'LLMs', 'Computer Vision', 'HuggingFace', 'TensorFlow'],
    github: 'https://github.com',
    linkedin: 'https://linkedin.com',
    cvUrl: null,
    avatarImage: '/team/omar.jpeg'
  },
  {
    id: 5,
    initials: 'AO',
    name: 'Abdalrahman Omran',
    role: 'AI Engineer',
    gradient: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
    accentColor: '#43e97b',
    bio: 'AI engineer with a strong foundation in deep learning and model fine-tuning. Works on building intelligent systems that push the boundaries of what automated video processing can achieve.',
    highlights: [
      { icon: '🧠', label: 'Deep Learning' },
      { icon: '🎬', label: 'Video AI' },
      { icon: '📊', label: 'Model Fine-tuning' }
    ],
    skills: ['Python', 'PyTorch', 'TensorFlow', 'LLMs', 'MLOps', 'HuggingFace', 'ONNX'],
    github: 'https://github.com',
    linkedin: 'https://linkedin.com',
    cvUrl: null,
    avatarImage: '/team/omran.jpeg'
  },
  {
    id: 6,
    initials: 'AB',
    name: 'Ali Bassam',
    role: 'AI Engineer',
    gradient: 'linear-gradient(135deg, #f7971e 0%, #ffd200 100%)',
    accentColor: '#f7971e',
    bio: 'AI engineer passionate about speech synthesis, neural machine translation, and the future of multilingual AI. Brings cutting-edge research into practical, deployable solutions.',
    highlights: [
      { icon: '🔬', label: 'AI Research' },
      { icon: '🌍', label: 'Multilingual NLP' },
      { icon: '🎙️', label: 'Speech Synthesis' }
    ],
    skills: ['Python', 'PyTorch', 'NLP', 'TTS', 'NMT', 'LLMs', 'Transformers'],
    github: 'https://github.com',
    linkedin: 'https://linkedin.com',
    cvUrl: null,
    avatarImage: '/team/ali.jpeg'
  }
];
