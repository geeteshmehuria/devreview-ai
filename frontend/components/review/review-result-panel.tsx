"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { X, Shield, Zap, Eye, Wrench, Layout, CheckCircle2, AlertTriangle, BarChart3 } from "lucide-react";
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer } from "recharts";
import type { Review, Finding } from "@/types";
import { ScoreRing } from "@/components/shared/score-ring";
import { cn, getSeverityColor, categoryLabel } from "@/lib/utils";

interface ReviewResultPanelProps {
  review: Review;
  onClear?: () => void;
}

const CATEGORY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  security: Shield,
  performance: Zap,
  readability: Eye,
  maintainability: Wrench,
  architecture: Layout,
  best_practices: CheckCircle2,
};

type Tab = "overview" | "security" | "performance" | "smells" | "debt";

export function ReviewResultPanel({ review, onClear }: ReviewResultPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "overview", label: "Overview" },
    { id: "security", label: "Security", count: review.security_findings.length },
    { id: "performance", label: "Performance", count: review.performance_findings.length },
    { id: "smells", label: "Code Smells", count: review.code_smells.length },
    { id: "debt", label: "Tech Debt", count: review.technical_debt.length },
  ];

  const radarData = review.category_scores.map((cs) => ({
    category: categoryLabel(cs.category),
    score: cs.score,
  }));

  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-surface-border bg-surface-1">
        <div className="flex items-center gap-4">
          <ScoreRing score={review.overall_score || 0} size={56} />
          <div>
            <p className="text-white font-semibold">{review.title || "Code Review"}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-slate-400">{review.language}</span>
              <span className="text-slate-600">·</span>
              <span className="text-xs text-slate-400 capitalize">{review.ai_provider}</span>
              <span className="text-slate-600">·</span>
              <span className={`text-xs font-medium ${review.risk_score && review.risk_score > 60 ? "text-red-400" : "text-emerald-400"}`}>
                Risk: {Math.round(review.risk_score || 0)}/100
              </span>
            </div>
          </div>
        </div>
        {onClear && (
          <button
            onClick={onClear}
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-surface-3 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-surface-border bg-surface-1 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors",
              activeTab === tab.id
                ? "text-white border-b-2 border-brand-400 -mb-px"
                : "text-slate-400 hover:text-white"
            )}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span className={cn(
                "px-1.5 py-0.5 rounded-full text-xs font-bold",
                tab.id === "security" && tab.count > 0 ? "bg-red-500/20 text-red-400" : "bg-surface-3 text-slate-400"
              )}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-6">
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* Category grid */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {review.category_scores.map((cs) => {
                const Icon = CATEGORY_ICONS[cs.category] || BarChart3;
                return (
                  <div key={cs.category} className="bg-surface-2 rounded-xl p-4 border border-surface-border">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Icon className="w-4 h-4 text-slate-400" />
                        <span className="text-xs text-slate-400">{categoryLabel(cs.category)}</span>
                      </div>
                      <span className={`text-sm font-bold ${cs.score >= 80 ? "text-emerald-400" : cs.score >= 60 ? "text-yellow-400" : "text-red-400"}`}>
                        {Math.round(cs.score)}
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-surface-3 rounded-full overflow-hidden">
                      <motion.div
                        className={`h-full rounded-full ${cs.score >= 80 ? "bg-emerald-500" : cs.score >= 60 ? "bg-yellow-500" : "bg-red-500"}`}
                        initial={{ width: 0 }}
                        animate={{ width: `${cs.score}%` }}
                        transition={{ duration: 1, ease: "easeOut" }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Radar chart + Summary */}
            <div className="grid md:grid-cols-2 gap-6">
              {radarData.length > 0 && (
                <div className="bg-surface-2 rounded-xl p-4 border border-surface-border">
                  <p className="text-sm text-slate-400 mb-3">Score Radar</p>
                  <ResponsiveContainer width="100%" height={200}>
                    <RadarChart data={radarData}>
                      <PolarGrid stroke="rgba(255,255,255,0.06)" />
                      <PolarAngleAxis dataKey="category" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                      <Radar dataKey="score" fill="rgba(82,183,136,0.2)" stroke="#52b788" strokeWidth={2} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              )}

              <div className="bg-surface-2 rounded-xl p-4 border border-surface-border overflow-auto">
                <p className="text-sm text-slate-400 mb-3">AI Summary</p>
                <div className="prose prose-sm prose-invert max-w-none text-slate-300">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {review.ai_summary || "No summary available."}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "security" && (
          <FindingsList findings={review.security_findings} emptyLabel="No security issues found" />
        )}

        {activeTab === "performance" && (
          <FindingsList findings={review.performance_findings} emptyLabel="No performance issues found" />
        )}

        {activeTab === "smells" && (
          <FindingsList findings={review.code_smells} emptyLabel="No code smells detected" />
        )}

        {activeTab === "debt" && (
          <FindingsList findings={review.technical_debt} emptyLabel="No technical debt items found" />
        )}
      </div>
    </div>
  );
}

function FindingsList({ findings, emptyLabel }: { findings: Finding[]; emptyLabel: string }) {
  if (findings.length === 0) {
    return (
      <div className="text-center py-12">
        <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-3" />
        <p className="text-white font-medium">{emptyLabel}</p>
      </div>
    );
  }

  const sorted = [...findings].sort((a, b) => {
    const order = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    return (order[a.severity as keyof typeof order] ?? 5) - (order[b.severity as keyof typeof order] ?? 5);
  });

  return (
    <div className="space-y-3">
      {sorted.map((finding) => (
        <motion.div
          key={finding.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="border border-surface-border rounded-xl p-4 bg-surface-2"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium capitalize", getSeverityColor(finding.severity))}>
                  {finding.severity}
                </span>
                <span className="text-sm font-medium text-white">{finding.title}</span>
              </div>
              <p className="text-sm text-slate-400 mt-1">{finding.description}</p>
              {finding.file_path && (
                <p className="text-xs text-slate-500 mt-1 font-mono">
                  {finding.file_path}{finding.line_number ? `:${finding.line_number}` : ""}
                </p>
              )}
              {finding.code_snippet && (
                <pre className="mt-2 p-3 bg-surface-0 rounded-lg text-xs text-slate-300 overflow-x-auto font-mono">
                  {finding.code_snippet}
                </pre>
              )}
              {finding.recommendation && (
                <div className="mt-2 p-3 bg-brand-700/10 border border-brand-600/20 rounded-lg">
                  <p className="text-xs text-brand-300">
                    <span className="font-semibold">Fix: </span>{finding.recommendation}
                  </p>
                </div>
              )}
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
