import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mediaService } from './mediaService';
import api from './api';

// Mock the api module
vi.mock('./api');

describe('MediaService', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('uploadVideo', () => {
        it('calls api.post with correct endpoint and formData', async () => {
            const formData = new FormData();
            formData.append('file', new File(['video content'], 'video.mp4', { type: 'video/mp4' }));

            const mockResponse = { id: 'vid_123', status: 'PENDING' };
            api.post.mockResolvedValueOnce(mockResponse);

            const result = await mediaService.uploadVideo(formData);

            expect(api.post).toHaveBeenCalledWith('/videos/upload', formData);
            expect(result).toEqual(mockResponse);
        });
    });

    describe('uploadAudio', () => {
        it('calls api.post with correct endpoint and formData', async () => {
            const formData = new FormData();
            formData.append('file', new File(['audio content'], 'audio.mp3', { type: 'audio/mpeg' }));

            const mockResponse = { id: 'aud_123', status: 'PENDING' };
            api.post.mockResolvedValueOnce(mockResponse);

            const result = await mediaService.uploadAudio(formData);

            expect(api.post).toHaveBeenCalledWith('/videos/upload/audio', formData);
            expect(result).toEqual(mockResponse);
        });
    });

    describe('uploadText', () => {
        it('calls api.post with correct endpoint and formData', async () => {
            const formData = new FormData();
            formData.append('file', new File(['text content'], 'text.txt', { type: 'text/plain' }));

            const mockResponse = { id: 'txt_123', status: 'COMPLETED' };
            api.post.mockResolvedValueOnce(mockResponse);

            const result = await mediaService.uploadText(formData);

            expect(api.post).toHaveBeenCalledWith('/videos/upload/text', formData);
            expect(result).toEqual(mockResponse);
        });
    });

    describe('getDashboardData', () => {
        it('calls api.get with correct endpoint', async () => {
            const mockData = { active: [], recent: [] };
            api.get.mockResolvedValueOnce(mockData);

            const result = await mediaService.getDashboardData();

            expect(api.get).toHaveBeenCalledWith('/videos/dashboard', expect.any(Object));
            expect(result).toEqual(mockData);
        });
    });

    describe('getVideos', () => {
        it('calls api.get with correct query parameters', async () => {
            const params = {
                page: 2,
                limit: 20,
                search: 'test',
                sortBy: 'name-asc',
                dateRange: 'last7Days',
                status: 'COMPLETED',
                mediaType: 'VIDEO'
            };

            api.get.mockResolvedValueOnce({ items: [], total: 0 });

            await mediaService.getVideos(params);

            expect(api.get).toHaveBeenCalledWith(
                expect.stringContaining('/videos/?'),
                expect.any(Object)
            );

            const url = api.get.mock.calls[0][0];
            expect(url).toContain('page=2');
            expect(url).toContain('limit=20');
            expect(url).toContain('search=test');
            expect(url).toContain('sortBy=name-asc');
            expect(url).toContain('dateRange=last7Days');
            expect(url).toContain('status=COMPLETED');
            expect(url).toContain('mediaType=VIDEO');
        });

        it('works with empty parameters', async () => {
            api.get.mockResolvedValueOnce({ items: [], total: 0 });

            await mediaService.getVideos();

            expect(api.get).toHaveBeenCalledWith('/videos/', expect.any(Object));
        });
    });

    describe('deleteVideo', () => {
        it('calls api.delete with correct endpoint', async () => {
            api.delete.mockResolvedValueOnce({ message: 'Deleted' });

            const result = await mediaService.deleteVideo('vid_123');

            expect(api.delete).toHaveBeenCalledWith('/videos/vid_123');
            expect(result).toEqual({ message: 'Deleted' });
        });
    });
});
