export const getStorage = () => {
    return sessionStorage;
};

export const getInitialUser = () => {
    try {
        const token = sessionStorage.getItem('access_token');
        const userData = sessionStorage.getItem('user');

        if (token && userData) {
            return JSON.parse(userData);
        }
    } catch (e) {
        // Invalid user data, clear it
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
        sessionStorage.removeItem('user');
    }
    return null;
};
