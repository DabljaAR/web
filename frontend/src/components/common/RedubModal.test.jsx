import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RedubModal from './RedubModal';

describe('RedubModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not render when closed', () => {
    const onClose = vi.fn();
    render(
      <RedubModal
        isOpen={false}
        onClose={onClose}
        videoId="vid-1"
        videoTitle="My video"
        onSubmit={vi.fn()}
      />
    );

    expect(screen.queryByText(/Redub Video/i)).not.toBeInTheDocument();
  });

  it('lets user select an output type and submit', async () => {
    const user = userEvent.setup();

    const onClose = vi.fn();
    let resolveSubmit;
    const onSubmit = vi.fn(() => new Promise((r) => { resolveSubmit = r; }));

    render(
      <RedubModal
        isOpen
        onClose={onClose}
        videoId="vid-1"
        videoTitle="My video"
        onSubmit={onSubmit}
      />
    );

    expect(screen.getByText('My video')).toBeInTheDocument();

    const startBtn = screen.getByRole('button', { name: 'Start' });
    expect(startBtn).toBeDisabled();

    await user.click(screen.getByRole('button', { name: /Captions Only/i }));
    expect(startBtn).toBeEnabled();

    await user.click(startBtn);
    expect(onSubmit).toHaveBeenCalledWith('vid-1', 'captionsOnly');

    // While pending
    expect(screen.getByRole('button', { name: /Starting/i })).toBeDisabled();

    resolveSubmit();

    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  it('shows error when submit fails', async () => {
    const user = userEvent.setup();

    const onClose = vi.fn();
    const onSubmit = vi.fn(async () => {
      throw new Error('Boom');
    });

    render(
      <RedubModal
        isOpen
        onClose={onClose}
        videoId="vid-1"
        videoTitle="My video"
        onSubmit={onSubmit}
      />
    );

    await user.click(screen.getByRole('button', { name: /Full Dubbing/i }));
    await user.click(screen.getByRole('button', { name: 'Start' }));

    expect(await screen.findByText('Boom')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes on backdrop click when not loading', async () => {
    const user = userEvent.setup();

    const onClose = vi.fn();
    render(
      <RedubModal
        isOpen
        onClose={onClose}
        videoId="vid-1"
        videoTitle="My video"
        onSubmit={vi.fn()}
      />
    );

    const backdrop = document.querySelector('.rdm-backdrop');
    expect(backdrop).toBeTruthy();

    await user.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
