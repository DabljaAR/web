import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import DemoSection from './DemoSection';
import { useTranslation } from '../../hooks/useTranslation';
import toast from 'react-hot-toast';

vi.mock('../../hooks/useTranslation');
vi.mock('react-hot-toast', () => ({
  default: vi.fn(),
}));

describe('DemoSection', () => {
  const mockT = vi.fn((k) => k);

  beforeEach(() => {
    vi.clearAllMocks();
    useTranslation.mockReturnValue({ t: mockT });
  });

  it('renders translated headings', () => {
    render(<DemoSection />);

    expect(screen.getByText('demo.title')).toBeInTheDocument();
    expect(screen.getByText('demo.subtitle')).toBeInTheDocument();
  });

  it('calls toast when a file is selected through the input', () => {
    render(<DemoSection />);

    const input = document.querySelector('input[type="file"]');
    expect(input).toBeTruthy();

    const file = new File(['abc'], 'demo.mp4', { type: 'video/mp4' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(toast).toHaveBeenCalledWith(expect.stringContaining('demo.mp4'));
  });

  it('handles drag over and drop', () => {
    render(<DemoSection />);

    const uploadArea = screen.getByText('demo.uploadTitle').closest('.upload-area');
    expect(uploadArea).toBeTruthy();

    fireEvent.dragOver(uploadArea, { preventDefault: vi.fn() });
    expect(uploadArea).toHaveStyle({ borderColor: 'var(--accent-blue)' });

    const file = new File(['abc'], 'drop.mp4', { type: 'video/mp4' });
    fireEvent.drop(uploadArea, {
      preventDefault: vi.fn(),
      dataTransfer: { files: [file] },
    });

    expect(toast).toHaveBeenCalledWith(expect.stringContaining('drop.mp4'));
  });
});
