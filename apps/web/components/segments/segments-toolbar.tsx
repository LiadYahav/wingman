"use client";

import type { ReactNode } from "react";
import { Funnel, Search, X } from "lucide-react";
import { STATUS_TABS, type StatusTab } from "@/lib/segments/view";
import { cn } from "@/lib/utils";

const TAB_LABELS: Record<StatusTab, string> = { all: "All", available: "Available", allocated: "Allocated" };

const pill = (active: boolean) =>
  cn(
    "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50",
    active
      ? "border-primary bg-primary text-primary-foreground"
      : "border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground"
  );

/** A labelled row of toggles: Status, Site. */
function PillRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}:</span>
      {children}
    </div>
  );
}

/**
 * The original's search: cluster, EPG, VLAN ID, segment or site. Controlled by
 * the page's draft (`useSearchDraft`), which reaches the URL once typing
 * pauses, or at once on Enter.
 */
export function SegmentSearch({ value, onChange, onCommit }: { value: string; onChange: (q: string) => void; onCommit: () => void }) {
  return (
    <div className="relative w-full sm:w-96">
      <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <input
        type="search"
        aria-label="Search segments"
        placeholder="Search cluster, EPG, VLAN ID, or segment…"
        value={value}
        autoComplete="off"
        spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onCommit();
          if (e.key === "Escape" && value) onChange("");
        }}
        className="w-full rounded-lg border bg-card py-1.5 pl-8 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 [&::-webkit-search-cancel-button]:hidden"
      />
      {value && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => onChange("")}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

export function StatusTabs({
  value,
  counts,
  onChange,
}: {
  value: StatusTab;
  counts: Record<StatusTab, number> | null;
  onChange: (tab: StatusTab) => void;
}) {
  return (
    <PillRow label="Status">
      {STATUS_TABS.map((tab) => (
        <button key={tab} type="button" aria-pressed={value === tab} onClick={() => onChange(tab)} className={pill(value === tab)}>
          {TAB_LABELS[tab]}
          {counts && <span className="tabular-nums opacity-70">{counts[tab]}</span>}
        </button>
      ))}
    </PillRow>
  );
}

/** segments-manager's sites, and All; a site the URL names that the list lacks is kept, so it can be cleared. */
export function SiteFilter({ sites, value, onChange }: { sites: string[]; value: string | null; onChange: (site: string | null) => void }) {
  const shown = value !== null && !sites.some((s) => s.toLowerCase() === value.toLowerCase()) ? [...sites, value] : sites;
  return (
    <PillRow label="Site">
      <button type="button" aria-pressed={value === null} onClick={() => onChange(null)} className={pill(value === null)}>
        All
      </button>
      {shown.map((site) => {
        const active = value !== null && site.toLowerCase() === value.toLowerCase();
        return (
          <button key={site} type="button" aria-pressed={active} onClick={() => onChange(active ? null : site)} className={pill(active)}>
            {site}
          </button>
        );
      })}
    </PillRow>
  );
}

/** Only the rows where segments-manager disagrees with a cluster file; shown while any does, or while on. */
export function MismatchToggle({ count, value, onChange }: { count: number; value: boolean; onChange: (on: boolean) => void }) {
  if (count === 0 && !value) return null;
  return (
    <button
      type="button"
      aria-pressed={value}
      onClick={() => onChange(!value)}
      className={cn(
        pill(value),
        !value && "border-status-warning/40 text-status-warning-fg hover:border-status-warning hover:text-status-warning-fg"
      )}
    >
      Disagrees with Git
      <span className="tabular-nums opacity-70">{count}</span>
    </button>
  );
}

/**
 * A filter shown as a chip that removes it: one the toolbar has no control
 * for (the cluster page's link), or a column's filter, so it stays in sight
 * when its column is hidden.
 */
export function FilterChip({
  label,
  value,
  column = false,
  onRemove,
}: {
  label: string;
  value: string;
  /** A column's filter: marked with the header's funnel. */
  column?: boolean;
  onRemove: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onRemove}
      aria-label={column ? `Remove the ${label} column filter: ${value}` : `Remove the ${label.toLowerCase()} filter ${value}`}
      data-testid={column ? "column-filter-chip" : undefined}
      className="inline-flex items-center gap-1 rounded-full border border-primary/40 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/20"
    >
      {column && <Funnel aria-hidden className="h-3 w-3 fill-current" />}
      {label}: <span className={column ? undefined : "font-mono"}>{value}</span>
      <X aria-hidden className="h-3 w-3" />
    </button>
  );
}
