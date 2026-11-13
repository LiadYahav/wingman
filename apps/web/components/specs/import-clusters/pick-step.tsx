"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileWarning, Link2, Search, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { OWNER_KEYS, type OwnerKey } from "@/lib/clusters";
import { Combobox } from "@/components/ui/combobox";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { EmptyState, NoMatches } from "@/components/common/empty-state";
import { CheckToggle } from "@/components/specs/import-clusters/check-toggle";
import { cn } from "@/lib/utils";
import type { ClusterStatus } from "@/types";

/** One import takes at most this many clusters (day1's `MAX_IMPORT`, ADR-0037). */
export const MAX_IMPORT = 50;
/** Rows listed at once; a narrower search shows the rest. */
const MAX_SHOWN = 200;

export interface PickFilters {
  search: string;
  site: string;
  mce: string;
  owner: Record<OwnerKey, string>;
}

export const NO_FILTERS: PickFilters = { search: "", site: "", mce: "", owner: { merkaz: "", anaf: "", mador: "" } };

/** A cluster file, wherever it is: names are unique, but a pick pins its site and MCE. */
export const pickKey = (c: { name: string; site: string; mce: string }) => `${c.site}/${c.mce}/${c.name}`;

const ALL = "__all__";

function matches(c: ClusterStatus, f: PickFilters): boolean {
  const q = f.search.trim().toLowerCase();
  if (q && !c.name.toLowerCase().includes(q)) return false;
  if (f.site && c.site !== f.site) return false;
  if (f.mce && c.mce !== f.mce) return false;
  const owner = c.owner ?? {};
  return OWNER_KEYS.every((k) => !f.owner[k].trim() || owner[k] === f.owner[k].trim());
}

/** `merkaz 1234 · anaf 56 · mador 7`, or that the file names none. */
function OwnerLine({ owner }: { owner: Record<string, string> | undefined }) {
  const parts = OWNER_KEYS.filter((k) => owner?.[k]).map((k) => `${k} ${owner![k]}`);
  return <span>{parts.length > 0 ? parts.join(" · ") : "no owner"}</span>;
}

function PickRow({
  cluster,
  flavor,
  checked,
  full,
  onToggle,
}: {
  cluster: ClusterStatus;
  flavor: string;
  checked: boolean;
  /** Fifty are picked: this one can't be added. */
  full: boolean;
  onToggle: (checked: boolean) => void;
}) {
  const onFlavor = cluster.spec_name === flavor;
  const disabled = onFlavor || (full && !checked);
  return (
    <CheckToggle
      checked={checked}
      onCheckedChange={onToggle}
      disabled={disabled}
      data-testid={`import-pick-${cluster.name}`}
      className={cn(
        "px-3 py-2.5 transition-colors",
        checked ? "bg-primary/[0.04]" : !disabled && "hover:bg-muted/40",
        onFlavor && "opacity-70"
      )}
    >
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-sm font-medium break-all">{cluster.name}</span>
        {onFlavor ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
            <Link2 className="h-3 w-3" aria-hidden />On this flavor
          </span>
        ) : cluster.spec_name ? (
          <span className="rounded-full bg-status-warning/10 px-2 py-0.5 text-[11px] font-medium text-status-warning-fg break-all">
            Follows {cluster.spec_name}
          </span>
        ) : null}
        {cluster.problems.length > 0 && (
          <span
            title={cluster.problems.join("\n")}
            className="inline-flex items-center gap-1 rounded-full bg-status-error/10 px-1.5 py-0.5 text-[11px] font-medium text-status-error-fg"
          >
            <FileWarning className="h-3 w-3" aria-hidden />Unreadable
          </span>
        )}
      </span>
      <span className="mt-0.5 block text-xs text-muted-foreground break-all">
        {cluster.site} / {cluster.mce} · <OwnerLine owner={cluster.owner} />
      </span>
    </CheckToggle>
  );
}

/**
 * Step one: pick the clusters to import, from every cluster file in the day1
 * repo. Clusters already on this flavor are listed, marked, and can't be
 * picked; one that follows another flavor can (the preview asks to move it).
 */
