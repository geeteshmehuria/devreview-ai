"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation } from "@tanstack/react-query";
import { GitPullRequest, Loader2, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { reviewsApi } from "@/lib/api/reviews";
import type { PRReviewResult } from "@/types";
import { ScoreRing } from "@/components/shared/score-ring";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getScoreColor, categoryLabel } from "@/lib/utils";

export default function PullRequestsPage() {
  const [prUrl, setPrUrl] = useState("");
  const [result, setResult] = useState<PRReviewResult | null>(null);

  const mutation = useMutation({
    mutationFn: (url: string) => reviewsApi.reviewPR({ pr_url: url }),
    onSuccess: (data) => {
      setResult(data);
      toast.success("PR review complete!");
    },
    onError: (e: Error) => toast.error(e.message || "PR review failed"),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prUrl.match(/https:\/\/github\.com\/.+\/pull\/\d+/)) {
      toast.error("Enter a valid GitHub PR URL (e.g. https://github.com/owner/repo/pull/123)");
      return;
    }
    mutation.mutate(prUrl);
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Pull Request Review</h2>
        <p className="text-slate-400 text-sm mt-1">
          Enter a GitHub PR URL to get an AI review of the diff.
        </p>
      </div>

      {/* Input */}
      <div className="glass-card rounded-2xl p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm text-slate-400 mb-2 block">GitHub Pull Request URL</label>
            <div className="flex gap-3">
              <input
                type="url"
                value={prUrl}
                onChange={(e) => setPrUrl(e.target.value)}
                placeholder="https://github.com/owner/repo/pull/123"
                className="flex-1 px-4 py-3 bg-surface-2 border border-surface-border text-white placeholder-slate-500 rounded-xl text-sm focus:outline-none focus:border-brand-500 transition-colors"
              />
              <button
                type="submit"
                disabled={mutation.isPending || !prUrl}
                className="flex items-center gap-2 px-6 py-3 bg-brand-600 hover:bg-brand-500 text-white rounded-xl text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:scale-105"
              >
                {mutation.isPending ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Analysing…</>
                ) : (
                  <><GitPullRequest className="w-4 h-4" /> Review PR</>
                )}
              </button>
            </div>
          </div>

          <p className="text-xs text-slate-500">
            The repository must be accessible with your GitHub token. Private repos are supported.
          </p>
        </form>
      </div>

      {/* Result */}
      <AnimatePresence>
        {result && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-4"
          >
            {/* PR header */}
            <div className="glass-card rounded-2xl p-6">
              <div className="flex items-start gap-5">
                <ScoreRing score={result.overall_score} size={80} />
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-slate-500">PR #{result.pr_number}</span>
                    <a href={prUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-xs text-brand-400 hover:text-brand-300">
                      <ExternalLink className="w-3 h-3" /> View on GitHub
                    </a>
                  </div>
                  <h3 className="text-white font-semibold text-lg mt-1">{result.pr_title}</h3>
                  <div className="flex items-center gap-4 mt-2">
                    <span className="text-sm">
                      <span className="text-slate-400">Overall: </span>
                      <span className={`font-bold ${getScoreColor(result.overall_score)}`}>
                        {Math.round(result.overall_score)}/100
                      </span>
                    </span>
                    <span className="text-sm">
                      <span className="text-slate-400">Risk: </span>
                      <span className={`font-bold ${result.risk_score > 60 ? "text-red-400" : "text-emerald-400"}`}>
                        {Math.round(result.risk_score)}/100
                      </span>
                    </span>
                    <span className="text-sm text-slate-400">via {result.provider}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Categories */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {result.category_scores.map((cs) => (
                <div key={cs.category} className="glass-card rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-slate-400">{categoryLabel(cs.category)}</span>
                    <span className={`text-sm font-bold ${getScoreColor(cs.score)}`}>{Math.round(cs.score)}</span>
                  </div>
                  <div className="w-full h-1.5 bg-surface-3 rounded-full overflow-hidden">
                    <motion.div
                      className={`h-full rounded-full ${cs.score >= 80 ? "bg-emerald-500" : cs.score >= 60 ? "bg-yellow-500" : "bg-red-500"}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${cs.score}%` }}
                      transition={{ duration: 1 }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* AI Summary */}
            <div className="glass-card rounded-2xl p-6">
              <h3 className="text-white font-semibold mb-3">AI Review Summary</h3>
              <div className="prose prose-sm prose-invert max-w-none text-slate-300">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.ai_summary}</ReactMarkdown>
              </div>
            </div>

            {/* Findings count */}
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Security Issues", count: result.security_findings, color: "text-red-400" },
                { label: "Performance Issues", count: result.performance_findings, color: "text-orange-400" },
              ].map(({ label, count, color }) => (
                <div key={label} className="glass-card rounded-xl p-4 flex items-center justify-between">
                  <span className="text-sm text-slate-400">{label}</span>
                  <span className={`text-2xl font-bold ${color}`}>{count}</span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
