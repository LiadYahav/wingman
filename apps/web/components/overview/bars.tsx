import { cn } from "@/lib/utils";

/**
 * The Overview's small visuals: a thin bar as wide as one count's share.
 * Decoration only (`aria-hidden`): the numbers beside them are the text.
 */

export function Bar({ percent, className, fill = "bg-primary/70" }: { percent: number; className?: string; fill?: string }) {
  return (
    <span className={cn("block h-1.5 w-full overflow-hidden rounded-full bg-muted", className)} aria-hidden>
      <span className={cn("block h-full rounded-full transition-[width] duration-300", fill)} style={{ width: `${percent}%` }} />
    </span>
  );
}
