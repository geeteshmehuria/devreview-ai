/**
 * Next.js middleware — protects dashboard routes at the edge.
 * Checks for the non-secret `session` marker cookie (see lib/session.ts).
 * No cookie → redirect to /login before any page renders. Real authorization
 * happens in the API, which validates the bearer token on every request.
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

  if (!request.cookies.get("session")?.value) {
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
