"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Loader2, MessageSquare, Plus, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { chatApi, streamChatMessage } from "@/lib/api/chat";
import { ChatMessageView } from "@/components/chat/chat-message";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { ChatCitation } from "@/types";

const EXAMPLE_QUESTIONS = [
  "How is authentication handled?",
  "What are the main API endpoints?",
  "Where is the database configured?",
  "Are there known security issues in this code?",
];
const MAX_CHARS = 2000; // matches the backend's ChatMessageCreate limit

/** The question being answered right now; replaced by the saved messages once `done` arrives. */
interface PendingTurn {
  question: string;
  answer: string;
  citations: ChatCitation[];
  lowConfidence: boolean;
  error: string | null;
}

export function RepoChat({ repoId, indexed }: { repoId: string; indexed: boolean }) {
  const qc = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<PendingTurn | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sessionsKey = ["chat-sessions", repoId];

  const { data: sessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: sessionsKey,
    queryFn: () => chatApi.listSessions(repoId),
  });
  const { data: messages = [], isLoading: messagesLoading } = useQuery({
    queryKey: ["chat-messages", activeId],
    queryFn: () => chatApi.listMessages(activeId!),
    enabled: !!activeId,
  });

  const streaming = !!pending && !pending.error;

  // Open the most recent conversation on first load only — "New chat" also sets activeId to null.
  const autoOpened = useRef(false);
  useEffect(() => {
    if (autoOpened.current || sessionsLoading) return;
    autoOpened.current = true;
    if (sessions.length > 0) setActiveId(sessions[0].id);
  }, [sessions, sessionsLoading]);

  // Stop any in-flight answer when leaving the page.
  useEffect(() => () => abortRef.current?.abort(), []);

  // Keep the newest text in view while it streams.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  const switchTo = (id: string | null) => {
    abortRef.current?.abort();
    setPending(null);
    setActiveId(id);
  };

  const deleteMutation = useMutation({
    mutationFn: chatApi.deleteSession,
    onSuccess: (_, id) => {
      if (id === activeId) switchTo(null);
      qc.invalidateQueries({ queryKey: sessionsKey });
    },
    onError: (e: Error) => toast.error(e.message || "Failed to delete conversation"),
  });

  const send = async (raw: string) => {
    const question = raw.trim();
    if (!question || streaming || !indexed) return;
    setInput("");
    setPending({ question, answer: "", citations: [], lowConfidence: false, error: null });

    let sessionId = activeId;
    try {
      if (!sessionId) {
        sessionId = (await chatApi.createSession(repoId)).id;
        setActiveId(sessionId);
      }
    } catch (e) {
      setPending((p) => p && { ...p, error: (e as Error).message || "Couldn't start a conversation" });
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    const sid = sessionId;
    try {
      await streamChatMessage(
        sid,
        question,
        {
          onToken: (text) => setPending((p) => p && { ...p, answer: p.answer + text }),
          onCitations: (citations, lowConfidence) => setPending((p) => p && { ...p, citations, lowConfidence }),
          onDone: async () => {
            // Show the saved messages first, then drop the temporary turn — no flicker.
            await qc.invalidateQueries({ queryKey: ["chat-messages", sid] });
            qc.invalidateQueries({ queryKey: sessionsKey }); // title + order changed
            setPending(null);
          },
          onError: (message) => setPending((p) => p && { ...p, error: message }),
        },
        controller.signal,
      );
    } catch (e) {
      if (controller.signal.aborted) return;
      setPending((p) => p && { ...p, error: (e as Error).message || "Something went wrong." });
    }
  };

  if (!indexed) {
    return (
      <div className="glass-card rounded-2xl p-12 text-center">
        <Database className="w-12 h-12 text-slate-600 mx-auto mb-3" />
        <p className="text-white font-medium mb-1">Index this repository to start chatting</p>
        <p className="text-slate-400 text-sm">
          Indexing reads the code, splits it into functions and classes, and makes it searchable.
        </p>
      </div>
    );
  }

  const empty = !pending && messages.length === 0 && !messagesLoading;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
      {/* Conversations */}
      <aside className="glass-card rounded-2xl p-3 space-y-2 max-h-56 md:max-h-none md:h-[calc(100vh-340px)] md:min-h-[480px] overflow-y-auto">
        <button
          onClick={() => switchTo(null)}
          className="w-full flex items-center justify-center md:justify-start gap-2 px-3 h-10 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" /> New chat
        </button>
        {sessionsLoading ? (
          [...Array(3)].map((_, i) => <div key={i} className="h-10 rounded-lg animate-pulse bg-surface-2" />)
        ) : (
          sessions.map((s) => (
            <div
              key={s.id}
              className={cn(
                "group flex items-center gap-1 rounded-lg transition-colors",
                s.id === activeId ? "bg-surface-3" : "hover:bg-surface-2",
              )}
            >
              <button onClick={() => switchTo(s.id)} className="flex-1 min-w-0 text-left px-3 py-2">
                <p className="text-sm text-white truncate">{s.title}</p>
                <p className="text-xs text-slate-500">{formatRelativeTime(s.updated_at)}</p>
              </button>
              <button
                onClick={() => {
                  if (confirm(`Delete "${s.title}"?`)) deleteMutation.mutate(s.id);
                }}
                className="w-9 h-9 mr-1 flex items-center justify-center rounded-md text-slate-500 hover:text-red-400 md:opacity-0 md:group-hover:opacity-100 focus:opacity-100 transition-opacity"
                aria-label={`Delete conversation ${s.title}`}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))
        )}
      </aside>

      {/* Conversation */}
      <section className="glass-card rounded-2xl flex flex-col h-[72dvh] min-h-[420px] md:h-[calc(100vh-340px)] md:min-h-[480px]">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
          {messagesLoading && activeId ? (
            <div className="flex justify-center py-10">
              <Loader2 className="w-6 h-6 text-brand-400 animate-spin" />
            </div>
          ) : empty ? (
            <div className="h-full flex flex-col items-center justify-center text-center gap-4">
              <MessageSquare className="w-10 h-10 text-slate-600" />
              <div>
                <p className="text-white font-medium">Ask anything about this repository</p>
                <p className="text-slate-400 text-sm mt-1">
                  Answers come from the indexed code and saved review findings, with links to the exact lines.
                </p>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 w-full max-w-xl">
                {EXAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    className="text-left text-sm px-4 py-3 rounded-xl border border-surface-border bg-surface-2 text-slate-300 hover:border-brand-500 hover:text-white transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {messages.map((m) => (
                <ChatMessageView key={m.id} role={m.role} content={m.content} citations={m.citations} />
              ))}
              {pending && (
                <>
                  <ChatMessageView role="user" content={pending.question} />
                  <ChatMessageView
                    role="assistant"
                    content={pending.answer}
                    citations={pending.citations}
                    lowConfidence={pending.lowConfidence}
                    streaming={streaming}
                    error={pending.error}
                  />
                </>
              )}
            </>
          )}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="border-t border-surface-border p-3 flex items-end gap-2"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            rows={2}
            maxLength={MAX_CHARS}
            placeholder="Ask about the code…"
            aria-label="Your question"
            className="flex-1 resize-none px-4 py-2.5 bg-surface-2 border border-surface-border text-white placeholder-slate-500 rounded-xl text-sm focus:outline-none focus:border-brand-500 transition-colors"
          />
          <button
            type="submit"
            disabled={streaming || !input.trim()}
            className="flex items-center justify-center w-12 h-12 shrink-0 bg-brand-600 hover:bg-brand-500 text-white rounded-xl text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            aria-label="Send"
          >
            {streaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </form>
      </section>
    </div>
  );
}
