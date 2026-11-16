import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, Bot, Loader2, SearchX, User } from "lucide-react";
import { CitationChip } from "@/components/chat/citation-chip";
import type { ChatCitation } from "@/types";

/** Must match NOT_FOUND in backend/app/rag/prompt.py. */
export const NOT_FOUND_PREFIX = "I couldn't find this in the repository";

export function ChatMessageView({
  role,
  content,
  citations = [],
  streaming = false,
  lowConfidence = false,
  error = null,
}: {
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[] | null;
  streaming?: boolean;
  lowConfidence?: boolean;
  error?: string | null;
}) {
  if (role === "user") {
    return (
      <div className="flex justify-end gap-3">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-brand-600/40 border border-brand-500/40 px-4 py-2.5 text-sm text-white whitespace-pre-wrap">
          {content}
        </div>
        <div className="w-8 h-8 rounded-lg bg-surface-3 flex items-center justify-center shrink-0">
          <User className="w-4 h-4 text-slate-400" />
        </div>
      </div>
    );
  }

  const notFound = content.trimStart().startsWith(NOT_FOUND_PREFIX);

  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-lg bg-brand-600/30 flex items-center justify-center shrink-0">
        <Bot className="w-4 h-4 text-brand-400" />
      </div>
      <div className="flex-1 min-w-0 space-y-2">
        {notFound ? (
          <p className="flex items-center gap-2 text-xs text-amber-300">
            <SearchX className="w-3.5 h-3.5" /> Not found in the indexed code
          </p>
        ) : (
          lowConfidence && (
            <p className="flex items-center gap-2 text-xs text-amber-300">
              <AlertTriangle className="w-3.5 h-3.5" /> Low confidence: the code found matched this question only weakly
            </p>
          )
        )}

        {content ? (
          <div
            className={`prose prose-sm prose-invert max-w-none text-slate-300 prose-pre:bg-surface-1 prose-pre:border prose-pre:border-surface-border ${
              notFound ? "rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3" : ""
            }`}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ children, href }) => (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        ) : (
          streaming && (
            <p className="flex items-center gap-2 text-sm text-slate-400">
              <Loader2 className="w-4 h-4 animate-spin" /> Searching the code…
            </p>
          )
        )}

        {streaming && content && <span className="inline-block w-2 h-4 bg-brand-400 animate-pulse align-middle" />}

        {citations && citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1" aria-label="Sources">
            {citations.map((c) => (
              <CitationChip key={c.n} citation={c} />
            ))}
          </div>
        )}

        {error && (
          <p className="flex items-start gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </p>
        )}
      </div>
    </div>
  );
}
