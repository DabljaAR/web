import api from './api';

export const mediaService = {
    uploadVideo: async (formData) => {
        return api.post('/videos/upload', formData);
    },

    downloadFromYoutube: async ({ youtube_url, format, quality }) => {
        const formData = new FormData();
        formData.append('youtube_url', youtube_url);
        formData.append('format', format);
        formData.append('quality', quality);
        return api.post('/videos/upload/youtube', formData);
    },

    uploadAudio: async (formData) => {
        return api.post('/videos/upload/audio', formData);
    },

    uploadText: async (formData) => {
        return api.post('/videos/upload/text', formData);
    },

    reprocessMedia: async (id, payload) => {
        return api.post(`/videos/${id}/reprocess`, payload);
    },



    getDashboardData: async () => {
        return api.get('/videos/dashboard');
    },

    getVideos: async (params = {}) => {
        // Build query string
        const queryParams = new URLSearchParams();
        if (params.page) queryParams.append('page', params.page);
        if (params.limit) queryParams.append('limit', params.limit);
        if (params.search) queryParams.append('search', params.search);
        if (params.sortBy) queryParams.append('sortBy', params.sortBy);
        if (params.dateRange) queryParams.append('dateRange', params.dateRange);
        if (params.status) queryParams.append('status', params.status);
        if (params.mediaType) queryParams.append('mediaType', params.mediaType);

        return api.get(`/videos/?${queryParams.toString()}`);
    },

    deleteVideo: async (id) => {
        return api.delete(`/videos/${id}`);
    }
};
