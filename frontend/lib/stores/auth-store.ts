/**
 * Global auth state (Zustand).
 * Keeps user + token state in memory; tokens are persisted in localStorage.
 * This store is the single source of truth for "is user logged in?".
 */

import { create } from "zustand";
import type { User } from "@/types";

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

  setTokens: (accessToken, refreshToken) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("access_token", accessToken);
      localStorage.setItem("refresh_token", refreshToken);
    }
  },

  clearTokens: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
    set({ user: null });
  },

  initialize: async () => {
    if (get().isInitialized) return;
    set({ isLoading: true });

    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

    if (!token) {
      set({ isInitialized: true, isLoading: false });
      return;
    }

    try {
      const { authApi } = await import("@/lib/api/auth");
      const user = await authApi.me();
      set({ user, isInitialized: true, isLoading: false });
    } catch {
      // Token invalid — clear and redirect
      get().clearTokens();
      set({ isInitialized: true, isLoading: false });
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
  },
}));
