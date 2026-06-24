"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { History, Filter, Code2, GitBranch, GitPullRequest, FileText } from "lucide-react";
import Link from "next/link";
import { reviewsApi } from "@/lib/api/reviews";
import { formatRelativeTime, getScoreColor } from "@/lib/utils";
import { ScoreRing } from "@/components/shared/score-ring";
import { SkeletonCard } from "@/components/shared/skeleton";

const TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  code_snippet: Code2,
  file_upload: FileText,
  repository: GitBranch,
  pull_request: GitPullRequest,
};

const FILTER_OPTIONS = [
  { value: "", label: "All Types" },
  { value: "code_snippet", label: "Code Snippets" },
  { value: "file_upload", label: "File Uploads" },
  { value: "repository", label: "Repositories" },
  { value: "pull_request", label: "Pull Requests" },
];

export default function HistoryPage() {
  const [page, setPage] = useState(1);
  const [typeFilter, setTypeFilter] = useState("");
  const PAGE_SIZE = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["reviews", { page, page_size: PAGE_SIZE, review_type: typeFilter || undefined }],
    queryFn: () => reviewsApi.list({ page, page_size: PAGE_SIZE, review_type: typeFilter || undefined }),
  });

  const reviews = data?.items || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Review History</h2>
          <p className="text-slate-400 text-sm mt-1">All {total} reviews — nothing is ever lost.</p>
        </div>

        {/* Filter */}
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400" />
          <select
            value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
            className="px-3 py-1.5 bg-surface-2 border border-surface-border text-white text-sm rounded-lg focus:outline-none focus:border-brand-500"
          >
            {FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(8)].map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : reviews.length === 0 ? (
        <div className="glass-card rounded-2xl p-12 text-center">
          <History className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-white font-medium mb-1">No reviews found</p>
          <p className="text-slate-400 text-sm">
            {typeFilter ? "Try a different filter." : "Start your first review from the Code Review page."}
          </p>
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {reviews.map((review, i) => {
              const Icon = TYPE_ICONS[review.review_type] || Code2;
              return (
                <motion.div
                  key={review.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                >
                  <Link href={`/history/${review.id}`}>
                    <div className="glass-card glass-hover rounded-xl p-4 cursor-pointer">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded-xl bg-surface-3 flex items-center justify-center shrink-0">
                          <Icon className="w-5 h-5 text-slate-400" />
                        </div>

                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-white truncate">
                            {review.title || "Code Review"}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-slate-500 capitalize">
                              {review.review_type.replace("_", " ")}
                            </span>
                            {review.language && (
                              <span className="text-xs text-slate-600">· {review.language}</span>
                            )}
                            <span className="text-xs text-slate-600">· {review.ai_provider}</span>
                          </div>
                        </div>

                        <div className="flex items-center gap-4 shrink-0">
                          {review.overall_score != null && (
                            <ScoreRing score={review.overall_score} size={40} />
                          )}
                          <div className="text-right hidden sm:block">
                            <p className={`text-sm font-semibold ${getScoreColor(review.overall_score || 0)}`}>
                              {review.overall_score != null ? `${Math.round(review.overall_score)}/100` : "—"}
                            </p>
                            <p className="text-xs text-slate-500">{formatRelativeTime(review.created_at)}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </Link>
                </motion.div>
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-4">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="px-4 py-2 bg-surface-2 text-slate-300 rounded-lg text-sm disabled:opacity-40 hover:bg-surface-3 transition-colors"
              >
                Previous
              </button>
              <span className="text-slate-400 text-sm">Page {page} of {totalPages}</span>
              <button
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page === totalPages}
                className="px-4 py-2 bg-surface-2 text-slate-300 rounded-lg text-sm disabled:opacity-40 hover:bg-surface-3 transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
