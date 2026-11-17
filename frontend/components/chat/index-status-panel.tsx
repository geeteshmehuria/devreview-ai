"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Database, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { repositoriesApi } from "@/lib/api/repositories";
import { formatRelativeTime } from "@/lib/utils";
import type { IndexState, IndexStatus } from "@/types";
import { RadarLoader } from "@/components/shared/radar-loader";

const BADGE: Record<IndexState, { label: string; className: string }> = {
  not_indexed: { label: "Not indexed", className: "bg-slate-500/10 text-slate-400 border-slate-500/30" },
  indexing: { label: "Indexing…", className: "bg-brand-500/10 text-brand-300 border-brand-500/30" },
  indexed: { label: "Indexed", className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" },
  failed: { label: "Failed", className: "bg-red-500/10 text-red-400 border-red-500/30" },
};

export function indexStatusKey(repoId: string) {
  return ["index-status", repoId];
}

/** Shared query so the chat can tell whether the repo is indexed. Polls only while indexing. */
export function useIndexStatus(repoId: string) {
  return useQuery({
    queryKey: indexStatusKey(repoId),
    queryFn: () => repositoriesApi.indexStatus(repoId),
    refetchInterval: (query) => (query.state.data?.index_status === "indexing" ? 3_000 : false),
  });
}

export function IndexStatusPanel({ repoId }: { repoId: string }) {
  const qc = useQueryClient();
  const { data: status, isLoading } = useIndexStatus(repoId);

  const indexMutation = useMutation({
    mutationFn: () => repositoriesApi.index(repoId),
    onSuccess: (s: IndexStatus) => {
      qc.setQueryData(indexStatusKey(repoId), s); // starts polling straight away
      toast.success("Indexing started. This can take a few minutes.");
    },
    onError: (e: Error) => toast.error(e.message || "Failed to start indexing"),
  });

  if (isLoading || !status) {
    return <div className="glass-card rounded-2xl p-5 h-[88px] animate-pulse" />;
  }

  const badge = BADGE[status.index_status] ?? BADGE.not_indexed;
  const indexing = status.index_status === "indexing";

  return (
    <div className="glass-card rounded-2xl p-4 sm:p-5 space-y-3">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="w-10 h-10 rounded-xl bg-brand-600/30 flex items-center justify-center shrink-0">
          <Database className="w-5 h-5 text-brand-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-white font-medium">Chat index</p>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${badge.className}`}>{badge.label}</span>
          </div>
          <div className="flex items-center gap-4 mt-1 text-xs text-slate-500 flex-wrap">
            <span>{status.chunk_count.toLocaleString()} chunks</span>
            {status.indexed_commit_sha && (
              <span className="font-mono" title={status.indexed_commit_sha}>
                @ {status.indexed_commit_sha.slice(0, 7)}
              </span>
            )}
            {status.indexed_at && <span>Indexed {formatRelativeTime(status.indexed_at)}</span>}
          </div>
        </div>
        <button
          onClick={() => indexMutation.mutate()}
          disabled={indexing || indexMutation.isPending}
          className="w-full sm:w-auto flex items-center justify-center gap-2 px-4 h-10 bg-brand-600 hover:bg-brand-500 text-white rounded-lg text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {indexing || indexMutation.isPending ? (
            <RadarLoader />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          {status.indexed_commit_sha ? "Re-index" : "Index repository"}
        </button>
      </div>

      {indexing && (
        <p className="text-xs text-slate-400">
          Reading files, chunking and embedding the code. Chat keeps using the previous index until this finishes.
        </p>
      )}
      {status.index_status === "failed" && status.index_error && (
        <p className="flex items-start gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{status.index_error}</span>
        </p>
      )}
    </div>
  );
}
