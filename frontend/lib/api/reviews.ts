import apiClient, { AI_TIMEOUT_MS } from "./client";
import type { DebtItem, Review, ReviewListResponse, PRReviewResult } from "@/types";

export const reviewsApi = {
  reviewCode: async (payload: {
    content: string;
    language?: string;
    filename?: string;
    detail_level?: string;
  }): Promise<Review> => {
    const { data } = await apiClient.post("/reviews/code", payload, { timeout: AI_TIMEOUT_MS });
    return data;
  },

  reviewFile: async (file: File, options?: { language?: string; detail_level?: string }): Promise<Review> => {
    const form = new FormData();
    form.append("file", file);
    form.append("language", options?.language || "auto");
    form.append("detail_level", options?.detail_level || "detailed");
    const { data } = await apiClient.post("/reviews/file", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: AI_TIMEOUT_MS,
    });
    return data;
  },

  reviewPR: async (payload: { pr_url: string; detail_level?: string }): Promise<PRReviewResult> => {
    const { data } = await apiClient.post("/pull-requests/review", payload, { timeout: AI_TIMEOUT_MS });
    return data;
  },

  list: async (params?: {
    page?: number;
    page_size?: number;
    review_type?: string;
  }): Promise<ReviewListResponse> => {
    const { data } = await apiClient.get("/reviews", { params });
    return data;
  },

  get: async (id: string): Promise<Review> => {
    const { data } = await apiClient.get(`/reviews/${id}`);
    return data;
  },

  debt: async (): Promise<DebtItem[]> => {
    const { data } = await apiClient.get("/reviews/debt");
    return data;
  },
};
