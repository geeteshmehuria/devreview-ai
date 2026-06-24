"use client";

/**
 * GitHub OAuth callback page.
 * Exchanges the `code` param from GitHub for our JWT tokens,
 * stores them, and redirects to the dashboard.
 *
 * Also sets a cookie (via document.cookie) so middleware can protect
 * routes without reading localStorage (which isn't available at edge).
 */

import { useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { motion } from "framer-motion";
import { Code2 } from "lucide-react";
import { authApi } from "@/lib/api/auth";
import { useAuthStore } from "@/lib/stores/auth-store";
import { toast } from "sonner";

function CallbackInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setUser, setTokens } = useAuthStore();
  const hasRun = useRef(false);

  useEffect(() => {
    if (hasRun.current) return;
    hasRun.current = true;

    const code = searchParams.get("code");
    const error = searchParams.get("error");

    if (error || !code) {
      toast.error("GitHub authentication was denied or failed.");
      router.replace("/login");
      return;
    }

    (async () => {
      try {
        const { tokens, user } = await authApi.githubCallback(code);

        // Store tokens
        setTokens(tokens.access_token, tokens.refresh_token);
        setUser(user);

        // Set cookie for middleware (session cookie, not httpOnly since we're client-side)
        document.cookie = `access_token=${tokens.access_token}; path=/; max-age=${tokens.expires_in}; SameSite=Lax`;

        toast.success(`Welcome, ${user.github_name || user.github_login}!`);
        router.replace("/dashboard");
      } catch (err) {
        toast.error("Authentication failed. Please try again.");
        router.replace("/login");
      }
    })();
  }, [searchParams, router, setUser, setTokens]);

  return (
    <div className="min-h-screen bg-surface-0 flex items-center justify-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="text-center"
      >
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 mb-6 shadow-lg shadow-brand-700/30">
          <Code2 className="w-8 h-8 text-white" />
        </div>
        <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <h2 className="text-white font-semibold text-lg">Signing you in…</h2>
        <p className="text-slate-400 text-sm mt-1">Exchanging GitHub credentials</p>
      </motion.div>
    </div>
  );
}

export default function CallbackPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-surface-0" />}>
      <CallbackInner />
    </Suspense>
  );
}
