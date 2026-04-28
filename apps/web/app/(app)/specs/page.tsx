"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Layers, Server, RefreshCw, Search, X, ChevronsUpDown } from "lucide-react";
import { api } from "@/lib/api-client";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ClusterSpec } from "@/types";

type SortOption = "name-asc" | "name-desc" | "version-asc" | "version-desc";

function SpecCard({ spec }: { spec: ClusterSpec }) {
  return (
    <Link href={`/specs/${spec.metadata.name}`}>
      <div className="bg-card rounded-xl border shadow-sm hover:shadow-md hover:border-primary/30 transition-all cursor-pointer p-5 h-full group">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="text-sm font-semibold group-hover:text-primary transition-colors">{spec.metadata.name}</h3>
          <span className="shrink-0 rounded-full px-2 py-0.5 text-xs bg-primary/10 text-primary font-medium">v{spec.metadata.version}</span>
        </div>
        {spec.metadata.description && (
          <p className="text-xs text-muted-foreground line-clamp-2 mb-3">{spec.metadata.description}</p>
        )}
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Layers className="h-3 w-3" />{spec.spec.day1.variables.length} variables
          </span>
          {spec.spec.day2.addons.length > 0 && (
            <span className="flex items-center gap-1">
              <Server className="h-3 w-3" />{spec.spec.day2.addons.length} addon{spec.spec.day2.addons.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        {spec.metadata.labels && Object.keys(spec.metadata.labels).length > 0 && (
          <div className="flex flex-wrap gap-1 mt-3">
            {Object.entries(spec.metadata.labels).map(([k, v]) => (
              <span key={k} className="rounded-full px-2 py-0.5 text-xs bg-muted text-muted-foreground">{k}: {v}</span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}

export default function SpecsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortOption>("name-asc");

  const { data: specs, isLoading, isFetching, error } = useQuery<ClusterSpec[]>({
    queryKey: ["specs"],
    queryFn: () => api.get<ClusterSpec[]>("/api/day1/specs"),
    staleTime: 60_000,
  });

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

  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >Cluster Specs</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {isLoading ? "Loading..." : `${filtered.length}${hasActiveFilters ? ` of ${specs?.length ?? 0}` : ""} spec${(specs?.length ?? 0) !== 1 ? "s" : ""}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ["specs"] })}
            disabled={isFetching}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
            title="Refresh specs"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            Refresh
          </button>
          <Link href="/specs/new" className={buttonVariants({ size: "sm" })}>
            <Plus className="h-4 w-4 mr-1.5" />New Spec
          </Link>
        </div>
      </div>

      {/* Filter/sort bar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-40 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search specs..."
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
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Failed to load specs. Please try again.
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {isLoading
            ? Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-40 rounded-xl" />
              ))
            : filtered.map((spec) => <SpecCard key={spec.metadata.name} spec={spec} />)}
          {!isLoading && specs?.length === 0 && (
            <div className="col-span-full bg-card rounded-xl border p-16 text-center text-muted-foreground">
              No specs yet.{" "}
              <Link href="/specs/new" className="text-primary hover:underline">Create your first spec</Link>.
            </div>
          )}
          {!isLoading && specs && specs.length > 0 && filtered.length === 0 && (
            <div className="col-span-full bg-card rounded-xl border p-12 text-center text-muted-foreground text-sm">
              No specs match your search.{" "}
              <button onClick={() => setSearch("")} className="text-primary hover:underline">Clear search</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
