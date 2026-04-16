import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import VideoTasksModal from './VideoTasksModal';
import taskService from '../../services/taskService';

vi.mock('../../services/taskService');

describe('VideoTasksModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not render when closed', () => {
    render(
      <VideoTasksModal
        isOpen={false}
        onClose={vi.fn()}
        videoId="v1"
        videoTitle="Title"
      />
    );

    expect(screen.queryByText(/Tasks/i)).not.toBeInTheDocument();
  });

  it('lists tasks and opens a completed task', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    taskService.getTasksForVideo.mockResolvedValue([
      {
        id: 't1',
        status: 'COMPLETED',
        output_type: 'captionsOnly',
        created_at: '2025-01-01T00:00:00Z',
        completed_at: '2025-01-01T01:00:00Z',
        source_lang: 'en',
        target_lang: 'ar-Arab',
      },
      {
        id: 't2',
        status: 'PROCESSING',
        output_type: 'fullDubbing',
        created_at: '2025-01-02T00:00:00Z',
        progress: 50,
        source_lang: 'en',
        target_lang: 'ar-Arab',
      },
    ]);

    taskService.getTask.mockResolvedValue({
      id: 't1',
      status: 'COMPLETED',
      output_type: 'captionsOnly',
      created_at: '2025-01-01T00:00:00Z',
      transcript: 'hello transcript',
      translated_transcript: null,
      target_lang: 'ar-Arab',
      segments: [{ start: 0, end: 1, text: 'hi' }],
      stt_metadata: { language: 'en' },
    });

    render(
      <VideoTasksModal
        isOpen
        onClose={onClose}
        videoId="v1"
        videoTitle="My Video"
      />
    );

    await waitFor(() => expect(taskService.getTasksForVideo).toHaveBeenCalledWith('v1'));

    const subtitle = await screen.findByText((_, el) => el?.classList?.contains('vtm-list-subtitle'));
    expect(subtitle).toHaveTextContent('My Video');
    expect(subtitle.textContent.toLowerCase()).toContain('task');

    // Completed task has an Open button
    await user.click(screen.getAllByRole('button', { name: /Open/i })[0]);

    await waitFor(() => expect(taskService.getTask).toHaveBeenCalledWith('t1'));

    expect(await screen.findByText(/Task Output/i)).toBeInTheDocument();
    expect(screen.getByText(/hello transcript/i)).toBeInTheDocument();

    // Back returns to list
    await user.click(screen.getByRole('button', { name: /Back/i }));
    expect(await screen.findByRole('heading', { name: /Tasks/i })).toBeInTheDocument();

    // Escape closes
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});
