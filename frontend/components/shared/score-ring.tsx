"use client";

import { motion } from "framer-motion";
import { getScoreColor } from "@/lib/utils";

interface ScoreRingProps {
  score: number;
  size?: number;
  strokeWidth?: number;
  showLabel?: boolean;
  label?: string;
  animate?: boolean;
}

export function ScoreRing({
  score,
  size = 80,
  strokeWidth = 6,
  showLabel = true,
  label,
  animate = true,
}: ScoreRingProps) {
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  const colorMap: Record<string, string> = {
    "text-emerald-400": "#34d399",
    "text-yellow-400": "#facc15",
    "text-orange-400": "#fb923c",
    "text-red-400": "#f87171",
  };

  const colorClass = getScoreColor(score);
  const strokeColor = colorMap[colorClass] || "#34d399";

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="rotate-[-90deg]">
        {/* Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={strokeWidth}
        />
        {/* Progress */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: animate ? 1.2 : 0, ease: "easeOut" }}
        />
      </svg>
      {showLabel && (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`font-bold ${colorClass} leading-none`} style={{ fontSize: size * 0.22 }}>
            {Math.round(score)}
          </span>
          {label && (
            <span className="text-slate-500 leading-none mt-0.5" style={{ fontSize: size * 0.12 }}>
              {label}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
