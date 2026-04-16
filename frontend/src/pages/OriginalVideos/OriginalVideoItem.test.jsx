import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OriginalVideoItem from './OriginalVideoItem';

describe('OriginalVideoItem', () => {
  const t = (key) => key;

  it('uses safe displayName fallback and calls delete', async () => {
    const user = userEvent.setup();

    const onPreview = vi.fn();
    const onDownload = vi.fn();
    const onDelete = vi.fn();

    const item = {
      id: 'vid-1',
      name: undefined,
      title: undefined,
      original_filename: undefined,
      status: 'pending',
      date: undefined,
      mediaType: undefined,
    };

    render(
      <OriginalVideoItem
        item={item}
        t={t}
        onPreview={onPreview}
        onDownload={onDownload}
        onDelete={onDelete}
      />
    );

    // Fallback title
    expect(screen.getByText('history.untitled')).toBeInTheDocument();

    // No preview/download actions when not completed
    expect(screen.queryByText(/originalVideos\.preview/i)).not.toBeInTheDocument();

    // Delete
    await user.click(screen.getByRole('button', { name: /history\.delete/i }));
    expect(onDelete).toHaveBeenCalledWith('vid-1');
  });

  it('shows preview/download when completed and wires callbacks', async () => {
    const user = userEvent.setup();

    const onPreview = vi.fn();
    const onDownload = vi.fn();
    const onDelete = vi.fn();

    const item = {
      id: 'vid-2',
      name: 'file.mp4',
      status: 'completed',
      date: '2020-01-01T00:00:00.000Z',
      mediaType: undefined,
    };

    render(
      <OriginalVideoItem
        item={item}
        t={t}
        onPreview={onPreview}
        onDownload={onDownload}
        onDelete={onDelete}
      />
    );

    await user.click(screen.getByRole('button', { name: /originalVideos\.preview/i }));
    expect(onPreview).toHaveBeenCalledWith(item);

    await user.click(screen.getByRole('button', { name: /originalVideos\.download/i }));
    expect(onDownload).toHaveBeenCalledWith(item);
  });
});
