"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  GitBranch,
  Code2,
  GitPullRequest,
  History,
  Activity,
  AlertTriangle,
  Settings,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/stores/auth-store";
import Image from "next/image";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/repositories", label: "Repositories", icon: GitBranch },
  { href: "/review", label: "Code Review", icon: Code2 },
  { href: "/pull-requests", label: "Pull Requests", icon: GitPullRequest },
  { href: "/history", label: "Review History", icon: History },
  { href: "/health", label: "Repo Health", icon: Activity },
  { href: "/debt", label: "Technical Debt", icon: AlertTriangle },
];

const bottomItems = [
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();

  const isActive = (href: string) => {
    if (href === "/dashboard") return pathname === href;
    return pathname.startsWith(href);
  };

  return (
    <aside className="w-64 min-h-screen glass border-r border-surface-border flex flex-col shrink-0">
      {/* Logo */}
      <div className="h-16 flex items-center gap-2.5 px-6 border-b border-surface-border">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shrink-0">
          <Code2 className="w-4 h-4 text-white" />
        </div>
        <span className="font-semibold text-white">DevReview AI</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-3 space-y-1">
        {navItems.map((item) => {
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all relative group",
                active
                  ? "text-white bg-brand-700/40 border border-brand-600/30"
                  : "text-slate-400 hover:text-white hover:bg-surface-3"
              )}
            >
              {active && (
                <motion.div
                  layoutId="sidebar-indicator"
                  className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-brand-400 rounded-full -ml-3"
                />
              )}
              <item.icon className={cn("w-4 h-4 shrink-0", active ? "text-brand-400" : "text-slate-500 group-hover:text-slate-300")} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Bottom */}
      <div className="px-3 pb-4 space-y-1 border-t border-surface-border pt-4">
        {bottomItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-slate-400 hover:text-white hover:bg-surface-3 transition-all"
          >
            <item.icon className="w-4 h-4 shrink-0 text-slate-500" />
            {item.label}
          </Link>
        ))}
        <button
          onClick={() => logout()}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-all"
        >
          <LogOut className="w-4 h-4 shrink-0" />
          Sign Out
        </button>
      </div>

      {/* User */}
      {user && (
        <div className="px-4 pb-4">
          <div className="flex items-center gap-3 px-3 py-3 rounded-xl bg-surface-2 border border-surface-border">
            {user.github_avatar_url ? (
              <Image
                src={user.github_avatar_url}
                alt={user.github_login}
                width={32}
                height={32}
                className="rounded-full"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-brand-700 flex items-center justify-center text-white text-sm font-bold">
                {user.github_login[0].toUpperCase()}
              </div>
            )}
            <div className="min-w-0">
              <p className="text-sm font-medium text-white truncate">
                {user.github_name || user.github_login}
              </p>
              <p className="text-xs text-slate-400 truncate">@{user.github_login}</p>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
