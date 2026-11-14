"use client";

import { Fragment, useState } from "react";
import { formatRelative, formatTimestamp } from "@/lib/server-scan/datetime";
import { eventTone } from "@/lib/server-scan/events";
import { cn } from "@/lib/utils";
import type { AuditEvent } from "@/types/server-scan-record";
import { pill } from "../server-badges";
import { ActorCell, EventDetails, Transition, eventToneClass } from "./event-details";

/**
 * A newest-first table of audit events, as server-scan's `EventTimeline.tsx`
 * (team-redbull/server-scan at 92146d3, decision 18): What happened, When,
 * User, and a row's details in their own full-width row, so opening one never
 * moves another column.
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

/** The events of one page; `label` names the table (the page it is on). */
export function EventTimeline({ events, label }: { events: AuditEvent[]; label: string }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full table-fixed text-left text-sm" aria-label={label}>
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
