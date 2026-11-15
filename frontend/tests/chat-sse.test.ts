import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("@/lib/api/client", () => ({
  default: {},
  API_URL: "http://api.test",
  refreshAccessToken: vi.fn(async () => "fresh-token"),
  handleAuthFailure: vi.fn(),
}));
vi.mock("@/lib/session", () => ({ getAccessToken: () => "old-token" }));

import { parseSSE, streamChatMessage } from "@/lib/api/chat";
import { handleAuthFailure, refreshAccessToken } from "@/lib/api/client";

describe("parseSSE", () => {
  it("parses complete events and keeps the unfinished tail", () => {
    const { events, rest } = parseSSE(
      'event: token\ndata: {"text": "Hel"}\n\nevent: token\ndata: {"text": "lo"}\n\nevent: cit',
    );
    expect(events).toEqual([
      { event: "token", data: { text: "Hel" } },
      { event: "token", data: { text: "lo" } },
    ]);
    expect(rest).toBe("event: cit");
  });

  it("handles CRLF line endings and multi-line data", () => {
    const { events } = parseSSE('event: done\r\ndata: {"message_id":\r\ndata: "m1"}\r\n\r\n');
    expect(events).toEqual([{ event: "done", data: { message_id: "m1" } }]);
  });

  it("keeps newlines inside JSON-encoded tokens", () => {
    const { events } = parseSSE('event: token\ndata: {"text": "line1\\n\\nline2"}\n\n');
    expect((events[0].data as { text: string }).text).toBe("line1\n\nline2");
  });

  it("skips malformed events and comment/heartbeat blocks", () => {
    const { events } = parseSSE(': ping\n\nevent: token\ndata: {broken\n\nevent: done\ndata: {"message_id": "x"}\n\n');
    expect(events).toEqual([{ event: "done", data: { message_id: "x" } }]);
  });

  it("defaults the event name to 'message'", () => {
    expect(parseSSE('data: {"a": 1}\n\n').events).toEqual([{ event: "message", data: { a: 1 } }]);
  });
});

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

function handlers() {
  return { onToken: vi.fn(), onCitations: vi.fn(), onDone: vi.fn(), onError: vi.fn() };
}

describe("streamChatMessage", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("dispatches events even when they are split across network chunks", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse([
        'event: token\ndata: {"text": "Uses sl',  // split mid-event
        'owapi [1]"}\n\nevent: citations\ndata: {"citations": [{"n": 1}], "low_confidence": true}\n\n',
        'event: done\ndata: {"message_id": "m1"}\n\n',
      ]),
    );
    const h = handlers();
    await streamChatMessage("s1", "Where is rate limiting?", h);

    expect(h.onToken).toHaveBeenCalledWith("Uses slowapi [1]");
    expect(h.onCitations).toHaveBeenCalledWith([{ n: 1 }], true);
    expect(h.onDone).toHaveBeenCalledWith("m1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/chat/sessions/s1/messages");
    expect(init.headers.Authorization).toBe("Bearer old-token");
    expect(JSON.parse(init.body)).toEqual({ content: "Where is rate limiting?" });
  });

  it("refreshes the token once on 401 and retries", async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(sseResponse(['event: done\ndata: {"message_id": "m2"}\n\n']));
    const h = handlers();
    await streamChatMessage("s1", "q", h);
    expect(refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer fresh-token");
    expect(h.onDone).toHaveBeenCalledWith("m2");
  });

  it("signs out when the refresh fails", async () => {
    vi.mocked(refreshAccessToken).mockRejectedValueOnce(new Error("expired"));
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }));
    await expect(streamChatMessage("s1", "q", handlers())).rejects.toThrow(/session expired/i);
    expect(handleAuthFailure).toHaveBeenCalled();
  });

  it("surfaces the backend's detail for errors before streaming (e.g. 409 not indexed)", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "This repository isn't indexed yet." }), { status: 409 }),
    );
    await expect(streamChatMessage("s1", "q", handlers())).rejects.toThrow("This repository isn't indexed yet.");
  });

  it("passes error events to onError", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse(['event: error\ndata: {"message": "All AI providers failed."}\n\n']));
    const h = handlers();
    await streamChatMessage("s1", "q", h);
    expect(h.onError).toHaveBeenCalledWith("All AI providers failed.");
    expect(h.onDone).not.toHaveBeenCalled();
  });
});
