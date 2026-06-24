import apiClient from "./client";
import type { TokenPair, User } from "@/types";

export const authApi = {
  getGithubUrl: async (): Promise<{ url: string }> => {
    const { data } = await apiClient.get("/auth/github/url");
    return data;
  },

  githubCallback: async (code: string): Promise<{ tokens: TokenPair; user: User }> => {
    const { data } = await apiClient.post("/auth/github/callback", { code });
    return data;
  },

  refresh: async (refreshToken: string): Promise<TokenPair> => {
    const { data } = await apiClient.post("/auth/refresh", { refresh_token: refreshToken });
    return data;
  },

  logout: async (): Promise<void> => {
    await apiClient.post("/auth/logout");
  },

  me: async (): Promise<User> => {
    const { data } = await apiClient.get("/auth/me");
    return data;
  },
};
