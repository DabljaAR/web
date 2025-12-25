import { create } from 'zustand';

const useStore = create((set) => ({
  // Global state
  user: null,
  theme: 'light',
  
  // Actions
  setUser: (user) => set({ user }),
  setTheme: (theme) => set({ theme }),
  
  // Computed values
  isAuthenticated: () => {
    const state = useStore.getState();
    return !!state.user;
  },
}));

export default useStore;

