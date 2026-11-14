"use client";

import { KeyRound } from "lucide-react";
import { useServerScanHistory } from "@/lib/api/server-scan";
import type { ServerRecord } from "@/types/server-scan-record";
import { EventList } from "../events/event-list";

/**
 * The History tab, as server-scan's `HistoryTab.tsx`, `EventList.tsx` and
 * `EventTimeline.tsx` (team-redbull/server-scan at 92146d3, decision 18;
 * docs/notes/2026-11-13-server-scan-area-api.md §9.1): the server's audit
 * trail, newest first, 50 a page. Read with server-scan's auditor token;
 * without it here, one line says so and nothing is asked (§9.5).
 */

function Pages({ serverId }: { serverId: string }) {
  const query = useServerScanHistory(serverId, true);
  return (
    <EventList
      query={query}
      label="History"
      loading="Loading history…"
      problem="The history could not be read from server-scan"
      testId="ss-history"
    />
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
