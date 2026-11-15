"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, ExternalLink, GitFork, Globe, Loader2, Lock, MessageSquare, Star, FileText } from "lucide-react";
import { repositoriesApi } from "@/lib/api/repositories";
import { IndexStatusPanel, useIndexStatus } from "@/components/chat/index-status-panel";
import { RepoChat } from "@/components/chat/repo-chat";
import { cn, formatRelativeTime, getScoreColor } from "@/lib/utils";

type Tab = "chat" | "overview";

export default function RepositoryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<Tab>("chat");

  const { data: repo, isLoading, error } = useQuery({
    queryKey: ["repository", id],
    queryFn: () => repositoriesApi.get(id),
    enabled: !!id,
  });
  const { data: indexStatus } = useIndexStatus(id);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 text-brand-400 animate-spin" />
      </div>
    );
  }

  if (error || !repo) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-400">Repository not found.</p>
      </div>
    );
  }

  const summary = repo.analysis_summary;

  return (
    <div className="max-w-6xl space-y-5">
      <Link
        href="/repositories"
        className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Repositories
      </Link>

      {/* Repo info */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-xl font-bold text-white">{repo.full_name}</h2>
            {repo.is_private ? <Lock className="w-4 h-4 text-slate-500" /> : <Globe className="w-4 h-4 text-slate-500" />}
            {repo.language && (
              <span className="text-xs px-2 py-0.5 bg-surface-3 text-slate-400 rounded-full">{repo.language}</span>
            )}
          </div>
          {repo.description && <p className="text-slate-400 text-sm mt-1">{repo.description}</p>}
          <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
            <span className="flex items-center gap-1"><Star className="w-3 h-3" />{repo.stars}</span>
            <span className="flex items-center gap-1"><GitFork className="w-3 h-3" />{repo.forks}</span>
            {repo.last_analyzed_at && <span>Analysed {formatRelativeTime(repo.last_analyzed_at)}</span>}
            <a href={repo.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 hover:text-white">
              GitHub <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
        {summary?.overall_score != null && (
          <div className={`text-lg font-bold px-3 py-1.5 rounded-lg bg-surface-3 ${getScoreColor(summary.overall_score)}`}>
            {Math.round(summary.overall_score)}/100
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-surface-border" role="tablist">
        {([
          ["chat", "Chat", MessageSquare],
          ["overview", "Overview", FileText],
        ] as const).map(([key, label, Icon]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === key ? "border-brand-500 text-white" : "border-transparent text-slate-400 hover:text-white",
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {tab === "chat" ? (
        <div className="space-y-4">
          <IndexStatusPanel repoId={repo.id} />
          <RepoChat repoId={repo.id} indexed={!!indexStatus?.indexed_commit_sha} />
        </div>
      ) : (
        <div className="glass-card rounded-2xl p-5 space-y-4">
          {summary ? (
            <>
              <div className="prose prose-sm prose-invert max-w-none text-slate-300">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{summary.ai_summary}</ReactMarkdown>
              </div>
              {summary.review_id && (
                <Link href={`/history/${summary.review_id}`} className="inline-flex items-center gap-2 text-sm text-brand-400 hover:text-brand-300">
                  <FileText className="w-4 h-4" /> Open the full analysis report
                </Link>
              )}
            </>
          ) : (
            <p className="text-slate-400 text-sm">
              {repo.status === "analyzing" || repo.status === "pending"
                ? "Analysis is running…"
                : "No analysis yet. Run one from the Repositories page."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
