import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CitationChip, citationLabel } from "@/components/chat/citation-chip";
import type { ChatCitation } from "@/types";

const code: ChatCitation = {
  n: 2,
  kind: "code",
  file_path: "backend/app/core/rate_limit.py",
  start_line: 10,
  end_line: 42,
  url: "https://github.com/o/r/blob/abc123/backend/app/core/rate_limit.py#L10-L42",
  title: null,
};

describe("citationLabel", () => {
  it("formats path and line range", () => {
    expect(citationLabel(code)).toBe("backend/app/core/rate_limit.py:L10-L42");
  });
  it("uses a single line when start and end match", () => {
    expect(citationLabel({ ...code, end_line: 10 })).toBe("backend/app/core/rate_limit.py:L10");
  });
  it("falls back to the path, then the finding title", () => {
    expect(citationLabel({ ...code, start_line: null, end_line: null })).toBe("backend/app/core/rate_limit.py");
    expect(citationLabel({ ...code, file_path: null, start_line: null, title: "Weak hashing" })).toBe("Weak hashing");
  });
});

describe("CitationChip", () => {
  it("links to GitHub in a new tab, safely", () => {
    render(<CitationChip citation={code} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", code.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveTextContent("[2]");
    expect(link).toHaveTextContent("backend/app/core/rate_limit.py:L10-L42");
  });

  it("renders a finding without a URL as plain text with the finding title", () => {
    render(
      <CitationChip
        citation={{ n: 5, kind: "finding", file_path: null, start_line: null, end_line: null, url: null, title: "SQL injection" }}
      />,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByTitle("Review finding: SQL injection")).toHaveTextContent("SQL injection");
  });
});
