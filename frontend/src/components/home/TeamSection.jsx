import React from 'react';
import { useTranslation } from '../../hooks/useTranslation';

const TeamSection = () => {
  const { t } = useTranslation();

  const teamMembers = [
    { initials: 'AI', name: 'Abdallah Ibrahim Ismail' },
    { initials: 'MM', name: 'Moustafa Mohamed Magdy' },
    { initials: 'EA', name: 'Eslam Amr' },
    { initials: 'AH', name: 'Abdelrahman Hamdy Omran' },
    { initials: 'OS', name: 'Omar Mohamed Saied' },
    { initials: 'AB', name: 'Ali Bassam Almasri' },
  ];

  return (
    <section id="team" className="team-section">
      <div className="container">
        <h2 className="section-title">{t('team.title')}</h2>
        <div className="team-grid">
          {teamMembers.map((member, index) => (
            <div key={index} className="team-member">
              <div className="member-avatar">{member.initials}</div>
              <h3>{member.name}</h3>
            </div>
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

