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

    getVideos: async () => {
        return api.get('/videos/');
    }
};
