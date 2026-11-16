"use client";

/**
 * Keeps one live-events stream open while the app is visible and writes each job result straight
 * into the React Query cache, so the chat index panel and repository lists update the moment a
 * background job finishes — no status polling.
 *
 * Polling is kept only as a slow safety net (see useLiveEventsConnected): if the stream is down
 * (proxy hiccup, Redis outage), screens fall back to their old fast polling automatically.
 */

import { createContext, useContext, useEffect, useState } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { EventsAuthError, readEventStream, reconnectDelay, type JobEvent } from "@/lib/api/events";
import { indexStatusKey } from "@/lib/query-keys";
import { useAuthStore } from "@/lib/stores/auth-store";
import type { IndexStatus } from "@/types";

const LiveEventsContext = createContext(false);

/** True while the events stream is connected — use it to slow down fallback polling. */
export function useLiveEventsConnected() {
  return useContext(LiveEventsContext);
}

/** Apply one job event to the query cache. Exported for tests. */
export function applyJobEvent(qc: QueryClient, event: JobEvent) {
  if (event.type === "index_status") {
    const { index_status, chunk_count, indexed_commit_sha, indexed_at, index_error } = event;
    qc.setQueryData<IndexStatus>(indexStatusKey(event.repo_id), {
      index_status, chunk_count, indexed_commit_sha, indexed_at, index_error,
    });
  } else {
    // An analysis changes the repo's score/summary and creates a review and debt items.
    qc.invalidateQueries({ queryKey: ["repositories"] });
    qc.invalidateQueries({ queryKey: ["repository", event.repo_id] });
    qc.invalidateQueries({ queryKey: ["reviews"] });
    qc.invalidateQueries({ queryKey: ["debt"] });
  }
}

/** On (re)connect, refetch whatever may have finished while we weren't listening. */
function refreshInFlight(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: ["index-status"] });
  qc.invalidateQueries({ queryKey: ["repositories"] });
}

export function LiveEventsProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const signedIn = useAuthStore((s) => !!s.user);
  const [connected, setConnected] = useState(false);
  const [visible, setVisible] = useState(true);

  // Close the stream in background tabs (saves battery and server connections); reopen on return.
  useEffect(() => {
    const update = () => setVisible(document.visibilityState === "visible");
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);

  useEffect(() => {
    if (!signedIn || !visible) return;
    const controller = new AbortController();
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const run = async (attempt: number) => {
      let gotReady = false;
      try {
        await readEventStream(
          {
            onReady: () => {
              gotReady = true;
              setConnected(true);
              refreshInFlight(qc);
            },
            onEvent: (e) => applyJobEvent(qc, e),
          },
          controller.signal,
        );
      } catch (e) {
        if (e instanceof EventsAuthError) stopped = true;
      }
      setConnected(false);
      if (stopped || controller.signal.aborted) return;
      const next = gotReady ? 0 : attempt + 1; // a stream that worked restarts the backoff
      timer = setTimeout(() => run(next), reconnectDelay(next));
    };
    run(0);

    return () => {
      stopped = true;
      controller.abort();
      clearTimeout(timer);
      setConnected(false);
    };
  }, [qc, signedIn, visible]);

  return <LiveEventsContext.Provider value={connected}>{children}</LiveEventsContext.Provider>;
}
