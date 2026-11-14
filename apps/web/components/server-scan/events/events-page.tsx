"use client";

import { useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { Info, KeyRound } from "lucide-react";
import { Hint } from "@/components/common/hint";
import { useDebounced } from "@/hooks/use-debounced";
import { useServerScanEventActors, useServerScanEvents } from "@/lib/api/server-scan-events";
import { errorMessages } from "@/lib/api-client";
import { filtersToParams, readEventFilters, withFilter, type EventFilters } from "@/lib/server-scan/event-filters";
import { Blocked, isBlocked, needsAuditorToken } from "../blocked";
import { EventFilterBar } from "./event-filter-bar";
import { EventList } from "./event-list";

/** What the page is, in the heading's tooltip. */
const ABOUT =
  "server-scan's audit trail of every server and of the platform itself: what changed, when, and who. Read with server-scan's auditor token. A change made in Wingman reaches server-scan with its admin token, so it reads API token (admin); Wingman's own log names the person.";

/** As server-scan's page: a typed filter is asked for 300 ms after the last key. */
const TYPING_MS = 300;

/**
 * The filters as the URL holds them, and a setter that replaces the URL's
 * history entry (Next keeps `useSearchParams` in step), as server-scan's page.
 */
function useEventFilters(): [EventFilters, (key: keyof EventFilters, value: string) => void] {
  const searchParams = useSearchParams();
  const filters = useMemo(() => readEventFilters(searchParams), [searchParams]);
  const setFilter = useCallback((key: keyof EventFilters, value: string) => {
    const { pathname, search } = window.location;
    const href = withFilter(pathname, search, key, value);
    if (href !== `${pathname}${search}`) window.history.replaceState(null, "", href);
  }, []);
  return [filters, setFilter];
}

/** The one line the page shows without server-scan's auditor token (§14.5). */
function AuditorOff({ error }: { error: unknown }) {
  return (
    <p className="flex items-center gap-2 rounded-xl border bg-card p-5 text-sm text-muted-foreground" data-testid="ss-events-off">
      <KeyRound aria-hidden className="h-4 w-4 shrink-0" />
      {errorMessages(error)[0] ?? "Events is not set up in this deployment."}
    </p>
  );
}

/**
 * The Server Scan area's Events page (ADR-0048's 3.31.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §14): server-scan's audit
 * trail of the fleet, newest first, with its four filters in the URL, 50 a
 * page over its cursors, each server linked to its page here. Read on open
 * and again when opened after 30 seconds; never polled.
 */
export function EventsPage() {
  const [filters, setFilter] = useEventFilters();
  const server = useDebounced(filters.server, TYPING_MS);
  const from = useDebounced(filters.from, TYPING_MS);
  const to = useDebounced(filters.to, TYPING_MS);
  const { eventType, actorId, range } = filters;
  // A preset's `since` is fixed when a filter changes, so the list's key stays put meanwhile.
  const params = useMemo(
    () => filtersToParams({ server, eventType, actorId, range, from, to }),
    [server, eventType, actorId, range, from, to]
  );
  const events = useServerScanEvents(params);
  const actors = useServerScanEventActors();
  const errors = [events.error, actors.error];
  const auditorOff = errors.find(needsAuditorToken);
  const blocking = errors.find(isBlocked);
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6 lg:p-8">
      <header>
        <div className="flex items-center gap-1">
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            Events
          </h1>
          <Hint hint={ABOUT} label="About Events" testId="ss-events-about">
            <Info aria-hidden className="h-4 w-4 text-muted-foreground" />
          </Hint>
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground">The audit trail, newest first. Times are Israel time.</p>
      </header>
      {auditorOff !== undefined ? (
        <AuditorOff error={auditorOff} />
      ) : blocking !== undefined ? (
        <Blocked error={blocking} />
      ) : (
        <>
          <EventFilterBar filters={filters} actors={actors.data?.items ?? []} onChange={setFilter} />
          <EventList
            key={JSON.stringify(params)}
            query={events}
            label="Events"
            loading="Loading events…"
            problem="The events could not be read from server-scan"
            testId="ss-events"
            showServer
          />
        </>
      )}
    </div>
  );
}
