import { FileCode2, ShieldAlert } from "lucide-react";
import type { ChatCitation } from "@/types";

/** "app/main.py:L10-L42", "app/main.py:L7", or just the path when there are no lines. */
export function citationLabel(c: ChatCitation): string {
  const path = c.file_path ?? c.title ?? "source";
  if (c.start_line == null) return path;
  return c.end_line != null && c.end_line !== c.start_line
    ? `${path}:L${c.start_line}-L${c.end_line}`
    : `${path}:L${c.start_line}`;
}

export function CitationChip({ citation }: { citation: ChatCitation }) {
  const isFinding = citation.kind === "finding";
  const Icon = isFinding ? ShieldAlert : FileCode2;
  const label = citationLabel(citation);
  const title = isFinding && citation.title ? `Review finding: ${citation.title}` : label;
  const className =
    "inline-flex items-center gap-1.5 max-w-full px-2 py-1 rounded-md border text-xs font-mono transition-colors " +
    (isFinding
      ? "border-orange-500/30 bg-orange-500/10 text-orange-300 hover:bg-orange-500/20"
      : "border-surface-border bg-surface-2 text-slate-300 hover:border-brand-500 hover:text-white");

  const content = (
    <>
      <span className="text-slate-500">[{citation.n}]</span>
      <Icon className="w-3 h-3 shrink-0" aria-hidden />
      <span className="truncate">{label}</span>
    </>
  );

  return citation.url ? (
    <a href={citation.url} target="_blank" rel="noopener noreferrer" title={title} className={className}>
      {content}
    </a>
  ) : (
    <span title={title} className={className}>
      {content}
    </span>
  );
}
