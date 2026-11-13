"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { CheckItem } from "@/components/data-table/check-item";
import type { ClusterFacets, ClusterOption } from "@/lib/server-scan/rows";

/**
 * The MCE, hosted-cluster and UPI-cluster filter, read off the fleet itself
 * (`clusterFacets`), as server-scan's (team-redbull/server-scan at 92146d3,
 * `frontend/src/features/inventory/ClusterSidebar.tsx`, decision 18): three
 * lists of checkboxes with counts, each hidden while empty, a find box above
 * them when they hold more than 8 entries, and a way to fold it away.
 *
 * It sits inside the page, not in the area's sidebar: it is this page's
 * filter, its counts follow the page's other filters, and the area's sidebar
 * is the navigation between pages.
 */

type ParamKey = "mce" | "cluster";

function Section({
  title,
  options,
  selected,
  paramKey,
  onToggle,
}: {
  title: string;
  options: ClusterOption[];
  selected: string[];
  paramKey: ParamKey;
  onToggle: (key: ParamKey, value: string) => void;
}) {
  if (options.length === 0) return null;
  return (
    <section aria-label={title}>
      <h2 className="px-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {title} <span className="text-muted-foreground/70">({options.length})</span>
      </h2>
      <div className="mt-1 space-y-px">
        {options.map((option) => (
          <CheckItem key={option.name} checked={selected.includes(option.name)} onToggle={() => onToggle(paramKey, option.name)} className="text-xs">
            <span className="flex items-center justify-between gap-3" title={option.mce ? `${option.name} · ${option.mce}` : option.name}>
              <span className="min-w-0 truncate">{option.name}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground">{option.count}</span>
            </span>
          </CheckItem>
        ))}
      </div>
    </section>
  );
}

export function ClusterSidebar({
  facets,
  mce,
  cluster,
  onToggle,
}: {
  facets: ClusterFacets;
  mce: string[];
  cluster: string[];
  onToggle: (key: ParamKey, value: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(true);
  const { mces, hosted, upi } = facets;
  const entries = mces.length + hosted.length + upi.length;
  if (entries === 0) return null;

  if (!open) {
    const ticked = mce.length + cluster.length;
    return (
      <button
        type="button"
        aria-expanded={false}
        onClick={() => setOpen(true)}
        className="inline-flex shrink-0 items-center gap-1 self-start rounded-lg border bg-card px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        Clusters{ticked > 0 ? ` (${ticked})` : ""}
        <ChevronRight aria-hidden className="h-3.5 w-3.5" />
      </button>
    );
  }

  const q = query.trim().toLowerCase();
  const narrow = (options: ClusterOption[]) => (q ? options.filter((o) => o.name.toLowerCase().includes(q)) : options);
  return (
    <aside
      aria-label="Cluster filters"
      className="sticky top-4 flex max-h-[calc(100vh-6rem)] w-56 shrink-0 flex-col gap-3 self-start overflow-hidden rounded-xl border bg-card p-2.5"
    >
      <div className="shrink-0 space-y-2">
        <button
          type="button"
          aria-expanded
          onClick={() => setOpen(false)}
          className="inline-flex items-center gap-1 px-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
          Hide filters
        </button>
        {entries > 8 && (
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find an MCE or cluster…"
            aria-label="Find an MCE or cluster"
            className="w-full rounded-md border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        )}
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
        <Section title="MCE" options={narrow(mces)} selected={mce} paramKey="mce" onToggle={onToggle} />
        <Section title="Hosted clusters" options={narrow(hosted)} selected={cluster} paramKey="cluster" onToggle={onToggle} />
        <Section title="UPI clusters" options={narrow(upi)} selected={cluster} paramKey="cluster" onToggle={onToggle} />
      </div>
    </aside>
  );
}
