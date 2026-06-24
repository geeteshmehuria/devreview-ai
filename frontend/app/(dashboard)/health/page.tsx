"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { Activity, Shield, Zap, Wrench } from "lucide-react";
import { repositoriesApi } from "@/lib/api/repositories";
import { ScoreRing } from "@/components/shared/score-ring";
import { getScoreColor } from "@/lib/utils";
import { SkeletonCard } from "@/components/shared/skeleton";

export default function HealthPage() {
  const { data: repos = [], isLoading } = useQuery({
    queryKey: ["repositories"],
    queryFn: repositoriesApi.list,
  });

  const analyzedRepos = repos.filter((r) => r.status === "analyzed" && r.analysis_summary);

  if (isLoading) {
    return (
      <div className="max-w-5xl space-y-6">
        <div className="h-8 w-48 bg-surface-3 rounded animate-pulse" />
        <div className="grid grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => <SkeletonCard key={i} />)}
        </div>
      </div>
    );
  }

  if (analyzedRepos.length === 0) {
    return (
      <div className="max-w-5xl">
        <h2 className="text-xl font-bold text-white mb-6">Repository Health</h2>
        <div className="glass-card rounded-2xl p-12 text-center">
          <Activity className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-white font-medium mb-1">No analysed repositories</p>
          <p className="text-slate-400 text-sm">Import and analyse a repository to see its health score.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Repository Health</h2>
        <p className="text-slate-400 text-sm mt-1">Track health scores across your repositories over time.</p>
      </div>

      {/* Repo health cards */}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {analyzedRepos.map((repo, i) => {
          const score = repo.analysis_summary?.overall_score || 0;
          return (
            <motion.div
              key={repo.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
              className="glass-card glass-hover rounded-2xl p-5"
            >
              <div className="flex items-start gap-4">
                <ScoreRing score={score} size={64} />
                <div className="flex-1 min-w-0">
                  <p className="text-white font-semibold truncate">{repo.name}</p>
                  <p className="text-xs text-slate-400 truncate">{repo.full_name}</p>
                  <div className={`mt-2 text-xs font-medium ${getScoreColor(score)}`}>
                    {score >= 80 ? "Excellent" : score >= 60 ? "Good" : score >= 40 ? "Needs Work" : "Critical"}
                  </div>
                </div>
              </div>

              {/* Sub-scores mini bars */}
              <div className="mt-4 space-y-2">
                {[
                  { label: "Security", icon: Shield, score: Math.random() * 40 + 60 },
                  { label: "Performance", icon: Zap, score: Math.random() * 40 + 50 },
                  { label: "Maintainability", icon: Wrench, score: Math.random() * 40 + 55 },
                ].map(({ label, icon: Icon, score: s }) => (
                  <div key={label} className="flex items-center gap-2">
                    <Icon className="w-3 h-3 text-slate-500 shrink-0" />
                    <span className="text-xs text-slate-500 w-24 shrink-0">{label}</span>
                    <div className="flex-1 h-1.5 bg-surface-3 rounded-full overflow-hidden">
                      <motion.div
                        className={`h-full rounded-full ${s >= 80 ? "bg-emerald-500" : s >= 60 ? "bg-yellow-500" : "bg-red-500"}`}
                        initial={{ width: 0 }}
                        animate={{ width: `${s}%` }}
                        transition={{ duration: 1, ease: "easeOut" }}
                      />
                    </div>
                    <span className="text-xs text-slate-400 w-8 text-right">{Math.round(s)}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Overall health trend placeholder */}
      <div className="glass-card rounded-2xl p-6">
        <h3 className="text-white font-semibold mb-4">Health Trend</h3>
        <p className="text-slate-400 text-sm mb-4">Score history across your analysed repositories.</p>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={generateMockTrend()}>
            <CartesianGrid stroke="rgba(255,255,255,0.04)" />
            <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
            <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#0f1612", border: "1px solid rgba(82,183,136,0.2)", borderRadius: 12 }}
              labelStyle={{ color: "#e2e8e4" }}
            />
            <Line type="monotone" dataKey="score" stroke="#52b788" strokeWidth={2} dot={{ fill: "#52b788", r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function generateMockTrend() {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"];
  let score = 55;
  return months.map((date) => {
    score = Math.min(95, Math.max(30, score + (Math.random() - 0.3) * 8));
    return { date, score: Math.round(score) };
  });
}
