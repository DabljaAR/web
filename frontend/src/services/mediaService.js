import api from './api';

export const mediaService = {
    uploadVideo: async (formData) => {
        return api.post('/videos/upload', formData);
    },

    downloadFromYoutube: async (params) => {
        const formData = new FormData();
        formData.append('youtube_url', params.youtube_url);
        formData.append('format', params.format);
        formData.append('quality', params.quality);
        if (params.output_type) formData.append('output_type', params.output_type);
        if (params.domain) formData.append('domain', params.domain);
        if (params.voice) formData.append('voice', params.voice);
        if (params.translation_style) formData.append('translation_style', params.translation_style);
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



    getDashboardData: async (options = {}) => {
        // Forward fetch options (e.g. { signal } for AbortController) to api.get.
        return api.get('/videos/dashboard', options);
    },

    getVideos: async (params = {}, options = {}) => {
        // `params` are strictly query params.
        // `options` are forwarded to fetch via api.get (e.g. { signal } for AbortController).
        // Back-compat: if callers accidentally pass `signal` inside params, plumb it through.
        const { signal, ...query } = params || {};
        const requestOptions = signal ? { ...options, signal } : options;

        // Build query string
        const queryParams = new URLSearchParams();
        if (query.page) queryParams.append('page', query.page);
        if (query.limit) queryParams.append('limit', query.limit);
        if (query.search) queryParams.append('search', query.search);
        if (query.sortBy) queryParams.append('sortBy', query.sortBy);
        if (query.dateRange) queryParams.append('dateRange', query.dateRange);
        if (query.status && query.status !== 'all') queryParams.append('status', query.status);
        if (query.mediaType && query.mediaType !== 'all') queryParams.append('mediaType', query.mediaType);

        const qs = queryParams.toString();
        const endpoint = qs ? `/videos/?${qs}` : '/videos/';
        return api.get(endpoint, requestOptions);
    },

    deleteVideo: async (id) => {
        return api.delete(`/videos/${id}`);
    }
};
