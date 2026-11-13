"use client";

import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SEGMENTS_REFRESH_MS } from "@/lib/api/segments";
import type { Connection } from "@/lib/segments/connection";
import { updatedAgo } from "@/lib/segments/sites";
import { cn } from "@/lib/utils";

/**
 * The original's online/offline state, as a dot: green while segments-manager
 * answered the last refresh, red (its tooltip says why) while it did not and
 * the page shows the last good data.
 */
function ConnectionDot({ connection }: { connection: Connection }) {
  const online = connection.state === "online";
  return (
    <Tooltip>
      <TooltipTrigger
        aria-label={connection.label}
        data-testid="segments-connection"
        data-state={connection.state}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <span aria-hidden className={cn("h-2 w-2 rounded-full", online ? "bg-status-ready" : "bg-destructive animate-pulse")} />
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{connection.label}</TooltipContent>
    </Tooltip>
  );
}

/** "● Updated 12 s ago · every 30 s", ticking while the page is open. */
function Updated({ at, connection }: { at: number; connection: Connection }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(timer);
  }, []);
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <ConnectionDot connection={connection} />
      <span data-testid="segments-updated">
        Updated {updatedAgo(at, Math.max(now, at))} · every {SEGMENTS_REFRESH_MS / 1000} s
      </span>
    </span>
  );
}

/**
 * The exports of exactly the rows shown, in the shown columns: a CSV, or an
 * Excel file of the same rows and columns, written in the browser.
 */
function Exports({ shown, exporting, onCsv, onExcel }: { shown: number; exporting: boolean; onCsv: () => void; onExcel: () => void }) {
  const what = `the ${shown} segment${shown === 1 ? "" : "s"} shown`;
  const joined = (side: "left" | "right") =>
    cn(buttonVariants({ variant: "outline", size: "sm" }), side === "left" ? "gap-1.5 rounded-r-none" : "-ml-px rounded-l-none");
  return (
    <div role="group" aria-label={`Download ${what}`} className="inline-flex items-center gap-1.5">
      <span className="text-xs text-muted-foreground">Download {shown} shown as</span>
      <span className="inline-flex">
        <button type="button" onClick={onCsv} disabled={shown === 0} aria-label={`CSV of ${shown} shown`} title={`Download ${what}, as CSV`} className={joined("left")}>
          <Download aria-hidden className="h-3.5 w-3.5" />
          CSV
        </button>
        <button
          type="button"
          onClick={onExcel}
          disabled={shown === 0 || exporting}
          aria-label={`Excel of ${shown} shown`}
          title={`Download ${what}, as an Excel file (.xlsx)`}
          className={joined("right")}
        >
          Excel
        </button>
      </span>
    </div>
  );
}

/**
 * The title, what is shown, and the page's actions: Refresh (read
 * segments-manager's database now) and the exports of exactly the rows shown.
 */
export function SegmentsHeader({
  summary,
  updatedAt,
  connection,
  shown,
  refreshing,
  onRefresh,
  exporting,
  onCsv,
  onExcel,
}: {
  summary: string;
  /** When the list was last read; `null` before the first read. */
  updatedAt: number | null;
  /** Whether segments-manager answered the last refresh. */
  connection: Connection;
  /** How many rows the exports hold; `null` hides the actions (nothing to act on). */
  shown: number | null;
  refreshing: boolean;
  onRefresh: () => void;
  /** An Excel file is being written. */
  exporting: boolean;
  onCsv: () => void;
  onExcel: () => void;
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
          {updatedAt !== null && <Updated at={updatedAt} connection={connection} />}
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
          <Exports shown={shown} exporting={exporting} onCsv={onCsv} onExcel={onExcel} />
        </div>
      )}
    </div>
  );
}
