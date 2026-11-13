"use client";

import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { SEGMENTS_REFRESH_MS } from "@/lib/api/segments";
import { updatedAgo } from "@/lib/segments/sites";
import { cn } from "@/lib/utils";

/** "Updated 12 s ago · every 30 s", ticking while the page is open. */
function Updated({ at }: { at: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(timer);
  }, []);
  return (
    <span className="text-xs text-muted-foreground" data-testid="segments-updated">
      Updated {updatedAgo(at, Math.max(now, at))} · every {SEGMENTS_REFRESH_MS / 1000} s
    </span>
  );
}

/**
 * The title, what is shown, and the page's two actions: Refresh (read
 * segments-manager's database now) and the CSV of exactly the rows shown.
 */
export function SegmentsHeader({
  summary,
  updatedAt,
  shown,
  refreshing,
  onRefresh,
  onCsv,
}: {
  summary: string;
  /** When the list was last read; `null` before the first read. */
  updatedAt: number | null;
  /** How many rows the CSV holds; `null` hides both actions (nothing to act on). */
  shown: number | null;
  refreshing: boolean;
  onRefresh: () => void;
  onCsv: () => void;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
          Segments
        </h1>
        <p className="mt-0.5 text-sm text-muted-foreground" data-testid="segments-summary" aria-live="polite">
          {summary}
        </p>
      </div>
      {shown !== null && (
        <div className="flex flex-wrap items-center gap-2">
          {updatedAt !== null && <Updated at={updatedAt} />}
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            title="Read segments-manager's database now"
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
          >
            <RefreshCw aria-hidden className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
            Refresh
          </button>
          <button
            type="button"
            onClick={onCsv}
            disabled={shown === 0}
            title={`Download the ${shown} segment${shown === 1 ? "" : "s"} shown, as CSV`}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
          >
            <Download aria-hidden className="h-3.5 w-3.5" />
            CSV of {shown} shown
          </button>
        </div>
      )}
    </div>
  );
}
