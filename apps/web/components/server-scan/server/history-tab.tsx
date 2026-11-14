"use client";

import { Fragment, useState } from "react";
import { KeyRound } from "lucide-react";
import { ProblemList } from "@/components/common/problem-list";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useServerScanHistory } from "@/lib/api/server-scan";
import { formatRelative, formatTimestamp } from "@/lib/server-scan/datetime";
import { eventTone, historyPager } from "@/lib/server-scan/events";
import { cn } from "@/lib/utils";
import type { AuditEvent, ServerRecord } from "@/types/server-scan-record";
import { pill } from "../server-badges";
import { ActorCell, EventDetails, Transition, eventToneClass } from "./event-details";

/**
 * The History tab, as server-scan's `HistoryTab.tsx`, `EventList.tsx` and
 * `EventTimeline.tsx` (team-redbull/server-scan at 92146d3, decision 18;
 * docs/notes/2026-11-13-server-scan-area-api.md §9.1): the server's audit
 * trail, newest first, 50 a page. Read with server-scan's auditor token;
 * without it here, one line says so and nothing is asked (§9.5).
 */

function EventRow({ event, open, onToggle }: { event: AuditEvent; open: boolean; onToggle: () => void }) {
  return (
    <Fragment>
      <tr className="border-t align-top" data-testid="ss-event" data-type={event.event_type}>
        <td className="px-3 py-2">
          <span className={cn(pill, "px-2", eventToneClass(eventTone(event.event_type)))}>{event.event_type}</span>
          <Transition event={event} />
          <button
            type="button"
            aria-expanded={open}
            onClick={onToggle}
            className="mt-1 block text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:underline"
          >
            {open ? "▾ Hide details" : "▸ Details"}
          </button>
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-xs text-muted-foreground">
          <time dateTime={event.created_at} title={formatRelative(event.created_at)}>
            {formatTimestamp(event.created_at)}
          </time>
        </td>
        <td className="px-3 py-2 text-xs">
          <ActorCell actor={event.actor} />
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={3} className="bg-muted/40 px-3 py-2">
            <EventDetails event={event} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

/** A newest-first table of events: What happened, When, User; a row's details in their own full-width row. */
function Timeline({ events }: { events: AuditEvent[] }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full table-fixed text-left text-sm" aria-label="History">
        <colgroup>
          <col />
          <col className="w-56" />
          <col className="w-56" />
        </colgroup>
        <thead className="bg-muted/50 text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">What happened</th>
            <th className="px-3 py-2 font-medium">When</th>
            <th className="px-3 py-2 font-medium">User</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <EventRow key={event.id} event={event} open={open.has(event.id)} onToggle={() => toggle(event.id)} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Pages({ serverId }: { serverId: string }) {
  const query = useServerScanHistory(serverId, true);
  const [index, setIndex] = useState(0);
  if (query.isPending) {
    return (
      <div className="space-y-2" aria-busy="true" data-testid="ss-history-loading">
        <p className="text-sm text-muted-foreground">Loading history…</p>
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (query.isError) return <ProblemList error={query.error} title="The history could not be read from server-scan" />;
  const pages = query.data.pages;
  if ((pages[0]?.items.length ?? 0) === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="ss-history-empty">
        No events recorded.
      </p>
    );
  }
  const shown = pages[index] ?? pages[0];
  const { pageCount, canNext } = historyPager(pages, index, query.hasNextPage);
  const next = () => {
    if (index + 1 < pages.length) setIndex(index + 1);
    else void query.fetchNextPage().then(() => setIndex(index + 1));
  };
  return (
    <div className="space-y-3">
      <Timeline events={shown.items} />
      <div className="flex items-center gap-3" data-testid="ss-history-pager">
        <button type="button" disabled={index <= 0} onClick={() => setIndex(index - 1)} className={buttonVariants({ variant: "outline", size: "sm" })}>
          Previous
        </button>
        <span className="text-sm text-muted-foreground">
          Page {index + 1} of {pageCount}
        </span>
        <button type="button" disabled={!canNext || query.isFetchingNextPage} onClick={next} className={buttonVariants({ variant: "outline", size: "sm" })}>
          {query.isFetchingNextPage ? "Loading…" : "Next"}
        </button>
      </div>
    </div>
  );
}

export function HistoryTab({ record }: { record: ServerRecord }) {
  return (
    <div className="rounded-xl border bg-card p-5" data-testid="ss-history">
      {record.history_available ? (
        <Pages serverId={record.id} />
      ) : (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="ss-history-off">
          <KeyRound aria-hidden className="h-4 w-4 shrink-0" />
          {record.history_detail ?? "History is not set up in this deployment."}
        </p>
      )}
    </div>
  );
}
