import { useTranslation } from '../../hooks/useTranslation';
import MemberCard from './MemberCard';
import { teamMembers } from '../../data/teamData';

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
