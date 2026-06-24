"use client";

/**
 * Bootstraps auth state on app load.
 * Calls /auth/me with stored token to hydrate user — prevents dashboard flash.
 */

import { useEffect } from "react";
import { useAuthStore } from "@/lib/stores/auth-store";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { initialize, isInitialized } = useAuthStore();

  useEffect(() => {
    initialize();
  }, [initialize]);

  // Don't render children until we know the auth state
  // This prevents the "flash of unauthenticated content" on dashboard pages
  if (!isInitialized) {
    return (
      <div className="min-h-screen bg-surface-0 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-400">Loading DevReview AI…</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
