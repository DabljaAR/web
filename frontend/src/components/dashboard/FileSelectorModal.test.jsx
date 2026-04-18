import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FileSelectorModal from './FileSelectorModal';
import { useTranslation } from '../../hooks/useTranslation';
import { mediaService } from '../../services/mediaService';

vi.mock('../../hooks/useTranslation');
vi.mock('../../services/mediaService');

describe('FileSelectorModal', () => {
  const mockT = vi.fn((k) => k);

  beforeEach(() => {
    vi.clearAllMocks();
    useTranslation.mockReturnValue({ t: mockT, language: 'en' });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not render when closed', () => {
    render(
      <FileSelectorModal
        isOpen={false}
        onClose={vi.fn()}
        onSelect={vi.fn()}
        activeTab="video"
      />
    );

    expect(screen.queryByText('dashboard.chooseExisting')).not.toBeInTheDocument();
  });

  it('fetches files on open and allows selecting a file', async () => {
    const onSelect = vi.fn();

    mediaService.getVideos.mockResolvedValue({
      items: [
        {
          id: '1',
          title: 'My video',
          original_filename: 'my.mp4',
          thumbnail_url: null,
          size_bytes: 10485760,
          created_at: '2025-01-01T00:00:00Z',
        },
      ],
    });

    render(
      <FileSelectorModal
        isOpen
        onClose={vi.fn()}
        onSelect={onSelect}
        activeTab="video"
      />
    );

    expect(screen.getByText('dashboard.chooseExisting')).toBeInTheDocument();

    await waitFor(() => {
      expect(mediaService.getVideos).toHaveBeenCalled();
    });

    expect(await screen.findByText('My video')).toBeInTheDocument();

    await userEvent.click(screen.getByText('My video'));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: '1' }));
  });

  it('shows empty state when no files are found', async () => {
    mediaService.getVideos.mockResolvedValue({ items: [] });

    render(
      <FileSelectorModal
        isOpen
        onClose={vi.fn()}
        onSelect={vi.fn()}
        activeTab="audio"
      />
    );

    expect(await screen.findByText('dashboard.noFilesFound')).toBeInTheDocument();
  });

  it('debounces search input and refetches', async () => {
    mediaService.getVideos.mockResolvedValue({ items: [] });

    render(
      <FileSelectorModal
        isOpen
        onClose={vi.fn()}
        onSelect={vi.fn()}
        activeTab="video"
      />
    );

    await waitFor(() => expect(mediaService.getVideos).toHaveBeenCalledTimes(1));

    const input = screen.getByPlaceholderText(/dashboard\.searchFilesPlaceholder/i);
    fireEvent.change(input, { target: { value: 'hello' } });

    // Should refetch after debounce window
    await waitFor(
      () => expect(mediaService.getVideos).toHaveBeenCalledTimes(2),
      { timeout: 1500 }
    );

    expect(mediaService.getVideos).toHaveBeenLastCalledWith(
      expect.objectContaining({ search: 'hello', mediaType: 'VIDEO', status: 'COMPLETED' })
    );
  });

  it('closes when clicking the backdrop (not the dialog)', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    mediaService.getVideos.mockResolvedValue({ items: [] });

    render(
      <FileSelectorModal
        isOpen
        onClose={onClose}
        onSelect={vi.fn()}
        activeTab="video"
      />
    );

    const backdrop = document.querySelector('.file-selector-backdrop');
    expect(backdrop).toBeTruthy();

    await user.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