export function PickStep({
  flavor,
  filters,
  onFiltersChange,
  picked,
  onPickedChange,
}: {
  flavor: string;
  filters: PickFilters;
  onFiltersChange: (filters: PickFilters) => void;
  picked: Map<string, ClusterStatus>;
  onPickedChange: (picked: Map<string, ClusterStatus>) => void;
}) {
  const { data: clusters, isLoading, error } = useQuery<ClusterStatus[]>({
    queryKey: ["clusters"],
    queryFn: () => api.get<ClusterStatus[]>("/api/day1/clusters"),
    staleTime: 30_000,
  });

  const all = useMemo(() => [...(clusters ?? [])].sort((a, b) => a.name.localeCompare(b.name)), [clusters]);
  const sites = useMemo(() => [...new Set(all.map((c) => c.site))].sort(), [all]);
  const mces = useMemo(
    () => [...new Set(all.filter((c) => !filters.site || c.site === filters.site).map((c) => c.mce))].sort(),
    [all, filters.site]
  );
  const filtered = useMemo(() => all.filter((c) => matches(c, filters)), [all, filters]);
  const shown = filtered.slice(0, MAX_SHOWN);
  const onFlavorCount = all.filter((c) => c.spec_name === flavor).length;
  const shownPickable = shown.filter((c) => c.spec_name !== flavor);
  const shownPicked = shownPickable.filter((c) => picked.has(pickKey(c))).length;
  const shownKeys = new Set(shown.map(pickKey));
  const hiddenPicked = [...picked.keys()].filter((k) => !shownKeys.has(k)).length;
  const full = picked.size >= MAX_IMPORT;
  const toAdd = shownPickable.length - shownPicked;
  const allFit = picked.size + toAdd <= MAX_IMPORT;
  const filtering =
    !!filters.search || !!filters.site || !!filters.mce || OWNER_KEYS.some((k) => !!filters.owner[k]);

  const set = (patch: Partial<PickFilters>) => onFiltersChange({ ...filters, ...patch });
  const toggle = (c: ClusterStatus, on: boolean) => {
    const next = new Map(picked);
    if (on) next.set(pickKey(c), c);
    else next.delete(pickKey(c));
    onPickedChange(next);
  };
  const toggleShown = (on: boolean) => {
    const next = new Map(picked);
    for (const c of shownPickable) {
      if (on) next.set(pickKey(c), c);
      else next.delete(pickKey(c));
    }
    onPickedChange(next);
  };

  if (error) return <ProblemList error={error} title="The clusters could not be loaded" />;

  return (
    <div className="space-y-3">
      {/* Filters */}
      <div className="space-y-2" role="search" aria-label="Filter clusters">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-48 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <input
              type="search"
              value={filters.search}
              onChange={(e) => set({ search: e.target.value })}
              placeholder="Search by name"
              aria-label="Search clusters by name"
              className="h-8 w-full rounded-lg border bg-card pl-8 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
          <Combobox
            aria-label="Site"
            data-testid="import-filter-site"
            className="w-36"
            options={[{ value: ALL, label: "All sites" }, ...sites.map((s) => ({ value: s, label: s }))]}
            value={filters.site || ALL}
            onValueChange={(v) => {
              const site = !v || v === ALL ? "" : v;
              const keepMce = !filters.mce || all.some((c) => c.mce === filters.mce && (!site || c.site === site));
              set({ site, mce: keepMce ? filters.mce : "" });
            }}
            searchPlaceholder="Search sites…"
          />
          <Combobox
            aria-label="MCE"
            data-testid="import-filter-mce"
            className="w-56"
            options={[{ value: ALL, label: "All MCEs" }, ...mces.map((m) => ({ value: m, label: m }))]}
            value={filters.mce || ALL}
            onValueChange={(v) => set({ mce: !v || v === ALL ? "" : v })}
            searchPlaceholder="Search MCEs…"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">Owner</span>
          {OWNER_KEYS.map((k) => (
            <input
              key={k}
              type="text"
              inputMode="numeric"
              value={filters.owner[k]}
              onChange={(e) => set({ owner: { ...filters.owner, [k]: e.target.value } })}
              placeholder={k}
              aria-label={`Owner ${k}`}
              className="h-7 w-24 rounded-md border bg-card px-2 text-xs tabular-nums focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          ))}
          {filtering && (
            <button
              type="button"
              onClick={() => onFiltersChange(NO_FILTERS)}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <X className="h-3 w-3" aria-hidden />Clear filters
            </button>
          )}
        </div>
      </div>

      {/* The list */}
      {isLoading ? (
        <div className="divide-y rounded-lg border">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-start gap-3 px-3 py-2.5">
              <Skeleton className="h-4 w-4 shrink-0" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-3 w-72 max-w-full" />
              </div>
            </div>
          ))}
        </div>
      ) : all.length === 0 ? (
        <EmptyState title="No clusters in the day1 repo" description="There is nothing to import yet." bordered />
      ) : filtered.length === 0 ? (
        <NoMatches what="clusters" onClear={() => onFiltersChange(NO_FILTERS)} bordered />
      ) : (
        <div className="rounded-lg border" data-testid="import-pick-list">
          <div className="flex items-center justify-between gap-3 border-b bg-muted/30 px-3 py-2">
            <CheckToggle
              checked={shownPickable.length > 0 && shownPicked === shownPickable.length ? true : shownPicked > 0 ? "mixed" : false}
              onCheckedChange={toggleShown}
              disabled={shownPickable.length === 0 || (shownPicked < shownPickable.length && !allFit)}
              className="w-auto items-center text-xs font-medium"
            >
              {shownPicked === shownPickable.length && shownPickable.length > 0
                ? `Unpick the ${shownPickable.length} shown`
                : `Pick all ${shownPickable.length} shown`}
            </CheckToggle>
            <p className="text-xs text-muted-foreground" data-testid="import-pick-shown">
              {filtered.length > MAX_SHOWN
                ? `First ${MAX_SHOWN} of ${filtered.length}: narrow the search`
                : `${filtered.length} of ${all.length} cluster${all.length !== 1 ? "s" : ""}`}
              {onFlavorCount > 0 && ` · ${onFlavorCount} already on this flavor`}
            </p>
          </div>
          {full ? (
            <p className="border-b px-3 py-1.5 text-xs text-muted-foreground" data-testid="import-pick-full">
              {MAX_IMPORT} picked: one import takes at most {MAX_IMPORT} clusters.
            </p>
          ) : !allFit && toAdd > 0 ? (
            <p className="border-b px-3 py-1.5 text-xs text-muted-foreground">
              Picking all shown would make more than {MAX_IMPORT}: narrow the filters, or pick one by one.
            </p>
          ) : null}
          <div className="divide-y divide-border/60">
            {shown.map((c) => (
              <PickRow
                key={pickKey(c)}
                cluster={c}
                flavor={flavor}
                checked={picked.has(pickKey(c))}
                full={full}
                onToggle={(on) => toggle(c, on)}
              />
            ))}
          </div>
        </div>
      )}

      {hiddenPicked > 0 && (
        <p className="text-xs text-muted-foreground">
          {hiddenPicked} picked cluster{hiddenPicked !== 1 ? "s are" : " is"} not shown by the filters.
        </p>
      )}
    </div>
  );
}
