import { create } from 'zustand';
import { getInitialUser } from '../utils/authUtils';

const useStore = create((set) => ({
  // Global state
  user: getInitialUser(),
  theme: 'light',

  // Actions
  setUser: (user) => set({ user }),
  setTheme: (theme) => set({ theme }),
  reset: () => set({ user: getInitialUser() }),

  // Computed values
  isAuthenticated: () => {
    const state = useStore.getState();
    return !!state.user;
  },
}));

export default useStore;

