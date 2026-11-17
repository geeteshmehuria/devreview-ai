import { cn } from "@/lib/utils";

/** App-wide loading indicator: a radar sweep that pings findings. `size` is the diameter in px. */
export function RadarLoader({
  size = 16,
  label = "Loading",
  className,
}: {
  size?: number;
  label?: string;
  className?: string;
}) {
  return (
    <span role="status" aria-label={label} className={cn("radar-loader", className)} style={{ fontSize: size }}>
      <i />
      <i />
      <i />
    </span>
  );
}
