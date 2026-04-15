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

        // If "remember me" was selected, allow bootstrapping auth from localStorage.
        if (localStorage.getItem('remember_me') === 'true') {
            const localToken = localStorage.getItem('access_token');
            const localUserData = localStorage.getItem('user');
            if (localToken && localUserData) {
                return JSON.parse(localUserData);
            }
        }
    } catch (e) {
        // Invalid user data, clear it
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        localStorage.removeItem('remember_me');
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
        sessionStorage.removeItem('user');
    }
    return null;
};
