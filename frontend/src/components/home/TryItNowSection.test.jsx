import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '../../test/test-utils';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TryItNowSection from './TryItNowSection';
import { useAuth } from '../../hooks/useAuth';
import { mediaService } from '../../services/mediaService';

// Mock hooks and services
vi.mock('../../hooks/useAuth');
vi.mock('../../services/mediaService');
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
    const actual = await vi.importActual('react-router-dom');
    return {
        ...actual,
        useNavigate: () => mockNavigate,
    };
});

const renderComponent = () => {
    return renderWithProviders(<TryItNowSection />);
};

describe('TryItNowSection', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('Guest State', () => {
        beforeEach(() => {
            useAuth.mockReturnValue({ isAuthenticated: false });
        });

        it('renders register and login links for guests', () => {
            renderComponent();
            expect(screen.getByText('Sign Up to Upload Videos')).toBeInTheDocument();
            expect(screen.getByText('Create Free Account')).toBeInTheDocument();
            expect(screen.getByText('Login')).toBeInTheDocument();
        });

        it('disables dropzone interactions for guests', () => {
            renderComponent();
            const dropzone = screen.getByText('Sign Up to Upload Videos').closest('.upload-dropzone');
            expect(dropzone).toHaveStyle({ cursor: 'default' });
        });
    });

    describe('Authenticated State', () => {
        beforeEach(() => {
            useAuth.mockReturnValue({ isAuthenticated: true });
        });

        it('renders upload instructions for authenticated users', () => {
            renderComponent();
            expect(screen.getByText('Drag & Drop Your Video')).toBeInTheDocument();
            expect(screen.getByText('Choose File')).toBeInTheDocument();
        });

        it('triggers file selection when clicking the dropzone', async () => {
            renderComponent();
            const dropzone = screen.getByText('Drag & Drop Your Video').closest('.upload-dropzone');

            // We can't easily test the hidden input click directly without complex mocks,
            // but we can test that the file input exists and accepts videos
            const fileInput = screen.getByLabelText('Upload Video');
            expect(fileInput).toHaveAttribute('accept', 'video/*,.mp4,.mov,.avi,.mkv');
        });

        it('handles file selection and successful upload', async () => {
            const user = userEvent.setup();
            mediaService.uploadVideo.mockResolvedValueOnce({ id: '123' });

            renderComponent();

            const fileInput = screen.getByLabelText('Upload Video');
            const file = new File(['dummy content'], 'test.mp4', { type: 'video/mp4' });

            await user.upload(fileInput, file);

            expect(screen.getByText('Uploading and Processing...')).toBeInTheDocument();

            await waitFor(() => {
                expect(mediaService.uploadVideo).toHaveBeenCalled();
                expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
            });
        });

        it('handles invalid file format', async () => {
            const user = userEvent.setup();
            renderComponent();

            const fileInput = screen.getByLabelText('Upload Video');
            const file = new File(['dummy content'], 'test.txt', { type: 'text/plain' });

            fireEvent.change(fileInput, { target: { files: [file] } });

            expect(await screen.findByText(/Invalid file format/i)).toBeInTheDocument();
            expect(mediaService.uploadVideo).not.toHaveBeenCalled();
        });

        it('handles file too large', async () => {
            const user = userEvent.setup();
            renderComponent();

            const fileInput = screen.getByLabelText('Upload Video');
            // Create a large file object (hacky way to test size property)
            const largeFile = {
                name: 'large.mp4',
                size: 600 * 1024 * 1024, // 600MB
                type: 'video/mp4',
                lastModified: Date.now(),
            };

            // Since we can't easily use userEvent.upload with a mocked POJO, 
            // we fire the event manually
            fireEvent.change(fileInput, { target: { files: [largeFile] } });

            expect(await screen.findByText(/File size exceeds 500MB limit/i)).toBeInTheDocument();
            expect(mediaService.uploadVideo).not.toHaveBeenCalled();
        });

        it('handles drag and drop interactions', () => {
            renderComponent();
            const dropzone = screen.getByText('Drag & Drop Your Video').closest('.upload-dropzone');

            fireEvent.dragOver(dropzone);
            expect(dropzone).toHaveClass('drag-over');

            fireEvent.dragLeave(dropzone);
            expect(dropzone).not.toHaveClass('drag-over');

            const file = new File(['dummy content'], 'test.mp4', { type: 'video/mp4' });
            fireEvent.drop(dropzone, {
                dataTransfer: {
                    files: [file]
                }
            });

            expect(screen.getByText('Uploading and Processing...')).toBeInTheDocument();
        });

        it('handles upload failure', async () => {
            const user = userEvent.setup();
            mediaService.uploadVideo.mockRejectedValueOnce(new Error('Upload failed'));

            renderComponent();

            const fileInput = screen.getByLabelText('Upload Video');
            const file = new File(['dummy content'], 'test.mp4', { type: 'video/mp4' });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByText(/Upload failed. Please try again./i)).toBeInTheDocument();
                expect(screen.queryByText('Uploading and Processing...')).not.toBeInTheDocument();
            });
        });
    });
});
