/**
 * Token storage shared by the API client and the auth store.
 *
 * Tokens live in localStorage. A separate, non-secret `session` marker cookie
 * lets the edge middleware know a user is signed in — it holds no token, and
 * it lives as long as the refresh token so reloads don't bounce users to /login.
 */

const ACCESS = "access_token";
const REFRESH = "refresh_token";
const SESSION_COOKIE_MAX_AGE = 30 * 24 * 60 * 60; // matches REFRESH_TOKEN_EXPIRE_DAYS

function setSessionCookie(maxAge: number) {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `session=1; path=/; max-age=${maxAge}; SameSite=Lax${secure}`;
}

export function getAccessToken(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(ACCESS);
}

export function getRefreshToken(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(REFRESH);
}

export function saveSession(accessToken: string, refreshToken: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS, accessToken);
  localStorage.setItem(REFRESH, refreshToken);
  setSessionCookie(SESSION_COOKIE_MAX_AGE);
}

export function clearSession() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS);
  localStorage.removeItem(REFRESH);
  setSessionCookie(0);
}
