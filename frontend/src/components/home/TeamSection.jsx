import { useTranslation } from '../../hooks/useTranslation';
import MemberCard from './MemberCard';
import AbdallahModal from './modals/AbdallahModal';
import MoustafaModal from './modals/MoustafaModal';
import EslamModal from './modals/EslamModal';
import AbdelrahmanModal from './modals/AbdelrahmanModal';
import OmarModal from './modals/OmarModal';
import AliModal from './modals/AliModal';

const teamMembers = [
  {
    initials: 'AI',
    name: 'Abdallah Ibrahim Ismail',
    role: 'Backend Developer',
    avatarGradient: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
    modal: AbdallahModal,
  },
  {
    initials: 'MM',
    name: 'Moustafa Mohamed Magdy',
    role: 'ML Engineer',
    avatarGradient: 'linear-gradient(135deg, #0ea5e9, #06b6d4)',
    modal: MoustafaModal,
  },
  {
    initials: 'EA',
    name: 'Eslam Amr',
    role: 'Full Stack Developer',
    avatarGradient: 'linear-gradient(135deg, #10b981, #059669)',
    modal: EslamModal,
  },
  {
    initials: 'AH',
    name: 'Abdelrahman Hamdy Omran',
    role: 'Frontend Developer',
    avatarGradient: 'linear-gradient(135deg, #f59e0b, #ef4444)',
    modal: AbdelrahmanModal,
  },
  {
    initials: 'OS',
    name: 'Omar Mohamed Saied',
    role: 'AI Engineer',
    avatarGradient: 'linear-gradient(135deg, #ec4899, #f43f5e)',
    modal: OmarModal,
  },
  {
    initials: 'AB',
    name: 'Ali Bassam Almasri',
    role: 'DevOps Engineer',
    avatarGradient: 'linear-gradient(135deg, #14b8a6, #0891b2)',
    modal: AliModal,
  },
];

const TeamSection = () => {
  const { t } = useTranslation();

  return (
    <section id="team" className="team-section">
      <div className="container">
        <h2 className="section-title">{t('team.title')}</h2>
        <div className="team-grid">
          {teamMembers.map((member, index) => (
            <MemberCard key={index} member={member} />
          ))}
        </div>
        <div className="supervisors">
          <p><strong>{t('team.supervisor')}</strong> Dr. Sally Saad</p>
          <p><strong>{t('team.ta')}</strong> Mohamed Moussa</p>
        </div>
      </div>
    </section>
  );
};

export default TeamSection;
