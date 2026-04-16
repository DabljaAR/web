import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MediaPreviewModal from './MediaPreviewModal';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';

vi.mock('../../hooks/useTranslation');
vi.mock('../../services/api', () => ({
  default: {
    getText: vi.fn(),
  },
}));

describe('MediaPreviewModal', () => {
  const mockT = vi.fn((k) => k);

  beforeEach(() => {
    vi.clearAllMocks();
    useTranslation.mockReturnValue({ t: mockT });
  });

  it('does not render when closed or without url', () => {
    render(<MediaPreviewModal isOpen={false} onClose={vi.fn()} url="http://x/y.mp4" />);
    expect(document.querySelector('.media-modal-backdrop')).toBeNull();

    render(<MediaPreviewModal isOpen onClose={vi.fn()} url={null} />);
    expect(document.querySelector('.media-modal-backdrop')).toBeNull();
  });

  it('renders a video preview and closes via button, backdrop, and Escape', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <MediaPreviewModal
        isOpen
        onClose={onClose}
        url="http://example.com/video.mp4"
        title="Preview"
      />
    );

    expect(document.querySelector('video')).toBeTruthy();

    await user.click(screen.getByTitle('Close'));
    expect(onClose).toHaveBeenCalledTimes(1);

    // Backdrop click
    const backdrop = document.querySelector('.media-modal-backdrop');
    await user.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(2);

    // Escape
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('loads and displays text previews (primary + secondary)', async () => {
    const onClose = vi.fn();

    api.getText.mockResolvedValue('hello');

    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue({ ok: true, text: async () => 'world' });

    render(
      <MediaPreviewModal
        isOpen
        onClose={onClose}
        url="/jobs/1/preview"
        type="TEXT"
        title="Text"
        secondaryUrl="https://example.com/translated.txt"
        primaryTitle="Original"
        secondaryTitle="Translated"
      />
    );

    expect(screen.getByText('Original')).toBeInTheDocument();
    expect(screen.getByText('Translated')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('hello')).toBeInTheDocument();
      expect(screen.getByText('world')).toBeInTheDocument();
    });

    fetchSpy.mockRestore();
  });
});
