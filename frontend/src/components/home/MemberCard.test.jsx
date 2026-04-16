import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MemberCard from './MemberCard';

describe('MemberCard', () => {
  const member = {
    initials: 'AB',
    name: 'Alice Bob',
    role: 'Frontend',
    gradient: 'linear-gradient(45deg, red, blue)',
    accentColor: '#667eea',
    bio: 'Hello world',
    highlights: [{ icon: '⭐', label: 'Top' }],
    skills: ['React', 'JavaScript'],
    github: 'https://github.com/example',
    linkedin: 'https://linkedin.com/in/example',
    cvUrl: null,
  };

  it('opens the member modal on click and closes via close button', async () => {
    const user = userEvent.setup();
    render(<MemberCard member={member} />);

    const card = screen.getByRole('button');
    await user.click(card);

    expect(await screen.findByText('About Me')).toBeInTheDocument();
    expect(screen.getByText('Hello world')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('About Me')).not.toBeInTheDocument();
  });

  it('opens via keyboard and closes on Escape', () => {
    render(<MemberCard member={member} />);

    const card = screen.getByRole('button');
    fireEvent.keyDown(card, { key: 'Enter' });

    expect(screen.getByText('About Me')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('About Me')).not.toBeInTheDocument();
  });
});
