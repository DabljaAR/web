import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import FeaturesSection from './FeaturesSection';
import { useTranslation } from '../../hooks/useTranslation';

vi.mock('../../hooks/useTranslation');

describe('FeaturesSection', () => {
  const mockT = vi.fn((k) => k);

  beforeEach(() => {
    vi.clearAllMocks();
    useTranslation.mockReturnValue({ t: mockT });
  });

  it('renders title and feature cards', () => {
    render(<FeaturesSection />);

    expect(screen.getByText('features.title')).toBeInTheDocument();
    expect(screen.getByText('features.feature1Title')).toBeInTheDocument();
    expect(screen.getByText('features.feature6Title')).toBeInTheDocument();

    // Numbers are static
    expect(screen.getByText('01')).toBeInTheDocument();
    expect(screen.getByText('06')).toBeInTheDocument();
  });
});
