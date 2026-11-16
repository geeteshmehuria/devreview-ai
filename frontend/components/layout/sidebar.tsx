"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Code2, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/stores/auth-store";
import { NAV_ITEMS, SETTINGS_ITEM, isActivePath } from "./nav-items";

/** Desktop-only sidebar (lg and up). Phones use <MobileNav />. */
export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();

  return (
    <aside className="hidden lg:flex w-64 h-screen sticky top-0 bg-surface-1 border-r border-surface-border flex-col shrink-0">
      {/* Logo */}
      <Link href="/dashboard" className="h-16 flex items-center gap-2.5 px-5 border-b border-surface-border">
        <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center shrink-0">
          <Code2 className="w-4 h-4 text-white" strokeWidth={2.5} />
        </div>
        <span className="font-semibold text-white">DevReview AI</span>
      </Link>

      {/* Nav */}
      <nav aria-label="Main" className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
        {NAV_ITEMS.map((item) => {
          const active = isActivePath(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 px-3 h-10 rounded-xl text-sm font-medium transition-colors relative group",
                active
                  ? "text-white bg-brand-600/45"
                  : "text-slate-400 hover:text-white hover:bg-surface-3"
              )}
            >
              {active && (
                <motion.div
                  layoutId="sidebar-indicator"
                  className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-brand-400 rounded-full -ml-3"
                />
              )}
              <item.icon
                className={cn("w-4 h-4 shrink-0", active ? "text-brand-400" : "text-slate-500 group-hover:text-slate-300")}
              />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Bottom */}
      <div className="px-3 pb-3 space-y-1 border-t border-surface-border pt-3">
        <Link
          href={SETTINGS_ITEM.href}
          aria-current={isActivePath(pathname, SETTINGS_ITEM.href) ? "page" : undefined}
          className={cn(
            "flex items-center gap-3 px-3 h-10 rounded-xl text-sm font-medium transition-colors",
            isActivePath(pathname, SETTINGS_ITEM.href)
              ? "text-white bg-brand-600/45"
              : "text-slate-400 hover:text-white hover:bg-surface-3"
          )}
        >
          <SETTINGS_ITEM.icon className="w-4 h-4 shrink-0 text-slate-500" />
          {SETTINGS_ITEM.label}
        </Link>
        <button
          onClick={() => logout()}
          className="w-full flex items-center gap-3 px-3 h-10 rounded-xl text-sm font-medium text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
        >
          <LogOut className="w-4 h-4 shrink-0" />
          Sign Out
        </button>
      </div>

      {/* User */}
      {user && (
        <div className="px-3 pb-4">
          <div className="flex items-center gap-3 p-2.5 rounded-xl bg-surface-2 border border-surface-border">
            <Avatar login={user.github_login} url={user.github_avatar_url} size={32} />
            <div className="min-w-0">
              <p className="text-sm font-medium text-white truncate">{user.github_name || user.github_login}</p>
              <p className="text-xs text-slate-400 truncate">@{user.github_login}</p>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

export function Avatar({ login, url, size = 32 }: { login?: string; url?: string | null; size?: number }) {
  if (url) {
    return <Image src={url} alt={login || "Avatar"} width={size} height={size} className="rounded-full shrink-0" />;
  }
  return (
    <div
      className="rounded-full bg-brand-600 flex items-center justify-center text-white text-sm font-bold shrink-0"
      style={{ width: size, height: size }}
    >
      {login?.[0]?.toUpperCase() || "?"}
    </div>
  );
}
