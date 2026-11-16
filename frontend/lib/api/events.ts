/**
 * Live job events (Server-Sent Events from GET /api/v1/events).
 *
 * The backend runs indexing and repository analysis as background jobs (ARQ) and publishes one
 * event when each finishes. This keeps one stream open per tab instead of polling status
 * endpoints every few seconds. Like the chat stream it uses `fetch` (EventSource can't send the
 * Bearer header) and the axios client's token refresh.
 */

import type { IndexStatus, Repository } from "@/types";
import { API_URL, handleAuthFailure, refreshAccessToken } from "./client";
import { parseSSE } from "./chat";
import { getAccessToken } from "@/lib/session";

// Keep in sync with backend/app/jobs/events.py
export type JobEvent =
  | ({ type: "index_status"; repo_id: string } & IndexStatus)
  | { type: "repo_status"; repo_id: string; status: Repository["status"] };

export interface EventStreamHandlers {
  /** Subscribed: events from now on will arrive. Refetch anything that may have changed before. */
  onReady: () => void;
  onEvent: (event: JobEvent) => void;
}

/** Thrown when the stream can't be used at all (signed out); callers stop reconnecting. */
export class EventsAuthError extends Error {}

/**
 * Open the stream and read it until it ends. Resolves when the server closes the connection or
 * `signal` aborts; rejects on network/HTTP errors. Reconnecting is the caller's job.
 */
export async function readEventStream(handlers: EventStreamHandlers, signal: AbortSignal): Promise<void> {
  const open = (token: string | null) =>
    fetch(`${API_URL}/api/v1/events`, {
      headers: { Accept: "text/event-stream", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      signal,
    });

  const token = getAccessToken();
  if (!token) throw new EventsAuthError("Not signed in");
  let response = await open(token);
  if (response.status === 401) {
    try {
      response = await open(await refreshAccessToken());
    } catch {
      handleAuthFailure();
      throw new EventsAuthError("Session expired");
    }
  }
  if (!response.ok || !response.body) throw new Error(`Event stream failed (${response.status})`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSSE(buffer); // ": ping" heartbeats carry no data and are skipped
    buffer = parsed.rest;
    for (const { event, data } of parsed.events) {
      if (event === "ready") handlers.onReady();
      else if (event === "job" && isJobEvent(data)) handlers.onEvent(data);
      else if (event === "error") throw new Error("Live updates unavailable");
    }
  }
}

function isJobEvent(data: unknown): data is JobEvent {
  const d = data as Partial<JobEvent> | null;
  return !!d && typeof d.repo_id === "string" && (d.type === "index_status" || d.type === "repo_status");
}

/** Wait before reconnect attempt `n` (0-based): 1s, 2s, 4s … capped at 30s, with jitter. */
export function reconnectDelay(attempt: number, random: () => number = Math.random): number {
  const base = Math.min(30_000, 1_000 * 2 ** attempt);
  return Math.round(base * (0.75 + random() * 0.5));
}
