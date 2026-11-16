"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Plus, Star, GitFork, Lock, Globe, Loader2, RefreshCw, Trash2, Search, Check, MessageSquare } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { repositoriesApi } from "@/lib/api/repositories";
import { formatRelativeTime, getScoreColor } from "@/lib/utils";
import { SkeletonCard } from "@/components/shared/skeleton";
import type { GitHubRepo, Repository } from "@/types";

const IN_PROGRESS: Repository["status"][] = ["pending", "analyzing"];

export default function RepositoriesPage() {
  const [repoUrl, setRepoUrl] = useState("");
  const [showForm, setShowForm] = useState(false);
  const qc = useQueryClient();

  const { data: repos = [], isLoading } = useQuery({
    queryKey: ["repositories"],
    queryFn: repositoriesApi.list,
    // Poll while any analysis is running so status and score update without a reload.
    refetchInterval: (query) =>
      query.state.data?.some((r) => IN_PROGRESS.includes(r.status)) ? 5_000 : false,
  });

  // Show the analysis as running immediately; polling then tracks the real status.
  const markAnalyzing = (id: string) =>
    qc.setQueryData<Repository[]>(["repositories"], (old) =>
      old?.map((r) => (r.id === id ? { ...r, status: "analyzing" } : r))
    );

  const addMutation = useMutation({
    mutationFn: (url: string) => repositoriesApi.add(url),
    onSuccess: async (repo) => {
      await qc.invalidateQueries({ queryKey: ["repositories"] });
      markAnalyzing(repo.id);
      toast.success(`${repo.name} imported. Analysis starting…`);
      setRepoUrl("");
      setShowForm(false);
    },
    onError: (e: Error) => toast.error(e.message || "Failed to import repository"),
  });

  const deleteMutation = useMutation({
    mutationFn: repositoriesApi.delete,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["repositories"] });
      toast.success("Repository removed");
    },
    onError: (e: Error) => toast.error(e.message || "Failed to remove repository"),
  });

  const analyzeMutation = useMutation({
    mutationFn: (id: string) => repositoriesApi.analyze(id, true),
    onSuccess: (repo) => {
      markAnalyzing(repo.id);
      toast.success(`Analysis triggered for ${repo.name}`);
    },
    onError: (e: Error) => toast.error(e.message || "Failed to trigger analysis"),
  });

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.match(/https:\/\/github\.com\/.+\/.+/)) {
      toast.error("Enter a valid GitHub repository URL");
      return;
    }
    addMutation.mutate(repoUrl);
  };

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight">Repositories</h2>
          <p className="text-slate-400 text-sm mt-1">Import and analyse your GitHub repositories.</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="w-full sm:w-auto flex items-center justify-center gap-2 px-4 h-11 sm:h-10 bg-brand-600 hover:bg-brand-500 text-white rounded-lg text-sm font-semibold transition-colors"
        >
          <Plus className="w-4 h-4" />
          Import Repository
        </button>
      </div>

      {/* Import form */}
      {showForm && (
        <motion.form
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          onSubmit={handleAdd}
          className="glass-card rounded-2xl p-4 sm:p-5"
        >
          <GitHubRepoPicker
            imported={new Set(repos.map((r) => r.full_name.toLowerCase()))}
            onPick={(repo) => addMutation.mutate(repo.url)}
            pendingUrl={addMutation.isPending ? addMutation.variables : undefined}
          />

          <p className="text-sm font-medium text-white mt-5 mb-3">Or paste a GitHub repository URL</p>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="url"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repository"
              className="flex-1 min-w-0 px-4 h-11 bg-surface-2 border border-surface-border text-white placeholder-slate-500 rounded-xl text-sm focus:outline-none focus:border-brand-500 transition-colors"
            />
            <button
              type="submit"
              disabled={addMutation.isPending || !repoUrl}
              className="flex items-center justify-center gap-2 px-5 h-11 bg-brand-600 hover:bg-brand-500 text-white rounded-xl text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {addMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Import
            </button>
          </div>
        </motion.form>
      )}

      {/* Repository list */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : repos.length === 0 ? (
        <div className="glass-card rounded-2xl p-8 sm:p-12 text-center">
          <GitBranch className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-white font-medium mb-1">No repositories yet</p>
          <p className="text-slate-400 text-sm">Import a GitHub repository to get started.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {repos.map((repo) => (
            <RepoCard
              key={repo.id}
              repo={repo}
              onAnalyze={() => analyzeMutation.mutate(repo.id)}
              onDelete={() => {
                if (confirm(`Remove ${repo.full_name} and its analysis history?`)) deleteMutation.mutate(repo.id);
              }}
              isAnalyzing={analyzeMutation.isPending && analyzeMutation.variables === repo.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Searchable list of the user's GitHub repos; clicking one imports it. */
function GitHubRepoPicker({ imported, onPick, pendingUrl }: {
  imported: Set<string>;
  onPick: (repo: GitHubRepo) => void;
  pendingUrl?: string;
}) {
  const [search, setSearch] = useState("");
  const { data: ghRepos = [], isLoading, isError, error, refetch } = useQuery({
    queryKey: ["github-repos"],
    queryFn: repositoriesApi.listGitHub,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const q = search.trim().toLowerCase();
  const filtered = q
    ? ghRepos.filter((r) =>
        [r.full_name, r.description, r.language].some((s) => s?.toLowerCase().includes(q))
      )
    : ghRepos;

  return (
    <div>
      <p className="text-sm font-medium text-white mb-3">Your GitHub repositories</p>
      <div className="relative mb-2">
        <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          // Enter here would submit the surrounding URL form.
          onKeyDown={(e) => e.key === "Enter" && e.preventDefault()}
          placeholder="Search your repositories…"
          aria-label="Search your GitHub repositories"
          className="w-full pl-9 pr-4 py-2.5 bg-surface-2 border border-surface-border text-white placeholder-slate-500 rounded-xl text-sm focus:outline-none focus:border-brand-500 transition-colors"
        />
      </div>

      <div className="max-h-72 overflow-y-auto rounded-xl border border-surface-border divide-y divide-surface-border">
        {isLoading ? (
          [...Array(4)].map((_, i) => <div key={i} className="h-12 animate-pulse bg-surface-2" />)
        ) : isError ? (
          <div className="p-4 text-sm text-red-400 flex items-center justify-between gap-3">
            <span>{(error as Error).message || "Couldn't load your GitHub repositories"}</span>
            <button
              type="button"
              onClick={() => refetch()}
              className="text-slate-300 hover:text-white underline shrink-0"
            >
              Retry
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <p className="p-4 text-sm text-slate-400">
            {q ? "No repositories match your search." : "No repositories found on your GitHub account."}
          </p>
        ) : (
          filtered.map((repo) => {
            const isImported = imported.has(repo.full_name.toLowerCase());
            const isPending = pendingUrl === repo.url;
            return (
              <button
                key={repo.full_name}
                type="button"
                onClick={() => onPick(repo)}
                disabled={isImported || !!pendingUrl}
                className="w-full flex items-center gap-3 px-4 py-3 min-h-14 text-left hover:bg-surface-2 transition-colors disabled:cursor-not-allowed disabled:hover:bg-transparent"
              >
                {repo.is_private ? (
                  <Lock className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                ) : (
                  <Globe className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className={`text-sm truncate ${isImported ? "text-slate-500" : "text-white"}`}>{repo.full_name}</p>
                  {repo.description && <p className="text-xs text-slate-500 truncate">{repo.description}</p>}
                </div>
                {repo.language && (
                  <span className="hidden sm:inline text-xs px-2 py-0.5 bg-surface-3 text-slate-400 rounded-full shrink-0">{repo.language}</span>
                )}
                <span className="hidden sm:flex items-center gap-1 text-xs text-slate-500 shrink-0">
                  <Star className="w-3 h-3" />{repo.stars}
                </span>
                {isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin text-brand-400 shrink-0" />
                ) : isImported ? (
                  <span className="flex items-center gap-1 text-xs text-emerald-400 shrink-0">
                    <Check className="w-3 h-3" />Imported
                  </span>
                ) : null}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

function RepoCard({ repo, onAnalyze, onDelete, isAnalyzing }: {
  repo: Repository;
  onAnalyze: () => void;
  onDelete: () => void;
  isAnalyzing: boolean;
}) {
  const score = repo.analysis_summary?.overall_score;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card glass-hover rounded-2xl p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        <div className="w-10 h-10 rounded-xl bg-brand-600/30 flex items-center justify-center shrink-0">
          <GitBranch className="w-5 h-5 text-brand-400" />
        </div>

        <div className="flex-1 min-w-[12rem]">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              href={repo.analysis_summary?.review_id ? `/history/${repo.analysis_summary.review_id}` : repo.url}
              target={repo.analysis_summary?.review_id ? undefined : "_blank"}
              rel="noopener noreferrer"
              className="text-white font-semibold hover:text-brand-400 transition-colors break-all"
            >
              {repo.full_name}
            </Link>
            {repo.is_private ? (
              <Lock className="w-3.5 h-3.5 text-slate-500" />
            ) : (
              <Globe className="w-3.5 h-3.5 text-slate-500" />
            )}
            {repo.language && (
              <span className="text-xs px-2 py-0.5 bg-surface-3 text-slate-400 rounded-full">{repo.language}</span>
            )}
            <StatusBadge status={repo.status} />
          </div>

          {repo.description && (
            <p className="text-sm text-slate-400 mt-1 line-clamp-1">{repo.description}</p>
          )}

          <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
            <span className="flex items-center gap-1"><Star className="w-3 h-3" />{repo.stars}</span>
            <span className="flex items-center gap-1"><GitFork className="w-3 h-3" />{repo.forks}</span>
            {repo.last_analyzed_at && <span>Analysed {formatRelativeTime(repo.last_analyzed_at)}</span>}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 ml-auto">
          {score != null && (
            <div className={`text-sm font-bold px-2.5 py-1 rounded-lg bg-surface-3 ${getScoreColor(score)}`}>
              {Math.round(score)}/100
            </div>
          )}
          <Link
            href={`/repositories/${repo.id}`}
            className="flex items-center gap-1.5 px-3 h-10 rounded-lg text-sm text-slate-300 hover:text-white bg-surface-3 hover:bg-brand-600/30 transition-colors"
            aria-label={`Chat with ${repo.full_name}`}
          >
            <MessageSquare className="w-4 h-4" />
            Chat
          </Link>
          <button
            onClick={onAnalyze}
            disabled={isAnalyzing || repo.status === "analyzing"}
            className="w-10 h-10 flex items-center justify-center rounded-lg text-slate-400 hover:text-brand-400 hover:bg-brand-600/20 transition-colors disabled:opacity-40"
            title="Re-analyse"
            aria-label={`Re-analyse ${repo.full_name}`}
          >
            <RefreshCw className={`w-4 h-4 ${repo.status === "analyzing" ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={onDelete}
            className="w-10 h-10 flex items-center justify-center rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            title="Remove"
            aria-label={`Remove ${repo.full_name}`}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </motion.div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    analyzed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    analyzing: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
    pending: "bg-slate-500/10 text-slate-400 border-slate-500/20",
    failed: "bg-red-500/10 text-red-400 border-red-500/20",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${map[status] || map.pending}`}>
      {status}
    </span>
  );
}
