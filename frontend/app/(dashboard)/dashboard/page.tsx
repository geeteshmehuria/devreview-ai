"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Code2, GitBranch, Shield, TrendingUp, Clock, AlertTriangle, ArrowRight, Zap } from "lucide-react";
import Link from "next/link";
import { reviewsApi } from "@/lib/api/reviews";
import { repositoriesApi } from "@/lib/api/repositories";
import { useAuthStore } from "@/lib/stores/auth-store";
import { formatRelativeTime, getScoreColor, formatScore } from "@/lib/utils";
import { ScoreRing } from "@/components/shared/score-ring";
import { SkeletonCard } from "@/components/shared/skeleton";

const STAGGER = { container: { animate: { transition: { staggerChildren: 0.07 } } }, item: { initial: { opacity: 0, y: 16 }, animate: { opacity: 1, y: 0 } } };

export default function DashboardPage() {
  const { user } = useAuthStore();

  const { data: reviews, isLoading: reviewsLoading } = useQuery({
    queryKey: ["reviews", { page: 1, page_size: 5 }],
    queryFn: () => reviewsApi.list({ page: 1, page_size: 5 }),
  });

  const { data: repos, isLoading: reposLoading } = useQuery({
    queryKey: ["repositories"],
    queryFn: () => repositoriesApi.list(),
  });

  const recentReviews = reviews?.items || [];
  const repoList = repos || [];
  const avgScore = recentReviews.length
    ? Math.round(recentReviews.filter((r) => r.overall_score != null).reduce((a, r) => a + (r.overall_score || 0), 0) / recentReviews.filter((r) => r.overall_score != null).length)
    : null;

  const stats = [
    { label: "Repositories", value: repoList.length, icon: GitBranch, href: "/repositories", color: "text-brand-400" },
    { label: "Total Reviews", value: reviews?.total || 0, icon: Code2, href: "/history", color: "text-blue-400" },
    { label: "Avg Score", value: avgScore != null ? `${avgScore}` : "—", icon: TrendingUp, href: "/history", color: "text-emerald-400" },
    { label: "Issues Found", value: "—", icon: AlertTriangle, href: "/debt", color: "text-orange-400" },
  ];

  return (
    <motion.div
      variants={STAGGER.container}
      initial="initial"
      animate="animate"
      className="space-y-6 max-w-7xl"
    >
      {/* Welcome */}
      <motion.div variants={STAGGER.item}>
        <h2 className="text-2xl font-bold text-white">
          Good day, {user?.github_name?.split(" ")[0] || user?.github_login} 👋
        </h2>
        <p className="text-slate-400 mt-1">Here's what's happening with your code.</p>
      </motion.div>

      {/* Stats */}
      <motion.div variants={STAGGER.item} className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <Link key={stat.label} href={stat.href}>
            <div className="glass-card glass-hover rounded-2xl p-5 cursor-pointer">
              <div className="flex items-start justify-between mb-4">
                <p className="text-sm text-slate-400">{stat.label}</p>
                <stat.icon className={`w-5 h-5 ${stat.color}`} />
              </div>
              <p className={`text-3xl font-bold ${stat.color}`}>{stat.value}</p>
            </div>
          </Link>
        ))}
      </motion.div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Recent Reviews */}
        <motion.div variants={STAGGER.item} className="lg:col-span-2">
          <div className="glass-card rounded-2xl p-6">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-white font-semibold">Recent Reviews</h3>
              <Link href="/history" className="text-sm text-brand-400 hover:text-brand-300 flex items-center gap-1 transition-colors">
                View all <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {reviewsLoading ? (
              <div className="space-y-3">
                {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
              </div>
            ) : recentReviews.length === 0 ? (
              <EmptyState
                icon={Code2}
                title="No reviews yet"
                description="Start with a code snippet or connect a repository."
                action={{ href: "/review", label: "Start First Review" }}
              />
            ) : (
              <div className="space-y-3">
                {recentReviews.map((review) => (
                  <Link key={review.id} href={`/history/${review.id}`}>
                    <div className="flex items-center gap-4 p-4 rounded-xl bg-surface-2 hover:bg-surface-3 border border-surface-border hover:border-brand-600/30 transition-all cursor-pointer">
                      <ScoreRing score={review.overall_score || 0} size={44} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-white truncate">
                          {review.title || "Code Review"}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-xs text-slate-500 capitalize">{review.review_type.replace("_", " ")}</span>
                          {review.language && <span className="text-xs text-slate-600">· {review.language}</span>}
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className={`text-sm font-semibold ${getScoreColor(review.overall_score || 0)}`}>
                          {formatScore(review.overall_score)}/100
                        </p>
                        <p className="text-xs text-slate-500 mt-0.5">{formatRelativeTime(review.created_at)}</p>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </motion.div>

        {/* Quick actions */}
        <motion.div variants={STAGGER.item} className="space-y-4">
          <div className="glass-card rounded-2xl p-6">
            <h3 className="text-white font-semibold mb-4">Quick Actions</h3>
            <div className="space-y-2">
              {[
                { href: "/review", icon: Code2, label: "Review Code Snippet", desc: "Paste & analyse" },
                { href: "/pull-requests", icon: GitBranch, label: "Review Pull Request", desc: "Enter PR URL" },
                { href: "/repositories", icon: Shield, label: "Analyse Repository", desc: "Full scan" },
              ].map((action) => (
                <Link key={action.href} href={action.href}>
                  <div className="flex items-center gap-3 p-3 rounded-xl hover:bg-surface-3 border border-transparent hover:border-brand-600/20 transition-all cursor-pointer group">
                    <div className="w-9 h-9 rounded-lg bg-brand-700/30 flex items-center justify-center shrink-0 group-hover:bg-brand-700/50 transition-colors">
                      <action.icon className="w-4 h-4 text-brand-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white">{action.label}</p>
                      <p className="text-xs text-slate-500">{action.desc}</p>
                    </div>
                    <ArrowRight className="w-4 h-4 text-slate-600 ml-auto group-hover:text-brand-400 group-hover:translate-x-0.5 transition-all" />
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Repositories */}
          <div className="glass-card rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-white font-semibold">Repositories</h3>
              <Link href="/repositories" className="text-xs text-brand-400 hover:text-brand-300 transition-colors">
                Manage
              </Link>
            </div>
            {reposLoading ? (
              <div className="space-y-2">
                {[...Array(3)].map((_, i) => <SkeletonCard key={i} className="h-10" />)}
              </div>
            ) : repoList.length === 0 ? (
              <p className="text-sm text-slate-400">No repositories imported yet.</p>
            ) : (
              <div className="space-y-2">
                {repoList.slice(0, 4).map((repo) => (
                  <Link key={repo.id} href={`/repositories/${repo.id}`}>
                    <div className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-surface-3 transition-all cursor-pointer">
                      <GitBranch className="w-4 h-4 text-brand-400 shrink-0" />
                      <span className="text-sm text-slate-300 truncate">{repo.name}</span>
                      <span className={`ml-auto text-xs px-1.5 py-0.5 rounded-md ${
                        repo.status === "analyzed" ? "bg-emerald-500/10 text-emerald-400" :
                        repo.status === "analyzing" ? "bg-yellow-500/10 text-yellow-400" :
                        "bg-slate-500/10 text-slate-400"
                      }`}>
                        {repo.status}
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}

function EmptyState({ icon: Icon, title, description, action }: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  action?: { href: string; label: string };
}) {
  return (
    <div className="text-center py-10">
      <div className="w-12 h-12 rounded-xl bg-surface-3 flex items-center justify-center mx-auto mb-3">
        <Icon className="w-6 h-6 text-slate-500" />
      </div>
      <p className="text-sm font-medium text-white mb-1">{title}</p>
      <p className="text-sm text-slate-400 mb-4">{description}</p>
      {action && (
        <Link href={action.href} className="inline-flex items-center gap-2 px-4 py-2 bg-brand-700/30 hover:bg-brand-700/50 text-brand-400 rounded-lg text-sm font-medium transition-colors">
          <Zap className="w-4 h-4" />
          {action.label}
        </Link>
      )}
    </div>
  );
}
