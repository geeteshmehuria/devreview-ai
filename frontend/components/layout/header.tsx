"use client";

import { usePathname } from "next/navigation";
import { useAuthStore } from "@/lib/stores/auth-store";

const PAGE_TITLES: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/repositories": "Repositories",
  "/review": "Code Review",
  "/pull-requests": "Pull Requests",
  "/history": "Review History",
  "/health": "Repository Health",
  "/debt": "Technical Debt",
  "/settings": "Settings",
};

export function Header() {
  const pathname = usePathname();
  const { user } = useAuthStore();

  const title =
    Object.entries(PAGE_TITLES).find(([key]) => pathname.startsWith(key))?.[1] ||
    "DevReview AI";

  return (
    <header className="h-16 glass border-b border-surface-border flex items-center justify-between px-6 shrink-0">
      <div>
        <h1 className="text-white font-semibold text-lg">{title}</h1>
      </div>

      <div className="w-8 h-8 rounded-full bg-brand-700 flex items-center justify-center text-white text-sm font-bold">
        {user?.github_login?.[0]?.toUpperCase() || "?"}
      </div>
    </header>
  );
}
