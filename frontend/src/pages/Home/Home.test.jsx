import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/test-utils';
import Home from './Home';
import { useTranslation } from '../../hooks/useTranslation';

// Mock dependencies
vi.mock('../../hooks/useTranslation');
vi.mock('../../components/home/HeroSection', () => ({
  default: () => <div data-testid="hero-section">Hero</div>,
}));
vi.mock('../../components/home/ProblemSection', () => ({
  default: () => <div data-testid="problem-section">Problem</div>,
}));
vi.mock('../../components/home/FeaturesSection', () => ({
  default: () => <div data-testid="features-section">Features</div>,
}));
vi.mock('../../components/home/HowItWorksSection', () => ({
  default: () => <div data-testid="how-it-works-section">HowItWorks</div>,
}));
vi.mock('../../components/home/TryItNowSection', () => ({
  default: () => <div data-testid="try-it-now-section">TryItNow</div>,
}));
vi.mock('../../components/home/TeamSection', () => ({
  default: () => <div data-testid="team-section">Team</div>,
}));
vi.mock('../../components/layout/Navbar', () => ({
  default: () => <nav data-testid="navbar">Navbar</nav>,
}));
vi.mock('../../components/layout/Footer', () => ({
  default: () => <footer data-testid="footer">Footer</footer>,
}));

describe('Home Page', () => {
  const mockT = vi.fn((key) => key);

  beforeEach(() => {
    vi.clearAllMocks();
    useTranslation.mockReturnValue({ t: mockT });
  });

  it('renders all sections', () => {
    renderWithProviders(<Home />);

    expect(screen.getByTestId('hero-section')).toBeInTheDocument();
    expect(screen.getByTestId('problem-section')).toBeInTheDocument();
    expect(screen.getByTestId('how-it-works-section')).toBeInTheDocument();
    expect(screen.getByTestId('try-it-now-section')).toBeInTheDocument();
    expect(screen.getByTestId('team-section')).toBeInTheDocument();
  });

  it('renders navbar and footer', () => {
    renderWithProviders(<Home />);

    expect(screen.getByTestId('navbar')).toBeInTheDocument();
    expect(screen.getByTestId('footer')).toBeInTheDocument();
  });
});



