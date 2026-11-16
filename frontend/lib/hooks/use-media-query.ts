"use client";

import { useEffect, useState } from "react";

/**
 * Returns whether a CSS media query matches. `false` on the server and first
 * render, then the real value after mount (avoids hydration mismatches).
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(query);
    const update = () => setMatches(mql.matches);
    update();
    mql.addEventListener("change", update);
    return () => mql.removeEventListener("change", update);
  }, [query]);

  return matches;
}

/** Phones and small tablets: below Tailwind's `md` breakpoint. */
export const useIsMobile = () => useMediaQuery("(max-width: 767px)");
