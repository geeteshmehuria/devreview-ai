"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { LogOut, MoreHorizontal, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/stores/auth-store";
import { MOBILE_MORE, NAV_ITEMS, isActivePath } from "./nav-items";

/** Bottom tab bar + "More" sheet, shown below the lg breakpoint. */
export function MobileNav() {
  const pathname = usePathname();
  const { logout } = useAuthStore();
  const [moreOpen, setMoreOpen] = useState(false);

  // Close the sheet whenever the route changes
  useEffect(() => setMoreOpen(false), [pathname]);

  // Close on Escape and stop the page scrolling behind the sheet
  useEffect(() => {
    if (!moreOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMoreOpen(false);
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [moreOpen]);

  const tab = (href: string) => NAV_ITEMS.find((i) => i.href === href)!;
  const left = [tab("/dashboard"), tab("/repositories")];
  const right = [tab("/history")];
  const moreActive = MOBILE_MORE.some((i) => isActivePath(pathname, i.href));
  const reviewActive = isActivePath(pathname, "/review");

  const renderTab = (href: string) => {
    const item = tab(href);
    const active = isActivePath(pathname, href);
    return (
      <Link
        key={href}
        href={href}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex-1 flex flex-col items-center justify-center gap-1 h-16 text-[11px] font-semibold transition-colors",
          active ? "text-brand-400" : "text-slate-400 hover:text-white"
        )}
      >
        <item.icon className="w-[22px] h-[22px]" />
        {item.short}
      </Link>
    );
  };

  return (
    <>
      <nav
        aria-label="Main"
        className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-surface-1/95 backdrop-blur-md border-t border-surface-border pb-safe"
      >
        <div className="flex items-stretch max-w-lg mx-auto px-2">
          {left.map((i) => renderTab(i.href))}

          <Link
            href="/review"
            aria-label="New code review"
            aria-current={reviewActive ? "page" : undefined}
            className="flex-1 flex items-center justify-center h-16"
          >
            <span
              className={cn(
                "w-13 h-13 -mt-5 rounded-2xl flex items-center justify-center text-white shadow-lg shadow-brand-600/40 transition-colors",
                reviewActive ? "bg-brand-500 ring-2 ring-brand-400" : "bg-brand-600 hover:bg-brand-500"
              )}
            >
              <Plus className="w-6 h-6" strokeWidth={2.5} />
            </span>
          </Link>

          {right.map((i) => renderTab(i.href))}

          <button
            type="button"
            onClick={() => setMoreOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={moreOpen}
            className={cn(
              "flex-1 flex flex-col items-center justify-center gap-1 h-16 text-[11px] font-semibold transition-colors",
              moreActive ? "text-brand-400" : "text-slate-400 hover:text-white"
            )}
          >
            <MoreHorizontal className="w-[22px] h-[22px]" />
            More
          </button>
        </div>
      </nav>

      <AnimatePresence>
        {moreOpen && (
          <>
            <motion.div
              key="backdrop"
              className="lg:hidden fixed inset-0 z-50 bg-black/70"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMoreOpen(false)}
            />
            <motion.div
              key="sheet"
              role="dialog"
              aria-modal="true"
              aria-label="More pages"
              className="lg:hidden fixed bottom-0 inset-x-0 z-50 bg-surface-1 border-t border-surface-border rounded-t-3xl pb-safe"
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", damping: 30, stiffness: 320 }}
            >
              <div className="max-w-lg mx-auto px-4 pt-3 pb-4">
                <div className="w-10 h-1 rounded-full bg-surface-4 mx-auto mb-3" />
                <div className="flex items-center justify-between mb-2 px-1">
                  <p className="text-sm font-semibold text-white">More</p>
                  <button
                    type="button"
                    onClick={() => setMoreOpen(false)}
                    aria-label="Close"
                    className="w-11 h-11 -mr-2 flex items-center justify-center rounded-xl text-slate-400 hover:text-white hover:bg-surface-3"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
                <div className="space-y-1">
                  {MOBILE_MORE.map((item) => {
                    const active = isActivePath(pathname, item.href);
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "flex items-center gap-3 px-3 h-12 rounded-xl text-[15px] font-medium transition-colors",
                          active ? "bg-brand-600/45 text-white" : "text-slate-200 hover:bg-surface-3"
                        )}
                      >
                        <item.icon className={cn("w-5 h-5", active ? "text-brand-400" : "text-slate-400")} />
                        {item.label}
                      </Link>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() => logout()}
                    className="w-full flex items-center gap-3 px-3 h-12 rounded-xl text-[15px] font-medium text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    <LogOut className="w-5 h-5" />
                    Sign Out
                  </button>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
