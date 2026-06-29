/**
 * Next.js middleware — protects dashboard routes at the edge.
 * Checks for access_token cookie (set by auth callback).
 * No cookie → redirect to /login before any page renders.
 *
 * This eliminates the "flash of unauthenticated content" completely —
 * the redirect happens at the CDN edge, not in the browser.
 */

import { NextRequest, NextResponse } from "next/server";

const PROTECTED_PREFIXES = ["/dashboard", "/repositories", "/review", "/history", "/health", "/debt", "/settings", "/pull-requests"];
const PUBLIC_PATHS = ["/", "/login", "/callback"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public paths through
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"))) {
    return NextResponse.next();
  }

  // Check if path is protected
  const isProtected = PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix));

  if (!isProtected) {
    return NextResponse.next();
  }

  // Check for auth token in cookie (set during GitHub callback)
  const token = request.cookies.get("access_token")?.value;

  if (!token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     * - public folder
     * - api routes
     */
    "/((?!_next/static|_next/image|favicon.ico|public|api).*)",
  ],
};
