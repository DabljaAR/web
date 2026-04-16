export const getStorage = () => {
    // Access tokens should remain session-scoped.
    return sessionStorage;
};

export const getInitialUser = () => {
    try {
        const token = sessionStorage.getItem('access_token');
        const userData = sessionStorage.getItem('user');

        if (token && userData) {
            return JSON.parse(userData);
        }

        // Remember-me bootstrap: rely on refresh_token + user, not a persisted access token.
        if (localStorage.getItem('remember_me') === 'true') {
            const localUserData = localStorage.getItem('user');
            const localRefresh = localStorage.getItem('refresh_token');

            // Migrate any legacy persisted access token into the session, then remove it.
            const legacyAccess = localStorage.getItem('access_token');
            if (legacyAccess && !sessionStorage.getItem('access_token')) {
                sessionStorage.setItem('access_token', legacyAccess);
            }
            if (legacyAccess) {
                localStorage.removeItem('access_token');
            }

            // Ensure the refresh token is available in-session for API refresh logic.
            if (localRefresh && !sessionStorage.getItem('refresh_token')) {
                sessionStorage.setItem('refresh_token', localRefresh);
            }

            if (localUserData && (localRefresh || legacyAccess)) {
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
