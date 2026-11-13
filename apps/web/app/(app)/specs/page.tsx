"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Plus, Layers, Server, Search, X, ChevronsUpDown, FileWarning, SlidersHorizontal } from "lucide-react";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, plural } from "@/lib/utils";
import { useIsAdmin } from "@/stores/auth-store";
import { ProblemList } from "@/components/common/problem-list";
import { RefreshButton } from "@/components/common/refresh-button";
import { EmptyState, EmptyStateLink, NoMatches } from "@/components/common/empty-state";
import { structureSummary } from "@/lib/specs";
import type { SpecEntry } from "@/types";

type SortOption = "name-asc" | "name-desc" | "version-asc" | "version-desc";

const MAX_LISTED_PROBLEMS = 3;

/** A spec file that does not parse: listed with why, never hidden. */
function BrokenSpecCard({ spec }: { spec: SpecEntry }) {
  const problems = spec.load_problems ?? [];
  const hidden = problems.length - MAX_LISTED_PROBLEMS;
  return (
    <Link href={`/specs/${encodeURIComponent(spec.metadata.name)}`} data-testid={`spec-card-${spec.metadata.name}`}>
      <div className="bg-card rounded-xl border border-destructive/30 shadow-sm hover:shadow-md hover:border-destructive/50 transition-all cursor-pointer p-5 h-full group">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="text-sm font-semibold break-all group-hover:text-primary transition-colors">{spec.metadata.name}</h3>
          <span className="shrink-0 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs bg-destructive/10 text-destructive font-medium">
            <FileWarning className="h-3 w-3" />Does not load
          </span>
        </div>
        <p className="text-xs text-destructive/90 break-words">{spec.load_error}</p>
        {problems.length > 0 && (
          <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground list-disc pl-4">
            {problems.slice(0, MAX_LISTED_PROBLEMS).map((p, i) => (
              <li key={i} className="break-words line-clamp-2">{p}</li>
            ))}
            {hidden > 0 && <li className="list-none -ml-4">+{hidden} more</li>}
          </ul>
        )}
      </div>
    </Link>
  );
}

