import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import Dashboard from './Dashboard';
import { useTranslation } from '../../hooks/useTranslation';

const mockNavigate = vi.fn();

// Mock dependencies
vi.mock('../../hooks/useTranslation');
vi.mock('../../components/home/BackgroundDecorations', () => ({
  default: () => <div data-testid="background-decorations">Background</div>,
}));
vi.mock('../../components/layout/Navbar', () => ({
  default: () => <nav data-testid="navbar">Navbar</nav>,
}));
vi.mock('../../components/layout/Footer', () => ({
  default: () => <footer data-testid="footer">Footer</footer>,
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

  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
    useTranslation.mockReturnValue({ t: mockT });
  });

  it('renders dashboard page', () => {
    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    expect(screen.getByText(/dashboard.welcome/i)).toBeInTheDocument();
    expect(screen.getByText(/dashboard.uploadContent/i)).toBeInTheDocument();
  });

  it('switches between tabs', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

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
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const file = new File(['test'], 'test.mp4', { type: 'video/mp4' });

    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, file);

    expect(alertSpy).toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('handles drag and drop', async () => {
    const user = userEvent.setup();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const file = new File(['test'], 'test.mp4', { type: 'video/mp4' });

    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

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

    expect(alertSpy).toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('updates form data', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    const domainSelect = document.querySelector('select[name="domain"]');
    expect(domainSelect).toBeInTheDocument();
    await user.selectOptions(domainSelect, 'medical');

    expect(domainSelect.value).toBe('medical');
  });

  it('handles start processing', async () => {
    const user = userEvent.setup();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    const startButton = screen.getByRole('button', { name: /dashboard.startProcessing/i });
    await user.click(startButton);

    expect(alertSpy).toHaveBeenCalledWith('Processing started! (Demo)');
    alertSpy.mockRestore();
  });

  it('displays processing jobs', () => {
    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    expect(screen.getByText(/Video_123.mp4/i)).toBeInTheDocument();
    expect(screen.getByText(/45%/i)).toBeInTheDocument();
  });

  it('displays recent jobs', () => {
    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    expect(screen.getByText(/Tech_Tutorial.mp4/i)).toBeInTheDocument();
    expect(screen.getByText(/Medical_Lecture.mp4/i)).toBeInTheDocument();
  });

  it('handles job actions', async () => {
    const user = userEvent.setup();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    const previewButtons = screen.getAllByRole('button', { name: /dashboard.preview/i });
    await user.click(previewButtons[0]);

    expect(alertSpy).toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('navigates to history page', async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>
    );

    const historyButton = screen.getByRole('button', { name: /dashboard.viewFullHistory/i });
    await user.click(historyButton);

    expect(mockNavigate).toHaveBeenCalledWith('/history');
  });
});

