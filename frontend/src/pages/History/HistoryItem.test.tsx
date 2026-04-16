import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import HistoryItem from './HistoryItem';

describe('HistoryItem', () => {
  const t = (key: string) => key;

  it('renders safe display name and date fallback and wires actions', async () => {
    const user = userEvent.setup();

    const onPreview = vi.fn();
    const onDownload = vi.fn();
    const onDelete = vi.fn();
    const onViewTasks = vi.fn();
    const onRedub = vi.fn();
    const onPreviewTranscript = vi.fn();
    const onPreviewTranslation = vi.fn();

    const item: any = {
      id: 'job-1',
      name: undefined, // forces fallback
      status: 'completed',
      date: null,
      mediaType: undefined,
      // Use URL flags to show transcript/translation actions
      transcriptUrl: 'https://example.com/t.txt',
      translationUrl: 'https://example.com/x.txt',
    };

    render(
      <HistoryItem
        item={item}
        t={t}
        onPreview={onPreview}
        onDownload={onDownload}
        onDelete={onDelete}
        onViewTasks={onViewTasks}
        onRedub={onRedub}
        onPreviewTranscript={onPreviewTranscript}
        onPreviewTranslation={onPreviewTranslation}
      />
    );

    // Title should use fallback from t()
    expect(screen.getByText('history.untitled')).toBeInTheDocument();

    // Date fallback should render (null date)
    expect(screen.getByText('history.noDate')).toBeInTheDocument();

    // Completed actions should be present
    await user.click(screen.getByRole('button', { name: /history\.tasks/i }));
    expect(onViewTasks).toHaveBeenCalledWith('job-1', 'history.untitled');

    await user.click(screen.getByRole('button', { name: /history\.preview/i }));
    expect(onPreview).toHaveBeenCalledWith(item);

    await user.click(screen.getByRole('button', { name: /history\.download/i }));
    expect(onDownload).toHaveBeenCalledWith(item);

    await user.click(screen.getByRole('button', { name: /history\.redub/i }));
    expect(onRedub).toHaveBeenCalledWith('job-1', 'history.untitled');

    // Transcript/Translation
    await user.click(screen.getByRole('button', { name: /history\.transcript/i }));
    expect(onPreviewTranscript).toHaveBeenCalledWith(item);

    await user.click(screen.getByRole('button', { name: /history\.translation/i }));
    expect(onPreviewTranslation).toHaveBeenCalledWith(item);

    // Delete icon button
    await user.click(screen.getByRole('button', { name: '🗑️' }));
    expect(onDelete).toHaveBeenCalledWith('job-1');
  });
});
