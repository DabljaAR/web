import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import HeroSection from './HeroSection';
import { useTranslation } from '../../hooks/useTranslation';

vi.mock('../../hooks/useTranslation');

describe('HeroSection', () => {
  const mockT = vi.fn((k) => k);

  beforeEach(() => {
    vi.clearAllMocks();
    useTranslation.mockReturnValue({ t: mockT });
  });

  it('renders hero content', () => {
    render(<HeroSection />);

    expect(screen.getByText('hero.badge')).toBeInTheDocument();
    expect(screen.getByText('hero.description')).toBeInTheDocument();
    expect(screen.getByText('stats.videos')).toBeInTheDocument();
  });

  it('scrolls to sections when CTA links are clicked', async () => {
    const user = userEvent.setup();

    const demo = document.createElement('div');
    demo.id = 'demo';
    demo.scrollIntoView = vi.fn();
    document.body.appendChild(demo);

    const how = document.createElement('div');
    how.id = 'how-it-works';
    how.scrollIntoView = vi.fn();
    document.body.appendChild(how);

    render(<HeroSection />);

    await user.click(screen.getByRole('link', { name: /hero\.startFree/i }));
    expect(demo.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });

    await user.click(screen.getByRole('link', { name: /hero\.watchDemo/i }));
    expect(how.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });

    demo.remove();
    how.remove();
  });
});
