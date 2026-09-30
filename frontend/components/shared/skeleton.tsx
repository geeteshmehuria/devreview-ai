import { cn } from "@/lib/utils";

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("p-4 rounded-xl bg-surface-2 border border-surface-border animate-pulse", className)}>
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-surface-3 shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-3.5 bg-surface-3 rounded w-3/4" />
          <div className="h-3 bg-surface-3 rounded w-1/2" />
        </div>
        <div className="h-5 w-12 bg-surface-3 rounded" />
      </div>
    </div>
  );
}
