import {
  LayoutDashboard,
  GitBranch,
  Code2,
  GitPullRequest,
  History,
  Activity,
  AlertTriangle,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  /** Shorter label for the mobile tab bar */
  short?: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", short: "Home", icon: LayoutDashboard },
  { href: "/repositories", label: "Repositories", short: "Repos", icon: GitBranch },
  { href: "/review", label: "Code Review", short: "Review", icon: Code2 },
  { href: "/pull-requests", label: "Pull Requests", short: "PRs", icon: GitPullRequest },
  { href: "/history", label: "Review History", short: "History", icon: History },
  { href: "/health", label: "Repo Health", short: "Health", icon: Activity },
  { href: "/debt", label: "Technical Debt", short: "Debt", icon: AlertTriangle },
];

export const SETTINGS_ITEM: NavItem = { href: "/settings", label: "Settings", icon: Settings };

/** Shown in the mobile bottom bar (Review is the raised centre button). */
export const MOBILE_TABS = ["/dashboard", "/repositories", "/review", "/history"];

/** Everything else lives in the mobile "More" sheet. */
export const MOBILE_MORE: NavItem[] = [
  ...NAV_ITEMS.filter((i) => !MOBILE_TABS.includes(i.href)),
  SETTINGS_ITEM,
];

export function isActivePath(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export const PAGE_TITLES: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/repositories": "Repositories",
  "/review": "Code Review",
  "/pull-requests": "Pull Requests",
  "/history": "Review History",
  "/health": "Repository Health",
  "/debt": "Technical Debt",
  "/settings": "Settings",
};
