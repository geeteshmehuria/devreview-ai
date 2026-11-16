/**
 * Axios-based API client with automatic token refresh and auth header injection.
 * All API calls go through this — never use fetch directly. The one exception is the
 * streaming chat helper in lib/api/chat.ts (axios can't stream in the browser); it reuses
 * refreshAccessToken() and handleAuthFailure() from here.
 */

import axios, { AxiosError, type AxiosRequestConfig } from "axios";
import { clearSession, getAccessToken, getRefreshToken, saveSession } from "@/lib/session";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** AI reviews can take a while (large inputs + provider fallback). */
export const AI_TIMEOUT_MS = 180_000;

export const apiClient = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

// ── Request interceptor: inject access token ──────────────────────────────────

apiClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor: readable errors + auto-refresh on 401 ──────────────

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value: unknown) => void;
  reject: (reason?: unknown) => void;
}> = [];

function processQueue(error: AxiosError | null, token: string | null = null) {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error);
    else resolve(token);
  });
  failedQueue = [];
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ detail?: unknown }>) => {
    // Surface the backend's message so `toast.error(e.message)` is meaningful everywhere.
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") error.message = detail;

    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          if (originalRequest.headers && token) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
          }
          return apiClient(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      if (!getRefreshToken()) {
        isRefreshing = false;
        handleAuthFailure();
        return Promise.reject(error);
      }

      try {
        const accessToken = await refreshAccessToken();
        processQueue(null, accessToken);

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${accessToken}`;
        }
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError as AxiosError, null);
        handleAuthFailure();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

let refreshInFlight: Promise<string> | null = null;

/**
 * Exchange the refresh token for a new token pair and store it. Concurrent callers share one
 * request, so the axios interceptor and the chat stream never refresh twice at once.
 */
export function refreshAccessToken(): Promise<string> {
  refreshInFlight ??= (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) throw new Error("Not signed in");
    const { data } = await axios.post(`${API_URL}/api/v1/auth/refresh`, { refresh_token: refreshToken });
    saveSession(data.access_token, data.refresh_token);
    return data.access_token as string;
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

export function handleAuthFailure() {
  clearSession();
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

export default apiClient;
