"use client";

import Image from "next/image";
import { useMutation } from "@tanstack/react-query";
import { Github, Shield } from "lucide-react";
import { toast } from "sonner";
import { authApi } from "@/lib/api/auth";
import { useAuthStore } from "@/lib/stores/auth-store";
import { BracketsLoader } from "@/components/shared/brackets-loader";

export default function SettingsPage() {
  const { user, clearTokens } = useAuthStore();

  const deleteMutation = useMutation({
    mutationFn: authApi.deleteAccount,
    onSuccess: () => {
      clearTokens();
      window.location.href = "/";
    },
    onError: (e: Error) => toast.error(e.message || "Failed to delete account"),
  });

  const handleDelete = () => {
    if (confirm("Permanently delete your account, reviews and repositories? This cannot be undone.")) {
      deleteMutation.mutate();
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Settings</h2>
        <p className="text-slate-400 text-sm mt-1">Manage your account.</p>
      </div>

      {/* Profile */}
      <div className="glass-card rounded-2xl p-4 sm:p-6">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">Profile</h3>
        {user && (
          <div className="flex flex-wrap items-center gap-4">
            {user.github_avatar_url ? (
              <Image src={user.github_avatar_url} alt={user.github_login} width={64} height={64} className="rounded-full" />
            ) : (
              <div className="w-16 h-16 rounded-full bg-brand-600 flex items-center justify-center text-white text-2xl font-bold">
                {user.github_login[0].toUpperCase()}
              </div>
            )}
            <div className="min-w-0">
              <p className="text-white font-semibold text-lg">{user.github_name || user.github_login}</p>
              <p className="text-slate-400">@{user.github_login}</p>
              {user.github_email && <p className="text-slate-500 text-sm mt-0.5 break-all">{user.github_email}</p>}
            </div>
            <a
              href={`https://github.com/${user.github_login}`}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full sm:w-auto sm:ml-auto flex items-center justify-center gap-2 px-4 h-11 sm:h-10 bg-surface-2 hover:bg-surface-3 text-slate-300 rounded-lg text-sm transition-colors border border-surface-border"
            >
              <Github className="w-4 h-4" />
              GitHub Profile
            </a>
          </div>
        )}
      </div>

      {/* Danger zone */}
      <div className="glass-card rounded-2xl p-4 sm:p-6 border border-red-500/20">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="w-4 h-4 text-red-400" />
          <h3 className="text-sm font-semibold text-red-400 uppercase tracking-wider">Danger Zone</h3>
        </div>
        <p className="text-sm text-slate-400 mb-4">
          Deleting your account permanently removes all reviews, stored code and repositories. This cannot be undone.
        </p>
        <button
          onClick={handleDelete}
          disabled={deleteMutation.isPending}
          className="w-full sm:w-auto flex items-center justify-center gap-2 px-4 h-11 sm:h-10 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          {deleteMutation.isPending && <BracketsLoader />}
          Delete Account
        </button>
      </div>
    </div>
  );
}
