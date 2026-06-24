"use client";

import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Code2, Upload, Play, Loader2, AlertCircle, ChevronDown } from "lucide-react";
import dynamic from "next/dynamic";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { reviewsApi } from "@/lib/api/reviews";
import type { Review } from "@/types";
import { ReviewResultPanel } from "@/components/review/review-result-panel";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <div className="h-full bg-surface-1 animate-pulse rounded-xl" />,
});

const LANGUAGES = [
  "auto", "python", "javascript", "typescript", "java", "go", "rust",
  "csharp", "cpp", "ruby", "php", "swift", "kotlin",
];

type InputMode = "paste" | "upload";

export default function ReviewPage() {
  const [mode, setMode] = useState<InputMode>("paste");
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState("auto");
  const [detailLevel, setDetailLevel] = useState("detailed");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [result, setResult] = useState<Review | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (mode === "upload" && uploadedFile) {
        return reviewsApi.reviewFile(uploadedFile, { language, detail_level: detailLevel });
      }
      if (!code.trim()) throw new Error("No code to review");
      return reviewsApi.reviewCode({ content: code, language, detail_level: detailLevel });
    },
    onSuccess: (data) => {
      setResult(data);
      toast.success("Review completed!");
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    onError: (err: Error) => {
      toast.error(err.message || "Review failed. Please try again.");
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 1_000_000) {
      toast.error("File too large. Max 1MB.");
      return;
    }
    setUploadedFile(file);
    // Detect language from extension
    const ext = file.name.split(".").pop()?.toLowerCase();
    const extLangMap: Record<string, string> = {
      py: "python", js: "javascript", ts: "typescript", tsx: "typescript",
      jsx: "javascript", java: "java", go: "go", rs: "rust", cs: "csharp",
      cpp: "cpp", rb: "ruby", php: "php",
    };
    if (ext && extLangMap[ext]) setLanguage(extLangMap[ext]);
  };

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">AI Code Review</h2>
        <p className="text-slate-400 text-sm mt-1">
          Paste code or upload a file to get an instant AI review across 6 categories.
        </p>
      </div>

      {/* Result Panel */}
      <AnimatePresence>
        {result && (
          <motion.div
            key="result"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            <ReviewResultPanel review={result} onClear={() => setResult(null)} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input area */}
      <div className="glass-card rounded-2xl overflow-hidden">
        {/* Mode tabs */}
        <div className="flex border-b border-surface-border">
          {(["paste", "upload"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`flex items-center gap-2 px-5 py-3.5 text-sm font-medium transition-colors ${
                mode === m
                  ? "text-white border-b-2 border-brand-400 -mb-px"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {m === "paste" ? <Code2 className="w-4 h-4" /> : <Upload className="w-4 h-4" />}
              {m === "paste" ? "Paste Code" : "Upload File"}
            </button>
          ))}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-surface-border bg-surface-1">
          <Select
            value={language}
            onChange={setLanguage}
            options={LANGUAGES.map((l) => ({ value: l, label: l === "auto" ? "Auto-detect" : l }))}
            label="Language"
          />
          <Select
            value={detailLevel}
            onChange={setDetailLevel}
            options={[
              { value: "brief", label: "Brief" },
              { value: "detailed", label: "Detailed" },
              { value: "comprehensive", label: "Comprehensive" },
            ]}
            label="Detail"
          />
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || (mode === "paste" && !code.trim()) || (mode === "upload" && !uploadedFile)}
            className="ml-auto flex items-center gap-2 px-5 py-2 bg-brand-600 hover:bg-brand-500 text-white rounded-lg text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-105 active:scale-95"
          >
            {mutation.isPending ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Analysing…</>
            ) : (
              <><Play className="w-4 h-4" /> Run Review</>
            )}
          </button>
        </div>

        {/* Editor / Upload area */}
        <div className="h-[480px]">
          {mode === "paste" ? (
            <MonacoEditor
              height="100%"
              language={language === "auto" ? "plaintext" : language}
              value={code}
              onChange={(val) => setCode(val || "")}
              theme="vs-dark"
              options={{
                fontSize: 14,
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                padding: { top: 16, bottom: 16 },
                lineNumbers: "on",
                renderLineHighlight: "line",
                smoothScrolling: true,
                cursorBlinking: "smooth",
              }}
            />
          ) : (
            <div
              onClick={() => fileRef.current?.click()}
              className="h-full flex flex-col items-center justify-center cursor-pointer hover:bg-surface-2 transition-colors"
            >
              <input
                ref={fileRef}
                type="file"
                accept=".py,.js,.ts,.tsx,.jsx,.java,.go,.rs,.cs,.cpp,.c,.rb,.php,.swift,.kt,.vue,.svelte"
                onChange={handleFileChange}
                className="hidden"
              />
              {uploadedFile ? (
                <div className="text-center">
                  <div className="w-16 h-16 rounded-2xl bg-brand-700/30 flex items-center justify-center mx-auto mb-4">
                    <Code2 className="w-8 h-8 text-brand-400" />
                  </div>
                  <p className="text-white font-medium">{uploadedFile.name}</p>
                  <p className="text-slate-400 text-sm mt-1">
                    {(uploadedFile.size / 1024).toFixed(1)} KB · Click to change
                  </p>
                </div>
              ) : (
                <div className="text-center">
                  <div className="w-16 h-16 rounded-2xl bg-surface-3 flex items-center justify-center mx-auto mb-4">
                    <Upload className="w-8 h-8 text-slate-500" />
                  </div>
                  <p className="text-white font-medium">Drop a file or click to browse</p>
                  <p className="text-slate-400 text-sm mt-1">Max 1MB · .py .js .ts .java .go .rs and more</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Select({ value, onChange, options, label }: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  label: string;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none pl-3 pr-8 py-1.5 bg-surface-2 border border-surface-border text-white text-sm rounded-lg cursor-pointer hover:border-brand-600/40 transition-colors focus:outline-none focus:border-brand-500"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
    </div>
  );
}
