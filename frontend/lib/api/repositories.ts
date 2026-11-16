import apiClient from "./client";
import type { GitHubRepo, IndexStatus, Repository } from "@/types";

export const repositoriesApi = {
  add: async (repo_url: string, force_refresh = false): Promise<Repository> => {
    const { data } = await apiClient.post("/repositories", { repo_url, force_refresh });
    return data;
  },

  list: async (): Promise<Repository[]> => {
    const { data } = await apiClient.get("/repositories");
    return data;
  },

  /** Repos on the user's GitHub account (owned, collaborator, org), for the import picker. */
  listGitHub: async (): Promise<GitHubRepo[]> => {
    const { data } = await apiClient.get("/repositories/github");
    return data;
  },

  analyze: async (id: string, force_refresh = false): Promise<Repository> => {
    const { data } = await apiClient.post(`/repositories/${id}/analyze`, null, {
      params: { force_refresh },
    });
    return data;
  },

  get: async (id: string): Promise<Repository> => {
    const { data } = await apiClient.get(`/repositories/${id}`);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/repositories/${id}`);
  },

  /** Start (or restart) RAG indexing for chat. Returns the current state if already running. */
  index: async (id: string): Promise<IndexStatus> => {
    const { data } = await apiClient.post(`/repositories/${id}/index`);
    return data;
  },

  indexStatus: async (id: string): Promise<IndexStatus> => {
    const { data } = await apiClient.get(`/repositories/${id}/index-status`);
    return data;
  },
};