function SpecCard({ spec }: { spec: SpecEntry }) {
  const shape = structureSummary(spec.spec.day1.structure);
  const presets = Object.keys(spec.spec.day1.values ?? {}).length;
  const addons = spec.spec.day2.addons.length;
  return (
    <Link href={`/specs/${encodeURIComponent(spec.metadata.name)}`} data-testid={`spec-card-${spec.metadata.name}`}>
      <div className="bg-card rounded-xl border shadow-sm hover:shadow-md hover:border-primary/30 transition-all cursor-pointer p-5 h-full group">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="text-sm font-semibold break-all group-hover:text-primary transition-colors">{spec.metadata.name}</h3>
          <span className="shrink-0 rounded-full px-2 py-0.5 text-xs bg-primary/10 text-primary font-medium max-w-[8rem] truncate">{spec.metadata.version}</span>
        </div>
        {spec.metadata.description && (
          <p className="text-xs text-muted-foreground line-clamp-2 mb-3">{spec.metadata.description}</p>
        )}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {shape.length > 0 && (
            <span className="flex items-center gap-1">
              <Layers className="h-3 w-3" />{shape.join(", ")}
            </span>
          )}
          {presets > 0 && (
            <span className="flex items-center gap-1">
              <SlidersHorizontal className="h-3 w-3" />{plural(presets, "preset")}
            </span>
          )}
          <span className="flex items-center gap-1">
            <Server className="h-3 w-3" />{addons > 0 ? plural(addons, "addon") : "No addons"}
          </span>
        </div>
        {spec.metadata.labels && Object.keys(spec.metadata.labels).length > 0 && (
          <div className="flex flex-wrap gap-1 mt-3">
            {Object.entries(spec.metadata.labels).map(([k, v]) => (
              <span key={k} className="rounded-full px-2 py-0.5 text-xs bg-muted text-muted-foreground max-w-full truncate">{k}: {v}</span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}

export default function SpecsPage() {
  const isAdmin = useIsAdmin();
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortOption>("name-asc");

  const { data: specs, isLoading, isFetching, error } = useQuery<SpecEntry[]>({
    queryKey: day1Keys.specs.all,
    queryFn: day1Api.specs.list,
    staleTime: 60_000,
  });

  const brokenCount = useMemo(() => (specs ?? []).filter((s) => s.load_error).length, [specs]);

  const filtered = useMemo(() => {
    let list = specs ?? [];
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (s) =>
          s.metadata.name.toLowerCase().includes(q) ||
          s.metadata.description?.toLowerCase().includes(q) ||
          Object.values(s.metadata.labels ?? {}).some((v) => String(v).toLowerCase().includes(q))
      );
    }
    return [...list].sort((a, b) => {
      const [field, dir] = sort.split("-") as [string, string];
      let cmp = 0;
      if (field === "name") cmp = a.metadata.name.localeCompare(b.metadata.name);
      else if (field === "version") cmp = String(a.metadata.version).localeCompare(String(b.metadata.version), undefined, { numeric: true });
      return dir === "asc" ? cmp : -cmp;
    });
  }, [specs, search, sort]);

  const hasActiveFilters = !!search;

  const sortOptions: { value: SortOption; label: string }[] = [
    { value: "name-asc", label: "Name A→Z" },
    { value: "name-desc", label: "Name Z→A" },
    { value: "version-desc", label: "Version ↓" },
    { value: "version-asc", label: "Version ↑" },
  ];

  const total = specs?.length ?? 0;

  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >Flavors</h1>
          {isLoading ? (
            <Skeleton className="mt-1.5 h-4 w-24" />
          ) : (
            <p className="text-sm text-muted-foreground mt-0.5">
              {specs
                ? `${filtered.length}${hasActiveFilters ? ` of ${total}` : ""} flavor${total !== 1 ? "s" : ""}`
                : "Cluster flavors in the specs repo"}
              {brokenCount > 0 && (
                <span className="text-destructive"> · {brokenCount} do{brokenCount === 1 ? "es" : ""} not load</span>
              )}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <RefreshButton queryKey={day1Keys.specs.all} fetching={isFetching} title="Refresh flavors" />
          {isAdmin && (
            <Link href="/specs/new" className={buttonVariants({ size: "sm" })}>
              <Plus className="h-4 w-4 mr-1.5" />New Flavor
            </Link>
          )}
        </div>
      </div>

      {/* Filter/sort bar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-40 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search flavors..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border bg-card pl-8 pr-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
          />
        </div>

        {/* Sort */}
        <div className="flex items-center gap-1.5">
          <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground" />
          <div className="flex items-center rounded-lg border bg-muted/40 p-0.5 gap-0.5">
            {sortOptions.map((o) => (
              <button
                key={o.value}
                onClick={() => setSort(o.value)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium transition-all whitespace-nowrap",
                  sort === o.value
                    ? "bg-background shadow-sm text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >{o.label}</button>
            ))}
          </div>
        </div>

        {hasActiveFilters && (
          <button
            onClick={() => setSearch("")}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-3 w-3" />Clear
          </button>
        )}
      </div>

      {error ? (
        <ProblemList error={error} title="The flavors could not be loaded" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {isLoading
            ? Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-40 rounded-xl" />
              ))
            : filtered.map((spec) =>
                spec.load_error
                  ? <BrokenSpecCard key={spec.metadata.name} spec={spec} />
                  : <SpecCard key={spec.metadata.name} spec={spec} />
              )}
          {!isLoading && specs?.length === 0 && (
            <EmptyState
              icon={Layers}
              title="No flavors yet"
              description="A flavor presets or locks a cluster's values, nodepool shape and add-ons; clusters are created from one, and existing ones can join it."
              action={isAdmin && <EmptyStateLink href="/specs/new">New spec</EmptyStateLink>}
              bordered
              className="col-span-full"
              data-testid="specs-empty"
            />
          )}
          {!isLoading && specs && specs.length > 0 && filtered.length === 0 && (
            <NoMatches
              what="flavors"
              clearLabel="Clear search"
              onClear={() => setSearch("")}
              bordered
              className="col-span-full"
            />
          )}
        </div>
      )}
    </div>
  );
}
