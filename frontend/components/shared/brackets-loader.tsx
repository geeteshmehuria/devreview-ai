import { cn } from "@/lib/utils";

/**
 * App-wide loading indicator: the </> mark breathing while its slash flips.
 * `size` is the height in px. Draws in currentColor, so it matches the text it sits next to.
 */
export function BracketsLoader({
  size = 16,
  label = "Loading",
  className,
}: {
  size?: number;
  label?: string;
  className?: string;
}) {
  return (
    <span role="status" aria-label={label} className={cn("brackets-loader", className)} style={{ fontSize: size }}>
      <svg viewBox="0 0 58 48" aria-hidden="true">
        <path className="l" d="M16 12 4 24l12 12" />
        <path className="s" d="M33 9 25 39" />
        <path className="r" d="M42 12l12 12-12 12" />
      </svg>
    </span>
  );
}
