"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Plus, Star, GitFork, Lock, Globe, Loader2, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { repositoriesApi } from "@/lib/api/repositories";
import { formatRelativeTime, getScoreColor } from "@/lib/utils";
import { SkeletonCard } from "@/components/shared/skeleton";
import type { Repository } from "@/types";

export default function RepositoriesPage() {
  const [repoUrl, setRepoUrl] = useState("");
  const [showForm, setShowForm] = useState(false);
  const qc = useQueryClient();

  const { data: repos = [], isLoading } = useQuery({
    queryKey: ["repositories"],
    queryFn: repositoriesApi.list,
  });

  const addMutation = useMutation({
    mutationFn: (url: string) => repositoriesApi.add(url),
    onSuccess: (repo) => {
      qc.invalidateQueries({ queryKey: ["repositories"] });
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
    onError: () => toast.error("Failed to remove repository"),
  });

  const analyzeMutation = useMutation({
    mutationFn: (id: string) => repositoriesApi.analyze(id, true),
    onSuccess: (repo) => {
      qc.invalidateQueries({ queryKey: ["repositories"] });
      toast.success(`Analysis triggered for ${repo.name}`);
    },
    onError: () => toast.error("Failed to trigger analysis"),
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
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Repositories</h2>
          <p className="text-slate-400 text-sm mt-1">Import and analyse your GitHub repositories.</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white rounded-lg text-sm font-medium transition-all hover:scale-105"
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
          className="glass-card rounded-2xl p-5"
        >
          <p className="text-sm font-medium text-white mb-3">GitHub Repository URL</p>
          <div className="flex gap-3">
            <input
              type="url"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repository"
              className="flex-1 px-4 py-2.5 bg-surface-2 border border-surface-border text-white placeholder-slate-500 rounded-xl text-sm focus:outline-none focus:border-brand-500 transition-colors"
            />
            <button
              type="submit"
              disabled={addMutation.isPending || !repoUrl}
              className="flex items-center gap-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-500 text-white rounded-xl text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-all"
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
        <div className="glass-card rounded-2xl p-12 text-center">
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
              onDelete={() => deleteMutation.mutate(repo.id)}
              isAnalyzing={analyzeMutation.isPending}
            />
          ))}
        </div>
      )}
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
      className="glass-card glass-hover rounded-2xl p-5"
    >
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 rounded-xl bg-brand-700/30 flex items-center justify-center shrink-0">
          <GitBranch className="w-5 h-5 text-brand-400" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link href={`/repositories/${repo.id}`} className="text-white font-semibold hover:text-brand-400 transition-colors">
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

        <div className="flex items-center gap-2 shrink-0">
          {score != null && (
            <div className={`text-sm font-bold px-2.5 py-1 rounded-lg bg-surface-3 ${getScoreColor(score)}`}>
              {Math.round(score)}/100
            </div>
          )}
          <button
            onClick={onAnalyze}
            disabled={isAnalyzing || repo.status === "analyzing"}
            className="p-2 rounded-lg text-slate-400 hover:text-brand-400 hover:bg-brand-700/20 transition-colors disabled:opacity-40"
            title="Re-analyse"
          >
            <RefreshCw className={`w-4 h-4 ${repo.status === "analyzing" ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={onDelete}
            className="p-2 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            title="Remove"
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
