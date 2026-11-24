"use client";

import { useRef } from "react";
import { Search, X } from "lucide-react";
import { FilterPills } from "@/components/clusters/list/filter-pills";
import { cn } from "@/lib/utils";
import type { Facet, Facets, PoolFilter } from "@/lib/inventory/pool-filter";

/** A part of the name; Escape clears it, then leaves the box. */
function SearchBox({ value, onChange }: { value: string; onChange: (next: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="relative w-full sm:w-56">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <input
        ref={input}
        type="search"
        aria-label="Search the pools by name"
        placeholder="Search by name…"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== "Escape") return;
          if (value) onChange("");
          else event.currentTarget.blur();
        }}
        className="h-8 w-full rounded-lg border bg-card pl-8 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 [&::-webkit-search-cancel-button]:hidden"
      />
      {value && (
        <button
          type="button"
          aria-label="Clear the search"
          onClick={() => {
            onChange("");
            input.current?.focus();
          }}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      )}
    </div>
  );
}

const FACET_LABEL: Record<Facet, string> = { zone: "Zone", size: "Size" };

/** One part of the platform's names, `All` or one value; `""` is All. */
function FacetPills({ facet, facets, value, onChange }: { facet: Facet; facets: Facets; value: string | null; onChange: (next: string | null) => void }) {
  if (facets[facet].length === 0) return null;
  const pills = [{ value: "", label: "All" }, ...facets[facet].map(({ value: v, count }) => ({ value: v, label: v, count }))];
  return (
    <FilterPills
      label={FACET_LABEL[facet]}
      pills={pills}
      value={value ?? ""}
      onChange={(next) => onChange(next || null)}
      testId={`pool-${facet}`}
    />
  );
}

/**
 * The table's own filters, beside the InfraEnv picker: a search on the name;
 * the zone and size the platform's names carry (none when no name follows
 * the convention); only the pools with servers; and how many InfraEnvs show.
 */
export function PoolFilters({
  facets,
  filter,
  onChange,
  shown,
  total,
  filtering,
}: {
  facets: Facets;
  filter: PoolFilter;
  onChange: (next: PoolFilter) => void;
  /** The InfraEnvs shown, and on the MCE. */
  shown: number;
  total: number;
  filtering: boolean;
}) {
  return (
    <>
      <SearchBox value={filter.search} onChange={(search) => onChange({ ...filter, search })} />
      <button
        type="button"
        aria-pressed={filter.withServers}
        onClick={() => onChange({ ...filter, withServers: !filter.withServers })}
        data-testid="pool-with-servers"
        className={cn(
          "inline-flex h-8 items-center rounded-full border px-3 text-xs font-medium transition-colors",
          filter.withServers
            ? "border-primary bg-primary text-primary-foreground"
            : "border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground"
        )}
      >
        Only with servers
      </button>
      <p role="status" aria-atomic className="text-xs text-muted-foreground sm:ml-auto" data-testid="pool-count">
        {filtering ? `${shown} of ${total} InfraEnvs` : `${total} InfraEnv${total === 1 ? "" : "s"}`}
      </p>
      {(facets.zone.length > 0 || facets.size.length > 0) && (
        <div className="flex w-full flex-wrap items-center gap-x-4 gap-y-2">
          <FacetPills facet="zone" facets={facets} value={filter.zone} onChange={(zone) => onChange({ ...filter, zone })} />
          <FacetPills facet="size" facets={facets} value={filter.size} onChange={(size) => onChange({ ...filter, size })} />
        </div>
      )}
    </>
  );
}
