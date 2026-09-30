import apiClient from "./client";
import type { Repository } from "@/types";

export const repositoriesApi = {
  add: async (repo_url: string, force_refresh = false): Promise<Repository> => {
    const { data } = await apiClient.post("/repositories", { repo_url, force_refresh });
    return data;
  },

  list: async (): Promise<Repository[]> => {
    const { data } = await apiClient.get("/repositories");
    return data;
  },

  analyze: async (id: string, force_refresh = false): Promise<Repository> => {
    const { data } = await apiClient.post(`/repositories/${id}/analyze`, null, {
      params: { force_refresh },
    });
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/repositories/${id}`);
  },
};
