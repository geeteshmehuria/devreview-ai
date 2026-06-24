"use client";

import { useAuthStore } from "@/lib/stores/auth-store";
import Image from "next/image";
import { Github, Shield, Bell, Cpu } from "lucide-react";

export default function SettingsPage() {
  const { user } = useAuthStore();

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Settings</h2>
        <p className="text-slate-400 text-sm mt-1">Manage your account and preferences.</p>
      </div>

      {/* Profile */}
      <div className="glass-card rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">Profile</h3>
        {user && (
          <div className="flex items-center gap-4">
            {user.github_avatar_url ? (
              <Image src={user.github_avatar_url} alt={user.github_login} width={64} height={64} className="rounded-full" />
            ) : (
              <div className="w-16 h-16 rounded-full bg-brand-700 flex items-center justify-center text-white text-2xl font-bold">
                {user.github_login[0].toUpperCase()}
              </div>
            )}
            <div>
              <p className="text-white font-semibold text-lg">{user.github_name || user.github_login}</p>
              <p className="text-slate-400">@{user.github_login}</p>
              {user.github_email && <p className="text-slate-500 text-sm mt-0.5">{user.github_email}</p>}
            </div>
            <a
              href={`https://github.com/${user.github_login}`}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto flex items-center gap-2 px-4 py-2 bg-surface-2 hover:bg-surface-3 text-slate-300 rounded-lg text-sm transition-colors border border-surface-border"
            >
              <Github className="w-4 h-4" />
              GitHub Profile
            </a>
          </div>
        )}
      </div>

      {/* AI Provider */}
      <div className="glass-card rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-4">
          <Cpu className="w-4 h-4 text-brand-400" />
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">AI Provider</h3>
        </div>
        <div className="space-y-3">
          {[
            { id: "gemini", label: "Google Gemini", desc: "Primary provider — fast, cost-effective", default: true },
            { id: "openai", label: "OpenAI GPT-4o", desc: "High-quality reviews", default: false },
            { id: "claude", label: "Anthropic Claude", desc: "Excellent code analysis", default: false },
          ].map((provider) => (
            <label key={provider.id} className="flex items-start gap-3 p-3 rounded-xl cursor-pointer hover:bg-surface-2 transition-colors">
              <input
                type="radio"
                name="provider"
                value={provider.id}
                defaultChecked={provider.default}
                className="mt-0.5 accent-brand-500"
              />
              <div>
                <p className="text-sm font-medium text-white">{provider.label}</p>
                <p className="text-xs text-slate-400">{provider.desc}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Notifications */}
      <div className="glass-card rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-4">
          <Bell className="w-4 h-4 text-brand-400" />
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Notifications</h3>
        </div>
        <div className="space-y-3">
          {[
            { label: "Review completed", desc: "Notify when an AI review finishes" },
            { label: "Analysis completed", desc: "Notify when repository analysis is done" },
          ].map(({ label, desc }) => (
            <div key={label} className="flex items-center justify-between p-3 rounded-xl hover:bg-surface-2 transition-colors">
              <div>
                <p className="text-sm font-medium text-white">{label}</p>
                <p className="text-xs text-slate-400">{desc}</p>
              </div>
              <input type="checkbox" defaultChecked className="accent-brand-500" />
            </div>
          ))}
        </div>
      </div>

      {/* Danger zone */}
      <div className="glass-card rounded-2xl p-6 border border-red-500/20">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="w-4 h-4 text-red-400" />
          <h3 className="text-sm font-semibold text-red-400 uppercase tracking-wider">Danger Zone</h3>
        </div>
        <p className="text-sm text-slate-400 mb-4">
          Deleting your account permanently removes all reviews and data. This cannot be undone.
        </p>
        <button className="px-4 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg text-sm transition-colors">
          Delete Account
        </button>
      </div>
    </div>
  );
}
