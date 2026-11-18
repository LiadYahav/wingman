"use client";

import { createColumnHelper, type ColumnDef } from "@tanstack/react-table";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { useServerRefresh } from "@/features/server-scan/api/server-scan";
import { FETCHING, FETCH_LABEL, FETCH_TITLE, fetchControl, fetchFailure, fetchedToast, rowFetchLabel } from "@/features/server-scan/lib/refresh";
import { cn } from "@/lib/utils";
import type { ServerRecord } from "@/features/server-scan/types/server-scan-record";
import type { ServerRow } from "@/features/server-scan/types/server-scan-servers";

/**
 * Fetch now (ADR-0048's v6.6.0 amendment): server-scan's button on a
 * server's page (`RefreshButton.tsx`, v6.5.0) and on every Servers row
 * (`RowRefreshButton.tsx`, v6.6.0), in Wingman's design. Each reads the one
 * server from its vendor manager now through day1, sent once (never
 * retried); while day1 waits, which can be minutes, the icon turns and the
 * button is busy. Greyed with day1's line when Wingman holds no admin token.
 *
 * What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
 */

const BUTTON =
  "inline-flex items-center justify-center rounded-md border text-muted-foreground outline-none transition-colors hover:border-foreground/30 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 disabled:cursor-wait disabled:opacity-60";
const OFF = "cursor-not-allowed opacity-40 hover:border-border hover:text-muted-foreground";

function Spinner({ busy }: { busy: boolean }) {
  return <RefreshCw aria-hidden className={cn("h-3.5 w-3.5", busy && "motion-safe:animate-spin")} />;
}

/** The server page's button, beside the BMC's: it says what it found, and why it failed inline too. */
export function FetchNowButton({ record }: { record: ServerRecord }) {
  const refresh = useServerRefresh();
  const control = fetchControl(record.refresh_available, record.refresh_detail, FETCH_LABEL, FETCH_TITLE);
  const fetchNow = () => {
    if (control.off) return;
    const before = record.revision;
    refresh.mutate(record.id, {
      onSuccess: (fresh) => {
        const { title, description } = fetchedToast(fresh, before);
        toast.success(title, { description });
      },
      onError: () => toast.error("Fetch failed", { description: record.name }),
    });
  };
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <button
        type="button"
        title={control.title}
        aria-label={control.label}
        aria-disabled={control.off || undefined}
        aria-busy={refresh.isPending || undefined}
        disabled={refresh.isPending}
        onClick={fetchNow}
        data-testid="ss-fetch-now"
        className={cn(BUTTON, "h-7 gap-1.5 px-2.5 text-xs font-medium", control.off && OFF)}
      >
        <Spinner busy={refresh.isPending} />
        {refresh.isPending ? FETCHING : "Fetch now"}
      </button>
      {/* Inline as well as the toast: the reason ("run its collector job instead") outlasts a toast. */}
      {refresh.isError && (
        <span role="alert" data-testid="ss-fetch-now-error" className="text-xs text-destructive">
          {fetchFailure(refresh.error)}
        </span>
      )}
    </span>
  );
}

/** A row's button: icon only, first in the row, its toast naming the server. */
function RowFetchNow({ row, available, detail }: { row: ServerRow; available: boolean; detail: string | null }) {
  const refresh = useServerRefresh();
  const control = fetchControl(available, detail, rowFetchLabel(row.name));
  const fetchNow = () => {
    if (control.off) return;
    refresh.mutate(row.id, {
      onSuccess: (fresh) => {
        const { title, description } = fetchedToast(fresh);
        toast.success(title, { description });
      },
      onError: (error) => toast.error("Fetch failed", { description: `${row.name}: ${fetchFailure(error)}` }),
    });
  };
  return (
    <button
      type="button"
      title={refresh.isPending ? FETCHING : control.title}
      aria-label={control.label}
      aria-disabled={control.off || undefined}
      aria-busy={refresh.isPending || undefined}
      disabled={refresh.isPending}
      onClick={fetchNow}
      data-testid="ss-row-fetch-now"
      className={cn(BUTTON, "h-6 w-6", control.off && OFF)}
    >
      <Spinner busy={refresh.isPending} />
    </button>
  );
}

/**
 * The table's first column, as server-scan's (v6.6.0): each row's Fetch now,
 * its header for screen readers only. `available` and `detail` are day1's
 * `refresh_available` and `refresh_detail`.
 */
export function fetchNowColumn(available: boolean, detail: string | null): ColumnDef<ServerRow, never> {
  return createColumnHelper<ServerRow>().display({
    id: "refresh",
    header: () => <span className="sr-only">Fetch now</span>,
    meta: { label: "Fetch now", className: "w-px whitespace-nowrap px-2" },
    cell: (c) => <RowFetchNow row={c.row.original} available={available} detail={detail} />,
  }) as ColumnDef<ServerRow, never>;
}
