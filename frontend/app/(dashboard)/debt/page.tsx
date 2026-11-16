"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Clock, TrendingDown, ListChecks, Filter } from "lucide-react";
import { reviewsApi } from "@/lib/api/reviews";
import { bySeverity, cn, getSeverityColor } from "@/lib/utils";

const SEVERITIES = ["critical", "high", "medium", "low"] as const;

export default function DebtPage() {
  const [severityFilter, setSeverityFilter] = useState("all");

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["debt"],
    queryFn: reviewsApi.debt,
  });

  const visible = items
    .filter((d) => severityFilter === "all" || d.severity === severityFilter)
    .sort(bySeverity);
  const totalHours = items.reduce((sum, d) => sum + (d.estimated_hours ?? 0), 0);

  const summary = [
    { label: "Critical Items", value: items.filter((d) => d.severity === "critical").length, color: "text-red-400", icon: AlertTriangle },
    { label: "High Priority", value: items.filter((d) => d.severity === "high").length, color: "text-orange-400", icon: TrendingDown },
    { label: "Est. Hours", value: Math.round(totalHours), color: "text-yellow-400", icon: Clock },
    { label: "Total Items", value: items.length, color: "text-emerald-400", icon: ListChecks },
  ];

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Technical Debt</h2>
        <p className="text-slate-400 text-sm mt-1">Debt items detected across all of your reviews and repository analyses.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        {summary.map(({ label, value, color, icon: Icon }) => (
          <div key={label} className="glass-card rounded-2xl p-4 sm:p-5">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs text-slate-400">{label}</p>
              <Icon className={`w-4 h-4 ${color}`} />
            </div>
            <p className={`text-2xl font-bold ${color}`}>{isLoading ? "—" : value}</p>
          </div>
        ))}
      </div>

      <div className="glass-card rounded-2xl p-4 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h3 className="text-white font-semibold">Debt Items</h3>
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              aria-label="Filter by severity"
              className="px-3 h-10 bg-surface-2 border border-surface-border text-white text-sm rounded-lg focus:outline-none focus:border-brand-400"
            >
              <option value="all">All Severities</option>
              {SEVERITIES.map((s) => (
                <option key={s} value={s} className="capitalize">{s[0].toUpperCase() + s.slice(1)}</option>
              ))}
            </select>
          </div>
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-16 bg-surface-2 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <div className="text-center py-12">
            <AlertTriangle className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-white font-medium mb-1">
              {items.length === 0 ? "No debt items tracked yet" : "No items with this severity"}
            </p>
            <p className="text-slate-400 text-sm max-w-sm mx-auto">
              {items.length === 0
                ? "Run a code review or repository analysis to automatically detect technical debt."
                : "Try a different filter."}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {visible.map((d) => (
              <div key={d.id} className="border border-surface-border rounded-xl p-4 bg-surface-2">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium capitalize", getSeverityColor(d.severity))}>
                    {d.severity}
                  </span>
                  <span className="text-sm font-medium text-white">{d.title}</span>
                  <span className="text-xs text-slate-500 capitalize">· {d.category}</span>
                  {d.estimated_hours != null && (
                    <span className="text-xs text-slate-500 ml-auto">~{d.estimated_hours}h</span>
                  )}
                </div>
                <p className="text-sm text-slate-400">{d.description}</p>
                {d.recommendation && (
                  <p className="text-xs text-brand-300 mt-2"><span className="font-semibold">Fix: </span>{d.recommendation}</p>
                )}
                <Link href={`/history/${d.review_id}`} className="text-xs text-brand-400 hover:text-brand-300 mt-2 inline-block py-1 break-all">
                  From: {d.review_title || "review"}
                  {d.file_path ? ` · ${d.file_path}` : ""}
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
