"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Github, Code2, Shield, Zap } from "lucide-react";
import { authApi } from "@/lib/api/auth";
import { toast } from "sonner";

export default function LoginPage() {
  const [isLoading, setIsLoading] = useState(false);

  const handleGitHubLogin = async () => {
    setIsLoading(true);
    try {
      const { url } = await authApi.getGithubUrl();
      window.location.href = url;
    } catch {
      toast.error("Failed to initiate GitHub login. Please try again.");
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-0 flex items-center justify-center px-4 relative overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-700/15 rounded-full blur-[100px]" />
        <div className="absolute bottom-1/4 right-1/4 w-64 h-64 bg-brand-600/10 rounded-full blur-[80px]" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md relative"
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 mb-4 shadow-lg shadow-brand-700/30">
            <Code2 className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">DevReview AI</h1>
          <p className="text-slate-400 mt-1">AI-powered code review platform</p>
        </div>

        {/* Card */}
        <div className="glass-card rounded-2xl p-8">
          <h2 className="text-xl font-semibold text-white mb-2 text-center">Welcome back</h2>
          <p className="text-slate-400 text-sm text-center mb-8">
            Sign in with your GitHub account to continue
          </p>

          <button
            onClick={handleGitHubLogin}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-3 px-6 py-3.5 bg-white hover:bg-slate-100 text-slate-900 rounded-xl font-semibold transition-all disabled:opacity-60 disabled:cursor-not-allowed hover:scale-[1.02] active:scale-[0.98]"
          >
            {isLoading ? (
              <div className="w-5 h-5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
            ) : (
              <Github className="w-5 h-5" />
            )}
            {isLoading ? "Redirecting to GitHub…" : "Continue with GitHub"}
          </button>

          {/* Trust signals */}
          <div className="mt-6 pt-6 border-t border-surface-border space-y-3">
            {[
              { icon: Shield, text: "We never store your code permanently" },
              { icon: Zap, text: "First review in under 30 seconds" },
            ].map(({ icon: Icon, text }) => (
              <div key={text} className="flex items-center gap-3 text-sm text-slate-400">
                <Icon className="w-4 h-4 text-brand-400 shrink-0" />
                <span>{text}</span>
              </div>
            ))}
          </div>
        </div>

        <p className="text-center text-xs text-slate-500 mt-4">
          By signing in you agree to our terms of service.
        </p>
      </motion.div>
    </div>
  );
}
