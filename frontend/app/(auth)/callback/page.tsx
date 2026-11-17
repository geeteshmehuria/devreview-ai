"use client";

/**
 * GitHub OAuth callback page.
 * Exchanges the `code` param from GitHub for our JWT tokens,
 * stores them (lib/session also sets the middleware's marker cookie),
 * and redirects to the page the user originally asked for.
 */

import { useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { motion } from "framer-motion";
import { Code2 } from "lucide-react";
import { authApi } from "@/lib/api/auth";
import { useAuthStore } from "@/lib/stores/auth-store";
import { toast } from "sonner";
import { RadarLoader } from "@/components/shared/radar-loader";

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

    // CSRF check: the state GitHub echoes back must match the one this browser
    // stored before redirecting. A missing stored state means this login was not
    // started here (login CSRF), so it is rejected. The backend also verifies
    // the state's signature.
    const expectedState = sessionStorage.getItem("oauth_state");
    const returnedState = searchParams.get("state");
    const redirectTo = sessionStorage.getItem("post_login_redirect") || "/dashboard";
    sessionStorage.removeItem("oauth_state");
    sessionStorage.removeItem("post_login_redirect");
    if (!expectedState || returnedState !== expectedState) {
      toast.error("Login session mismatch. Please try signing in again.");
      router.replace("/login");
      return;
    }

    (async () => {
      try {
        const { tokens, user } = await authApi.githubCallback(code, expectedState);
        setTokens(tokens.access_token, tokens.refresh_token);
        setUser(user);

        toast.success(`Welcome, ${user.github_name || user.github_login}!`);
        router.replace(redirectTo);
      } catch {
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
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-brand-600 mb-6 shadow-lg shadow-brand-600/30">
          <Code2 className="w-8 h-8 text-white" />
        </div>
        <RadarLoader size={40} className="block mx-auto mb-4" />
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
