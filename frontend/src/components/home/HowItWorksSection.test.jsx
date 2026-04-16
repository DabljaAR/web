import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import HowItWorksSection from './HowItWorksSection';
import { useTranslation } from '../../hooks/useTranslation';

vi.mock('../../hooks/useTranslation');

describe('HowItWorksSection', () => {
  const mockT = vi.fn((k) => k);

  beforeEach(() => {
    vi.clearAllMocks();
    useTranslation.mockReturnValue({ t: mockT });
  });

  it('renders workflow steps', () => {
    render(<HowItWorksSection />);

    expect(screen.getByText('howItWorks.title')).toBeInTheDocument();
    expect(screen.getByText('howItWorks.step1Title')).toBeInTheDocument();
    expect(screen.getByText('howItWorks.step5Title')).toBeInTheDocument();

    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });
});
