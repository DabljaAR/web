export const getStorage = () => {
    const rememberMe = localStorage.getItem('remember_me') === 'true';
    return rememberMe ? localStorage : sessionStorage;
};

export const getInitialUser = () => {
    try {
        // Check localStorage first (remember me)
        let token = localStorage.getItem('access_token');
        let userData = localStorage.getItem('user');

        // If not in localStorage, check sessionStorage
        if (!token || !userData) {
            token = sessionStorage.getItem('access_token');
            userData = sessionStorage.getItem('user');
        }

        if (token && userData) {
            return JSON.parse(userData);
        }
    } catch (e) {
        // Invalid user data, clear it
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
        sessionStorage.removeItem('user');
    }
    return null;
};
