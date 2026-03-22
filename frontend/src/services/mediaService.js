import api from './api';

export const mediaService = {
    uploadVideo: async (formData) => {
        return api.post('/videos/upload', formData);
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
