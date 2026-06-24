"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { ArrowRight, Shield, Zap, GitPullRequest, BarChart3, Code2, Lock } from "lucide-react";

const features = [
  {
    icon: Code2,
    title: "AI Code Review",
    description: "Paste code or upload files. Get instant security, performance, and architecture feedback.",
  },
  {
    icon: GitPullRequest,
    title: "Pull Request Analysis",
    description: "Automatically analyse PR diffs for bugs, regressions, and security risks.",
  },
  {
    icon: Shield,
    title: "Security Scanning",
    description: "Detect OWASP vulnerabilities, CWE issues, and secret exposure in real-time.",
  },
  {
    icon: BarChart3,
    title: "Repository Health",
    description: "Track overall health score with trend graphs and detailed breakdowns.",
  },
  {
    icon: Zap,
    title: "Technical Debt",
    description: "Quantify debt with severity levels, effort estimates, and remediation paths.",
  },
  {
    icon: Lock,
    title: "Review History",
    description: "Never lose a review. Full timeline with previous findings and trends.",
  },
];

const stats = [
  { value: "6", label: "Review categories" },
  { value: "3", label: "AI providers" },
  { value: "∞", label: "Review history" },
  { value: "< 30s", label: "Avg review time" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-surface-0 overflow-hidden">
      {/* Nav */}
      <nav className="fixed top-0 inset-x-0 z-50 glass border-b border-surface-border">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center">
              <Code2 className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-white">DevReview AI</span>
          </div>
          <Link
            href="/login"
            className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Get Started <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-24 px-6 text-center relative">
        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-brand-700/20 rounded-full blur-[120px]" />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="relative max-w-4xl mx-auto"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-700/20 border border-brand-600/30 text-brand-400 text-sm font-medium mb-8">
            <Zap className="w-3.5 h-3.5" />
            Powered by Gemini, GPT-4o &amp; Claude
          </div>

          <h1 className="text-5xl md:text-7xl font-bold text-white leading-[1.1] mb-6">
            AI-Powered{" "}
            <span className="gradient-text">Code Reviews</span>
            <br />
            in Seconds
          </h1>

          <p className="text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            DevReview AI analyses your repositories, pull requests, and code snippets — delivering
            security findings, performance insights, and architecture guidance instantly.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/login"
              className="flex items-center gap-2 px-8 py-4 bg-brand-600 hover:bg-brand-500 text-white rounded-xl font-semibold text-lg transition-all hover:scale-105"
            >
              Start Reviewing Free
              <ArrowRight className="w-5 h-5" />
            </Link>
            <a
              href="#features"
              className="px-8 py-4 glass glass-hover text-slate-300 rounded-xl font-semibold text-lg"
            >
              See Features
            </a>
          </div>
        </motion.div>

        {/* Stats */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="mt-20 grid grid-cols-2 md:grid-cols-4 gap-6 max-w-3xl mx-auto"
        >
          {stats.map((stat) => (
            <div key={stat.label} className="glass-card rounded-2xl p-6 text-center">
              <div className="text-3xl font-bold gradient-text mb-1">{stat.value}</div>
              <div className="text-sm text-slate-400">{stat.label}</div>
            </div>
          ))}
        </motion.div>
      </section>

      {/* Features */}
      <section id="features" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white mb-4">
              Everything you need for{" "}
              <span className="gradient-text">production-quality</span> code
            </h2>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto">
              Built to the same standard as CodeRabbit, SonarQube, and Codacy — without the
              enterprise price tag.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature, i) => (
              <motion.div
                key={feature.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: i * 0.1 }}
                viewport={{ once: true }}
                className="glass-card glass-hover rounded-2xl p-6"
              >
                <div className="w-12 h-12 rounded-xl bg-brand-700/30 border border-brand-600/20 flex items-center justify-center mb-4">
                  <feature.icon className="w-6 h-6 text-brand-400" />
                </div>
                <h3 className="text-white font-semibold text-lg mb-2">{feature.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{feature.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 px-6">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          viewport={{ once: true }}
          className="max-w-3xl mx-auto glass-card rounded-3xl p-12 text-center relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-brand-700/20 via-transparent to-transparent pointer-events-none" />
          <h2 className="text-4xl font-bold text-white mb-4 relative">
            Ready to ship better code?
          </h2>
          <p className="text-slate-400 mb-8 relative">
            Connect your GitHub account and get your first review in under a minute.
          </p>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 px-8 py-4 bg-brand-600 hover:bg-brand-500 text-white rounded-xl font-semibold text-lg transition-all hover:scale-105 relative"
          >
            Connect GitHub
            <ArrowRight className="w-5 h-5" />
          </Link>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="border-t border-surface-border py-8 px-6 text-center text-slate-500 text-sm">
        <p>DevReview AI — Portfolio Project by Geetesh Maihuria</p>
      </footer>
    </div>
  );
}
