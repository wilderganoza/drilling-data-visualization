import { create } from 'zustand';
import type { UserInfo } from '../api/endpoints/auth';

interface AuthState {
  token: string | null;
  user: UserInfo | null;
  isAuthenticated: boolean;
  setAuth: (token: string, user: UserInfo) => void;
  logout: () => void;
  loadFromStorage: () => void;
}

export const useAuthStore = create<AuthState>()((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,

  setAuth: (token, user) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('user', JSON.stringify(user));
    set({ token, user, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    set({ token: null, user: null, isAuthenticated: false });
    window.location.href = '/login';
  },

  loadFromStorage: () => {
    const token = localStorage.getItem('access_token');
    const userStr = localStorage.getItem('user');
    if (token && userStr) {
      try {
        const user = JSON.parse(userStr) as UserInfo;
        set({ token, user, isAuthenticated: true });
      } catch {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
      }
    }
  },
}));
