import apiClient, { API_URL, handleAuthFailure, refreshAccessToken } from "./client";
import { getAccessToken } from "@/lib/session";
import type { ChatCitation, ChatMessage, ChatSession } from "@/types";

export const chatApi = {
  listSessions: async (repoId: string): Promise<ChatSession[]> => {
    const { data } = await apiClient.get(`/repositories/${repoId}/chat/sessions`);
    return data;
  },

  createSession: async (repoId: string): Promise<ChatSession> => {
    const { data } = await apiClient.post(`/repositories/${repoId}/chat/sessions`, {});
    return data;
  },

  deleteSession: async (sessionId: string): Promise<void> => {
    await apiClient.delete(`/chat/sessions/${sessionId}`);
  },

  listMessages: async (sessionId: string): Promise<ChatMessage[]> => {
    const { data } = await apiClient.get(`/chat/sessions/${sessionId}/messages`);
    return data;
  },
};

// ── Streaming (Server-Sent Events) ────────────────────────────────────────────

export interface SSEEvent {
  event: string;
  data: unknown;
}

/**
 * Parse complete SSE events out of `buffer`. Network chunks can end mid-event, so whatever
 * follows the last blank line is returned as `rest` and must be prepended to the next chunk.
 */
export function parseSSE(buffer: string): { events: SSEEvent[]; rest: string } {
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: SSEEvent[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length === 0) continue;
    try {
      events.push({ event, data: JSON.parse(data.join("\n")) });
    } catch {
      // Ignore a malformed event rather than killing the whole answer.
    }
  }
  return { events, rest };
}

export interface StreamHandlers {
  onToken: (text: string) => void;
  onCitations: (citations: ChatCitation[], lowConfidence: boolean) => void;
  onDone: (messageId: string) => void;
  onError: (message: string) => void;
}

/**
 * POST a chat message and stream the answer.
 *
 * This is the one place the app uses `fetch` instead of the axios client: axios can't read a
 * response body as a stream in the browser, and `EventSource` can't send a POST body or the
 * Bearer header. So we read `response.body` with a ReadableStream reader, and reuse the axios
 * client's token refresh (once, on 401) so auth behaves the same as everywhere else.
 */
export async function streamChatMessage(
  sessionId: string,
  content: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const send = (token: string | null) =>
    fetch(`${API_URL}/api/v1/chat/sessions/${sessionId}/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content }),
      signal,
    });

  let response = await send(getAccessToken());
  if (response.status === 401) {
    let token: string;
    try {
      token = await refreshAccessToken();
    } catch {
      handleAuthFailure();
      throw new Error("Your session expired. Please sign in again.");
    }
    response = await send(token);
  }

  if (!response.ok || !response.body) {
    // Errors before streaming starts (404, 409 not indexed, 422, 429) are normal JSON responses.
    const detail = await response.json().then((b) => b?.detail, () => null);
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSSE(buffer);
    buffer = parsed.rest;
    for (const { event, data } of parsed.events) {
      const d = data as Record<string, unknown>;
      if (event === "token") handlers.onToken(String(d.text ?? ""));
      else if (event === "citations") handlers.onCitations((d.citations as ChatCitation[]) ?? [], Boolean(d.low_confidence));
      else if (event === "done") handlers.onDone(String(d.message_id ?? ""));
      else if (event === "error") handlers.onError(String(d.message ?? "Something went wrong."));
      finished ||= event === "done" || event === "error";
    }
  }
  // The connection closed mid-answer (server restart, proxy timeout): without this the UI waits forever.
  if (!finished) handlers.onError("The connection was lost before the answer finished. Please try again.");
}
