import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient } from "@tanstack/react-query";

vi.mock("@/lib/api/client", () => ({
  default: {},
  API_URL: "http://api.test",
  refreshAccessToken: vi.fn(async () => "fresh-token"),
  handleAuthFailure: vi.fn(),
}));
const session = { token: "old-token" as string | null };
vi.mock("@/lib/session", () => ({ getAccessToken: () => session.token }));

import { EventsAuthError, readEventStream, reconnectDelay, type JobEvent } from "@/lib/api/events";
import { applyJobEvent } from "@/components/providers/live-events-provider";
import { handleAuthFailure, refreshAccessToken } from "@/lib/api/client";

function sseResponse(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "Content-Type": "text/event-stream" } });
}

const INDEXED: JobEvent = {
  type: "index_status",
  repo_id: "r1",
  index_status: "indexed",
  chunk_count: 42,
  indexed_commit_sha: "a".repeat(40),
  indexed_at: "2026-11-16T10:00:00Z",
  index_error: null,
};

describe("readEventStream", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    session.token = "old-token";
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
    vi.mocked(refreshAccessToken).mockClear();
    vi.mocked(handleAuthFailure).mockClear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("reports ready, delivers job events split across chunks, and ignores heartbeats", async () => {
    const json = JSON.stringify(INDEXED);
    fetchMock.mockResolvedValue(
      sseResponse(["event: ready\ndata: {}\n\n: ping\n\n", `event: job\ndata: ${json.slice(0, 20)}`, `${json.slice(20)}\n\n`]),
    );
    const onReady = vi.fn();
    const onEvent = vi.fn();
    await readEventStream({ onReady, onEvent }, new AbortController().signal);

    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/v1/events");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer old-token");
    expect(onReady).toHaveBeenCalledOnce();
    expect(onEvent).toHaveBeenCalledOnce();
    expect(onEvent).toHaveBeenCalledWith(INDEXED);
  });

  it("drops events it doesn't understand", async () => {
    fetchMock.mockResolvedValue(sseResponse(['event: job\ndata: {"type": "unknown", "repo_id": "r1"}\n\n']));
    const onEvent = vi.fn();
    await readEventStream({ onReady: vi.fn(), onEvent }, new AbortController().signal);
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("refreshes the token once on 401", async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "expired" }), { status: 401 }))
      .mockResolvedValueOnce(sseResponse(["event: ready\ndata: {}\n\n"]));
    const onReady = vi.fn();
    await readEventStream({ onReady, onEvent: vi.fn() }, new AbortController().signal);
    expect(refreshAccessToken).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer fresh-token");
    expect(onReady).toHaveBeenCalledOnce();
  });

  it("stops for good when signed out or the refresh fails", async () => {
    session.token = null;
    await expect(readEventStream({ onReady: vi.fn(), onEvent: vi.fn() }, new AbortController().signal)).rejects.toBeInstanceOf(
      EventsAuthError,
    );

    session.token = "old-token";
    fetchMock.mockResolvedValue(new Response("{}", { status: 401 }));
    vi.mocked(refreshAccessToken).mockRejectedValueOnce(new Error("no refresh token"));
    await expect(readEventStream({ onReady: vi.fn(), onEvent: vi.fn() }, new AbortController().signal)).rejects.toBeInstanceOf(
      EventsAuthError,
    );
    expect(handleAuthFailure).toHaveBeenCalledOnce();
  });

  it("rejects on server errors and on an error event so the caller reconnects", async () => {
    fetchMock.mockResolvedValueOnce(new Response("{}", { status: 503 }));
    await expect(readEventStream({ onReady: vi.fn(), onEvent: vi.fn() }, new AbortController().signal)).rejects.toThrow("503");

    fetchMock.mockResolvedValueOnce(sseResponse(['event: error\ndata: {"message": "down"}\n\n']));
    await expect(readEventStream({ onReady: vi.fn(), onEvent: vi.fn() }, new AbortController().signal)).rejects.toThrow(
      "unavailable",
    );
  });
});

describe("reconnectDelay", () => {
  it("backs off exponentially up to 30s", () => {
    const mid = () => 0.5; // no jitter
    expect([0, 1, 2, 3, 4, 5, 6, 10].map((n) => reconnectDelay(n, mid))).toEqual([
      1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000,
    ]);
    expect(reconnectDelay(0, () => 0)).toBe(750);
    expect(reconnectDelay(0, () => 1)).toBe(1250);
  });
});

describe("applyJobEvent", () => {
  it("writes an index result straight into the index-status query", () => {
    const qc = new QueryClient();
    applyJobEvent(qc, INDEXED);
    expect(qc.getQueryData(["index-status", "r1"])).toEqual({
      index_status: "indexed",
      chunk_count: 42,
      indexed_commit_sha: "a".repeat(40),
      indexed_at: "2026-11-16T10:00:00Z",
      index_error: null,
    });
  });

  it("refetches repository, review and debt data when an analysis finishes", () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    applyJobEvent(qc, { type: "repo_status", repo_id: "r1", status: "analyzed" });
    expect(spy.mock.calls.map(([f]) => f?.queryKey)).toEqual([["repositories"], ["repository", "r1"], ["reviews"], ["debt"]]);
  });
});
