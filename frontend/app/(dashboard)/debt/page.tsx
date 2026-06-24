"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Clock, TrendingDown, CheckCircle2, Filter } from "lucide-react";
import { useState } from "react";
import { reviewsApi } from "@/lib/api/reviews";

export default function DebtPage() {
  const [severityFilter, setSeverityFilter] = useState("all");

  const { isLoading } = useQuery({
    queryKey: ["reviews", { page: 1, page_size: 50 }],
    queryFn: () => reviewsApi.list({ page: 1, page_size: 50 }),
  });

  // For a real impl, we'd aggregate from all reviews. Here we show from recent.

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Technical Debt</h2>
        <p className="text-slate-400 text-sm mt-1">Track and prioritise technical debt across your codebase.</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Critical Items", value: "—", color: "text-red-400", icon: AlertTriangle },
          { label: "High Priority", value: "—", color: "text-orange-400", icon: TrendingDown },
          { label: "Est. Hours", value: "—", color: "text-yellow-400", icon: Clock },
          { label: "Resolved", value: "—", color: "text-emerald-400", icon: CheckCircle2 },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className="glass-card rounded-2xl p-5">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs text-slate-400">{label}</p>
              <Icon className={`w-4 h-4 ${color}`} />
            </div>
            <p className={`text-2xl font-bold ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Empty state pointing to review flow */}
      <div className="glass-card rounded-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold">Debt Items</h3>
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="px-3 py-1.5 bg-surface-2 border border-surface-border text-white text-sm rounded-lg focus:outline-none"
            >
              <option value="all">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-16 bg-surface-2 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <AlertTriangle className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-white font-medium mb-1">No debt items tracked yet</p>
            <p className="text-slate-400 text-sm max-w-sm mx-auto">
              Run a code review or repository analysis to automatically detect and track technical debt.
            </p>
          </div>
        )}
      </div>

      {/* How it works */}
      <div className="glass-card rounded-2xl p-6">
        <h3 className="text-white font-semibold mb-4">How Technical Debt is Tracked</h3>
        <div className="grid md:grid-cols-3 gap-4">
          {[
            { step: "1", title: "Run a Review", desc: "Analyse code, files, or full repositories." },
            { step: "2", title: "AI Detects Debt", desc: "The AI categorises debt by severity and estimates remediation hours." },
            { step: "3", title: "Track Progress", desc: "Mark items resolved and watch your debt decrease over time." },
          ].map(({ step, title, desc }) => (
            <div key={step} className="flex gap-3">
              <div className="w-7 h-7 rounded-full bg-brand-700/30 flex items-center justify-center text-brand-400 text-sm font-bold shrink-0">
                {step}
              </div>
              <div>
                <p className="text-sm font-medium text-white">{title}</p>
                <p className="text-sm text-slate-400 mt-0.5">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
