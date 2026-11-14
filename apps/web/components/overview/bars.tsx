import { cn } from "@/lib/utils";

/**
 * The Overview's small visuals: a thin bar as wide as one count's share, and
 * a bar split into several counts. Decoration only (`aria-hidden`): the
 * numbers beside them are the text.
 */

export function Bar({ percent, className, fill = "bg-primary/70" }: { percent: number; className?: string; fill?: string }) {
  return (
    <span className={cn("block h-1.5 w-full overflow-hidden rounded-full bg-muted", className)} aria-hidden>
      <span className={cn("block h-full rounded-full transition-[width] duration-300", fill)} style={{ width: `${percent}%` }} />
    </span>
  );
}

export interface BarPart {
  key: string;
  count: number;
  fill: string;
}

/** Each part as wide as its count's share of the whole; a part above zero always shows. */
export function SegmentedBar({ parts, className }: { parts: BarPart[]; className?: string }) {
  return (
    <span className={cn("flex h-2 w-full gap-px overflow-hidden rounded-full bg-muted", className)} aria-hidden data-testid="segmented-bar">
      {parts.filter((part) => part.count > 0).map((part) => (
        <span key={part.key} className={cn("h-full min-w-[3px]", part.fill)} style={{ flexGrow: part.count, flexBasis: 0 }} data-part={part.key} />
      ))}
    </span>
  );
}
