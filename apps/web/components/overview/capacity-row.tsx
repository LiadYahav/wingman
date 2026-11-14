import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Bar } from "./bars";

/**
 * One place's capacity: what is free (the number) and how much is in use
 * (the bar), amber when all of it is in use. `children` is the line below it.
 */
export function CapacityRow({
  href,
  name,
  context,
  free,
  of,
  usedPercent,
  label,
  mono = false,
  children,
  ...props
}: {
  href: string;
  name: string;
  /** Beside the name, muted: the site an MCE is at. */
  context?: string;
  free: number;
  /** "of 12" after the number, when the total is worth saying. */
  of?: number;
  usedPercent: number;
  /** The row's accessible name: what the number counts. */
  label: string;
  /** The name is an identifier (an MCE folder), not a word. */
  mono?: boolean;
  children?: ReactNode;
  "data-testid"?: string;
}) {
  // Nothing free of something: all of it in use. A place with nothing at all is only empty.
  const none = free === 0 && of !== 0;
  return (
    <Link
      href={href}
      aria-label={label}
      className="block rounded-lg px-3 py-2 hover:bg-muted/50 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      {...props}
    >
      <span className="flex items-baseline justify-between gap-3">
        <span className="flex min-w-0 items-baseline gap-2">
          <span className={cn("truncate font-medium", mono ? "font-mono text-xs" : "text-sm")}>{name}</span>
          {context && <span className="shrink-0 text-[11px] text-muted-foreground">{context}</span>}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">
          <span className={cn("text-sm font-semibold tabular-nums", none ? "text-status-warning-fg" : "text-foreground")}>{free}</span>
          {" "}free{of !== undefined && <> of <span className="tabular-nums">{of}</span></>}
        </span>
      </span>
      <Bar percent={usedPercent} className="mt-1.5" fill={none ? "bg-status-warning/70" : "bg-primary/70"} />
      {children}
    </Link>
  );
}

/** A card's one headline number: what is free across every row. */
export function CapacityTotal({ free, what, ...props }: { free: number; what: string; "data-testid"?: string }) {
  return (
    <p className="mb-2 text-xs text-muted-foreground" {...props}>
      <span className="mr-1 text-2xl font-semibold tabular-nums text-foreground">{free}</span>
      {what}
    </p>
  );
}
