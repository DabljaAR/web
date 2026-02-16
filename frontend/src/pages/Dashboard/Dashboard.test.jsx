import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import Dashboard from './Dashboard';
import { useTranslation } from '../../hooks/useTranslation';
import { useAuth } from '../../hooks/useAuth';
import { mediaService } from '../../services/mediaService';

const mockNavigate = vi.fn();

// Mock dependencies
vi.mock('../../hooks/useTranslation');
vi.mock('../../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));
vi.mock('../../services/mediaService', () => ({
  mediaService: {
    getDashboardData: vi.fn(),
    uploadVideo: vi.fn(),
    uploadAudio: vi.fn(),
    uploadText: vi.fn(),
    deleteVideo: vi.fn(),
  },
}));
vi.mock('../../components/home/BackgroundDecorations', () => ({
  default: () => <div data-testid="background-decorations">Background</div>,
}));
vi.mock('../../components/layout/Navbar', () => ({
  default: () => <nav data-testid="navbar">Navbar</nav>,
}));
vi.mock('../../components/layout/Footer', () => ({
  default: () => <footer data-testid="footer">Footer</footer>,
}));
vi.mock('../../components/common/MediaPreviewModal', () => ({
  default: () => <div data-testid="preview-modal">Preview Modal</div>,
}));
vi.mock('../../components/dashboard/FileSelectorModal', () => ({
  default: () => <div data-testid="file-selector-modal">File Selector Modal</div>,
}));
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('Dashboard Page', () => {
  const mockT = vi.fn((key) => key);
  const mockJobs = {
    active: [
      { id: 'job_1', title: 'Processing Video.mp4', status: 'PROCESSING' }
    ],
    recent: [
      { id: 'job_2', title: 'Completed Video.mp4', status: 'COMPLETED', url: 'http://test.com/video.mp4', thumbnailUrl: 'http://test.com/thumb.jpg' }
    ]
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
    localStorage.clear();
    useTranslation.mockReturnValue({ t: mockT });
    useAuth.mockReturnValue({ user: { username: 'testuser', first_name: 'Test' } });
    mediaService.getDashboardData.mockResolvedValue(mockJobs);
  });

  const renderComponent = () => render(
    <BrowserRouter>
      <Dashboard />
    </BrowserRouter>
  );

  it('renders dashboard page and fetches data', async () => {
    renderComponent();

    expect(screen.getByText(/dashboard.welcome/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(mediaService.getDashboardData).toHaveBeenCalled();
      expect(screen.getByText(/Processing Video.mp4/i)).toBeInTheDocument();
      expect(screen.getByText(/Completed Video.mp4/i)).toBeInTheDocument();
    });
  });

  it('switches between tabs', async () => {
    const user = userEvent.setup();
    renderComponent();

    const videoTab = screen.getByRole('button', { name: /dashboard.tabVideo/i });
    const audioTab = screen.getByRole('button', { name: /dashboard.tabAudio/i });
    const textTab = screen.getByRole('button', { name: /dashboard.tabText/i });

    expect(videoTab.className).toContain('active');

    await user.click(audioTab);
    expect(audioTab.className).toContain('active');

    await user.click(textTab);
    expect(textTab.className).toContain('active');
  });

  it('handles file selection', async () => {
    const user = userEvent.setup();
    const file = new File(['test'], 'test.mp4', { type: 'video/mp4' });

    renderComponent();

    // Ensure video tab is active
    const videoTab = screen.getByRole('button', { name: /dashboard.tabVideo/i });
    await user.click(videoTab);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, file);

    await waitFor(() => {
      expect(screen.getByText(/test.mp4/i)).toBeInTheDocument();
    });
  });

  it('handles drag and drop', async () => {
    const user = userEvent.setup();
    const file = new File(['test'], 'test.mp4', { type: 'video/mp4' });

    renderComponent();

    const uploadArea = screen.getByText(/dashboard.uploadTitle/i).closest('.upload-area');

    await user.upload(uploadArea.querySelector('input[type="file"]'), file, {
      applyAccept: false,
    });

    // Simulate drop event
    const dropEvent = new Event('drop', { bubbles: true });
    Object.defineProperty(dropEvent, 'dataTransfer', {
      value: {
        files: [file],
      },
    });
    uploadArea.dispatchEvent(dropEvent);

    await waitFor(() => {
      expect(screen.getByText(/test.mp4/i)).toBeInTheDocument();
    });
  });

  it('updates form data', async () => {
    const user = userEvent.setup();
    renderComponent();

    const domainSelect = document.querySelector('select[name="domain"]');
    expect(domainSelect).toBeInTheDocument();
    await user.selectOptions(domainSelect, 'medical');

    expect(domainSelect.value).toBe('medical');
  });

  it('handles start processing', async () => {
    const user = userEvent.setup();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => { });
    const file = new File(['test'], 'test.mp4', { type: 'video/mp4' });
    mediaService.uploadVideo.mockResolvedValue({ id: 'new_job', status: 'PENDING' });

    renderComponent();

    const videoTab = screen.getByRole('button', { name: /dashboard.tabVideo/i });
    await user.click(videoTab);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, file);

    const startButton = screen.getByRole('button', { name: /dashboard.startProcessing/i });
    await user.click(startButton);

    await waitFor(() => {
      expect(mediaService.uploadVideo).toHaveBeenCalled();
      expect(alertSpy).toHaveBeenCalledWith('Upload successful! Processing started.');
    }, { timeout: 3000 });
    alertSpy.mockRestore();
  });

  it('handles job actions - delete', async () => {
    const user = userEvent.setup();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => { });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mediaService.deleteVideo.mockResolvedValue({});

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/Completed Video.mp4/i)).toBeInTheDocument();
    });

    // Open menu
    const menuButtons = screen.getAllByTitle('Options');
    await user.click(menuButtons[0]);

    // Click delete
    const deleteButton = screen.getByText(/dashboard.delete/i);
    await user.click(deleteButton);

    await waitFor(() => {
      expect(mediaService.deleteVideo).toHaveBeenCalledWith('job_2');
      expect(alertSpy).toHaveBeenCalledWith('Deleted successfully.');
    });
    alertSpy.mockRestore();
  });

  it('navigates to history page', async () => {
    const user = userEvent.setup();
    renderComponent();

    const historyButton = screen.getByRole('button', { name: /dashboard.viewFullHistory/i });
    await user.click(historyButton);

    expect(mockNavigate).toHaveBeenCalledWith('/history');
  });
});

