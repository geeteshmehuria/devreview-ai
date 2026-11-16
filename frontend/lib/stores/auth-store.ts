/**
 * Global auth state (Zustand).
 * Keeps user state in memory; tokens are persisted via lib/session.
 * This store is the single source of truth for "is user logged in?".
 */

import { create } from "zustand";
import type { User } from "@/types";
import { clearSession, getAccessToken, saveSession } from "@/lib/session";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isInitialized: boolean;

  setUser: (user: User | null) => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
  clearTokens: () => void;
  initialize: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isLoading: false,
  isInitialized: false,

  setUser: (user) => set({ user }),

  setTokens: (accessToken, refreshToken) => saveSession(accessToken, refreshToken),

  clearTokens: () => {
    clearSession();
    set({ user: null });
  },

  initialize: async () => {
    if (get().isInitialized) return;
    set({ isLoading: true });

    if (!getAccessToken()) {
      set({ isInitialized: true, isLoading: false });
      return;
    }

    try {
      const { authApi } = await import("@/lib/api/auth");
      const user = await authApi.me();
      set({ user, isInitialized: true, isLoading: false });
    } catch {
      // A rejected token is already cleared by the API client (after a failed refresh).
      // Anything else (timeout, backend cold start, 5xx) must not log the user out.
      set({ user: null, isInitialized: true, isLoading: false });
    }
  },

  logout: async () => {
    try {
      const { authApi } = await import("@/lib/api/auth");
      await authApi.logout();
    } catch {
      // ignore API errors during logout
    }
    get().clearTokens();
    window.location.href = "/login";
  },
}));
