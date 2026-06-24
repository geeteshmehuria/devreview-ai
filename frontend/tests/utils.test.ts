import { describe, it, expect } from "vitest";
import {
  formatScore,
  getScoreColor,
  getSeverityColor,
  formatRelativeTime,
  truncate,
  categoryLabel,
} from "@/lib/utils";

describe("formatScore", () => {
  it("formats a numeric score to a rounded string", () => {
    expect(formatScore(87.4)).toBe("87");
    expect(formatScore(100)).toBe("100");
    expect(formatScore(0)).toBe("0");
  });

  it("returns em dash for null/undefined", () => {
    expect(formatScore(null)).toBe("—");
    expect(formatScore(undefined)).toBe("—");
  });
});

describe("getScoreColor", () => {
  it("returns emerald for scores >= 80", () => {
    expect(getScoreColor(80)).toBe("text-emerald-400");
    expect(getScoreColor(95)).toBe("text-emerald-400");
  });

  it("returns yellow for scores 60–79", () => {
    expect(getScoreColor(60)).toBe("text-yellow-400");
    expect(getScoreColor(72)).toBe("text-yellow-400");
  });

  it("returns orange for scores 40–59", () => {
    expect(getScoreColor(40)).toBe("text-orange-400");
    expect(getScoreColor(55)).toBe("text-orange-400");
  });

  it("returns red for scores below 40", () => {
    expect(getScoreColor(0)).toBe("text-red-400");
    expect(getScoreColor(39)).toBe("text-red-400");
  });
});

describe("getSeverityColor", () => {
  it("maps severity strings to CSS classes", () => {
    expect(getSeverityColor("critical")).toContain("text-red-400");
    expect(getSeverityColor("high")).toContain("text-orange-400");
    expect(getSeverityColor("medium")).toContain("text-yellow-400");
    expect(getSeverityColor("low")).toContain("text-blue-400");
    expect(getSeverityColor("info")).toContain("text-slate-400");
  });

  it("returns info style for unknown severity", () => {
    expect(getSeverityColor("unknown")).toContain("text-slate-400");
  });
});

describe("truncate", () => {
  it("truncates strings longer than maxLen", () => {
    expect(truncate("hello world", 8)).toBe("hello...");
  });

  it("returns unchanged string when within maxLen", () => {
    expect(truncate("short", 10)).toBe("short");
  });
});

describe("categoryLabel", () => {
  it("maps category keys to display labels", () => {
    expect(categoryLabel("security")).toBe("Security");
    expect(categoryLabel("best_practices")).toBe("Best Practices");
    expect(categoryLabel("architecture")).toBe("Architecture");
  });
});

describe("formatRelativeTime", () => {
  it("returns 'Never' for null input", () => {
    expect(formatRelativeTime(null)).toBe("Never");
    expect(formatRelativeTime(undefined)).toBe("Never");
  });

  it("returns 'Just now' for very recent dates", () => {
    const now = new Date().toISOString();
    expect(formatRelativeTime(now)).toBe("Just now");
  });
});
