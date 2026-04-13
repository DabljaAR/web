import { useState } from 'react';

const MemberCard = ({ member }) => {
  const [open, setOpen] = useState(false);
  const Modal = member.modal;

  return (
    <>
      <div
        className="team-member team-member--clickable"
        onClick={() => setOpen(true)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setOpen(true); }}
      >
        <div className="member-avatar" style={{ background: member.avatarGradient }}>
          {member.avatarImage ? (
            <img
              className="member-avatar-image"
              src={member.avatarImage}
              alt={member.name}
              loading="lazy"
            />
          ) : (
            member.initials
          )}
        </div>
        <h3>{member.name}</h3>
        <p className="member-card-role">{member.role}</p>
        <span className="member-card-cta">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="16" />
            <line x1="8" y1="12" x2="16" y2="12" />
          </svg>
          View Portfolio
        </span>
      </div>

      {open && Modal && <Modal onClose={() => setOpen(false)} />}
    </>
  );
};

export default MemberCard;
