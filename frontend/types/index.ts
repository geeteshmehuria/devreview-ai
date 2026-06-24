// ── Auth ──────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  github_login: string;
  github_name: string | null;
  github_avatar_url: string | null;
  github_email: string | null;
  role: "user" | "admin";
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// ── Repository ────────────────────────────────────────────────────────────────

export type RepositoryStatus = "pending" | "analyzing" | "analyzed" | "failed";

export interface Repository {
  id: string;
  full_name: string;
  name: string;
  description: string | null;
  url: string;
  language: string | null;
  stars: number;
  forks: number;
  is_private: boolean;
  status: RepositoryStatus;
  last_analyzed_at: string | null;
  analysis_summary: AnalysisSummary | null;
}

export interface AnalysisSummary {
  overall_score: number;
  ai_summary: string;
  provider: string;
  model: string;
}

export interface HealthSnapshot {
  id: string;
  overall_score: number;
  security_score: number;
  performance_score: number;
  maintainability_score: number;
  documentation_score: number;
  complexity_score: number;
  breakdown: Record<string, unknown> | null;
  created_at: string;
}

export interface RepositoryDetail extends Repository {
  health_snapshots: HealthSnapshot[];
}

// ── Reviews ───────────────────────────────────────────────────────────────────

export type ReviewType = "repository" | "pull_request" | "code_snippet" | "file_upload";
export type ReviewStatus = "pending" | "processing" | "completed" | "failed";
export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface Finding {
  id: string;
  severity: Severity;
  title: string;
  description: string;
  file_path: string | null;
  line_number: number | null;
  code_snippet: string | null;
  recommendation: string | null;
  extra: Record<string, unknown>;
}

export interface CategoryScore {
  category: string;
  score: number;
  summary: string;
  suggestions: string[];
}

export interface Review {
  id: string;
  review_type: ReviewType;
  status: ReviewStatus;
  title: string | null;
  language: string | null;
  overall_score: number | null;
  risk_score: number | null;
  ai_summary: string | null;
  ai_provider: string;
  ai_model: string;
  created_at: string;
  category_scores: CategoryScore[];
  security_findings: Finding[];
  performance_findings: Finding[];
  code_smells: Finding[];
  technical_debt: Finding[];
}

export interface ReviewListItem {
  id: string;
  review_type: ReviewType;
  status: ReviewStatus;
  title: string | null;
  language: string | null;
  overall_score: number | null;
  risk_score: number | null;
  ai_provider: string;
  created_at: string;
}

export interface ReviewListResponse {
  items: ReviewListItem[];
  total: number;
  page: number;
  page_size: number;
}

// ── Pull Requests ─────────────────────────────────────────────────────────────

export interface PRReviewResult {
  pr_number: number;
  pr_title: string;
  overall_score: number;
  risk_score: number;
  ai_summary: string;
  category_scores: CategoryScore[];
  security_findings: number;
  performance_findings: number;
  provider: string;
}

// ── API ───────────────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string;
  type?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
