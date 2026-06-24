import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ScoreRing } from "@/components/shared/score-ring";

describe("ScoreRing", () => {
  it("renders the score number", () => {
    render(<ScoreRing score={75} />);
    expect(screen.getByText("75")).toBeInTheDocument();
  });

  it("renders an SVG element", () => {
    const { container } = render(<ScoreRing score={50} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("does not render label text when showLabel is false", () => {
    const { container } = render(<ScoreRing score={80} showLabel={false} />);
    // Score number should not appear
    expect(container.textContent).toBe("");
  });

  it("renders a custom label when provided", () => {
    render(<ScoreRing score={60} label="Health" />);
    expect(screen.getByText("Health")).toBeInTheDocument();
  });

  it("rounds decimal scores for display", () => {
    render(<ScoreRing score={82.7} />);
    expect(screen.getByText("83")).toBeInTheDocument();
  });
});
