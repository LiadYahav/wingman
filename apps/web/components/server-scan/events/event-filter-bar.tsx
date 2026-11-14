"use client";

import { Combobox } from "@/components/ui/combobox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  ALL_ACTORS, CUSTOM_RANGE, DATE_HINT, RANGE_PRESETS, actorOptions, isBadDate, type EventFilters,
} from "@/lib/server-scan/event-filters";
import { WRITTEN_EVENT_TYPES } from "@/lib/server-scan/events";
import type { EventActor } from "@/types/server-scan-events";

/**
 * The Events page's four filters, in server-scan's order and words
 * (team-redbull/server-scan at 92146d3, `EventsPage.tsx` and
 * `ActorCombobox.tsx`, decision 18): Event type, Server, User, Time range,
 * and the custom range's two bounds. Each change sets one URL parameter.
 */

/** A dropdown's "All" / "Any time", which sets nothing. */
const NONE = "__none__";

const FIELD = "flex min-w-48 flex-1 flex-col gap-1 text-xs font-medium text-muted-foreground";
const INPUT =
  "h-8 w-full rounded-lg border bg-card px-2.5 text-sm font-normal text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 aria-invalid:border-destructive";

const TYPE_ITEMS = [{ value: NONE, label: "All" }, ...WRITTEN_EVENT_TYPES.map((t) => ({ value: t as string, label: t as string }))];
const RANGE_ITEMS = [
  { value: NONE, label: "Any time" },
  ...RANGE_PRESETS.map((p) => ({ value: p.value as string, label: p.label as string })),
  { value: CUSTOM_RANGE, label: "Custom" },
];

function Dropdown({
  id,
  label,
  items,
  value,
  onChange,
}: {
  id: string;
  label: string;
  items: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className={FIELD}>
      <label htmlFor={id}>{label}</label>
      <Select items={items} value={value || NONE} onValueChange={(v) => onChange(v === NONE || v === null ? "" : String(v))}>
        <SelectTrigger id={id} className="w-full bg-card" data-testid={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false}>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** A custom bound, typed in Israel's time; one that is not a date is marked and not sent. */
function DateBound({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  const bad = isBadDate(value);
  return (
    <div className={FIELD}>
      <label htmlFor={id}>{label} (Israel time)</label>
      <input id={id} type="text" value={value} placeholder={DATE_HINT} aria-invalid={bad} autoComplete="off" onChange={(e) => onChange(e.target.value)} className={INPUT} />
      {bad && <span className="font-normal text-destructive">Use {DATE_HINT}</span>}
    </div>
  );
}

export function EventFilterBar({
  filters,
  actors,
  onChange,
}: {
  filters: EventFilters;
  /** The User filter's choices, busiest first. */
  actors: readonly EventActor[];
  onChange: (key: keyof EventFilters, value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-start gap-3" data-testid="ss-events-filters">
      <Dropdown id="ss-events-type" label="Event type" items={TYPE_ITEMS} value={filters.eventType} onChange={(v) => onChange("eventType", v)} />
      <div className={FIELD}>
        <label htmlFor="ss-events-server">Server</label>
        <input
          id="ss-events-server"
          type="text"
          value={filters.server}
          placeholder="Server name"
          title="A part of the server's name, in any case"
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => onChange("server", e.target.value)}
          className={INPUT}
        />
      </div>
      <div className={FIELD}>
        <label htmlFor="ss-events-actor">User</label>
        <Combobox
          id="ss-events-actor"
          options={actorOptions(actors)}
          value={filters.actorId || null}
          onValueChange={(v) => onChange("actorId", v === ALL_ACTORS || v === null ? "" : v)}
          placeholder="All"
          searchPlaceholder="Name or id"
          emptyMessage="No matching user"
          className="bg-card"
          data-testid="ss-events-actor"
        />
      </div>
      <Dropdown id="ss-events-range" label="Time range" items={RANGE_ITEMS} value={filters.range} onChange={(v) => onChange("range", v)} />
      {filters.range === CUSTOM_RANGE && (
        <>
          <DateBound id="ss-events-from" label="From" value={filters.from} onChange={(v) => onChange("from", v)} />
          <DateBound id="ss-events-to" label="To (exclusive)" value={filters.to} onChange={(v) => onChange("to", v)} />
        </>
      )}
    </div>
  );
}
