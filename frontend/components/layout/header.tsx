"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Code2, Plus } from "lucide-react";
import { useAuthStore } from "@/lib/stores/auth-store";
import { Avatar } from "./sidebar";
import { PAGE_TITLES } from "./nav-items";

export function Header() {
  const pathname = usePathname();
  const { user } = useAuthStore();

  const title =
    Object.entries(PAGE_TITLES).find(([key]) => pathname.startsWith(key))?.[1] || "DevReview AI";
  const onReview = pathname.startsWith("/review");

  return (
    <header className="sticky top-0 z-30 h-14 lg:h-16 bg-surface-0/85 backdrop-blur-md border-b border-surface-border flex items-center gap-3 px-4 sm:px-6 lg:px-8 shrink-0">
      {/* Logo only on phones/tablets — the sidebar shows it on desktop */}
      <Link
        href="/dashboard"
        aria-label="DevReview AI home"
        className="lg:hidden w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center shrink-0"
      >
        <Code2 className="w-4 h-4 text-white" strokeWidth={2.5} />
      </Link>

      <h1 className="text-white font-semibold text-base lg:text-lg truncate">{title}</h1>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        {!onReview && (
          <Link
            href="/review"
            className="hidden sm:flex items-center gap-2 h-10 px-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-sm font-semibold transition-colors"
          >
            <Plus className="w-4 h-4" strokeWidth={2.5} />
            New review
          </Link>
        )}
        <Link href="/settings" aria-label="Account settings" className="rounded-full">
          <Avatar login={user?.github_login} url={user?.github_avatar_url} size={32} />
        </Link>
      </div>
    </header>
  );
}
