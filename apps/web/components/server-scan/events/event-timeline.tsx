"use client";

import { Fragment, useState } from "react";
import Link from "next/link";
import { formatRelative, formatTimestamp } from "@/lib/server-scan/datetime";
import { eventTone } from "@/lib/server-scan/events";
import { serverHref } from "@/lib/server-scan/server-page";
import { cn } from "@/lib/utils";
import type { AuditEvent } from "@/types/server-scan-record";
import { pill } from "../server-badges";
import { ActorCell, EventDetails, Transition, eventToneClass } from "./event-details";

/**
 * A newest-first table of audit events, as server-scan's `EventTimeline.tsx`
 * (team-redbull/server-scan at 92146d3, decision 18): Server (the Events
 * page's; a server's History is that server), What happened, When, User, and
 * a row's details in their own full-width row, so opening one never moves
 * another column.
 */

/** The event's server: its page here; "Unknown server" for one since pruned (its id on hover); "-" for none. */
function ServerCell({ event }: { event: AuditEvent }) {
  if (!event.server_id) return <span className="text-muted-foreground">-</span>;
  if (!event.server_name) {
    return (
      <span title={event.server_id} className="text-muted-foreground">
        Unknown server
      </span>
    );
  }
  return (
    <Link href={serverHref(event.server_id)} className="font-medium wrap-anywhere text-primary hover:underline">
      {event.server_name}
    </Link>
  );
}

interface RowProps {
  event: AuditEvent;
  open: boolean;
  onToggle: () => void;
  showServer: boolean;
}

function EventRow({ event, open, onToggle, showServer }: RowProps) {
  return (
    <Fragment>
      <tr className="border-t align-top" data-testid="ss-event" data-type={event.event_type}>
        {showServer && (
          <td className="px-3 py-2 text-xs" data-testid="ss-event-server">
            <ServerCell event={event} />
          </td>
        )}
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
          <td colSpan={showServer ? 4 : 3} className="bg-muted/40 px-3 py-2">
            <EventDetails event={event} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

/** The events of one page; `label` names the table (the page it is on). */
export function EventTimeline({ events, label, showServer = false }: { events: AuditEvent[]; label: string; showServer?: boolean }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className={cn("w-full table-fixed text-left text-sm", showServer && "min-w-[48rem]")} aria-label={label}>
        <colgroup>
          {showServer && <col className="w-64" />}
          <col />
          <col className="w-56" />
          <col className="w-56" />
        </colgroup>
        <thead className="bg-muted/50 text-xs text-muted-foreground">
          <tr>
            {showServer && <th className="px-3 py-2 font-medium">Server</th>}
            <th className="px-3 py-2 font-medium">What happened</th>
            <th className="px-3 py-2 font-medium">When</th>
            <th className="px-3 py-2 font-medium">User</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <EventRow key={event.id} event={event} open={open.has(event.id)} onToggle={() => toggle(event.id)} showServer={showServer} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
