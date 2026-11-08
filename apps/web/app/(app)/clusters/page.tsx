"use client";

import { useState, useMemo, useCallback, useRef } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Search, ChevronsUpDown, ChevronUp, ChevronDown, X, FileWarning, Server, TriangleAlert } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { useIsAdmin } from "@/stores/auth-store";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/clusters/status-badge";
import { DriftBadge } from "@/components/clusters/drift-badge";
import { ProblemList } from "@/components/common/problem-list";
import { EmptyState, EmptyStateLink, NoMatches } from "@/components/common/empty-state";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useBulkStatus } from "@/hooks/use-bulk-status";
import { liveStatusToPhase } from "@/lib/live-status";
import { clusterHref } from "@/lib/clusters";
import { day2Api, day2Keys } from "@/lib/day2";
import type { CatalogEntry, ClusterLiveStatus, ClusterStatus, DestinationCharts, DriftState, DriftSummaryItem } from "@/types";

type SortField = "name" | "site" | "spec" | "mastertag" | "created_at";
type SortDir = "asc" | "desc";
type DriftFilter = "all" | DriftState;

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

const DRIFT_FILTERS: { value: DriftFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "in_sync", label: "In sync" },
  { value: "drifted", label: "Drifted" },
  { value: "unknown", label: "Unknown" },
  { value: "not_linked", label: "Not linked" },
];

function SortIcon({ field, sortField, sortDir }: { field: SortField; sortField: SortField; sortDir: SortDir }) {
  if (sortField !== field) return <ChevronsUpDown className="h-3 w-3 text-muted-foreground/50" />;
  return sortDir === "asc"
    ? <ChevronUp className="h-3 w-3 text-primary" />
    : <ChevronDown className="h-3 w-3 text-primary" />;
}

/** Off-convention names and unreadable files are flagged in place, never hidden. */
function ClusterFlags({ cluster }: { cluster: ClusterStatus }) {
  const offConvention = !cluster.naming.follows_convention;
  const unreadable = cluster.problems.length > 0;
  if (!offConvention && !unreadable) return null;
  return (
    <TooltipProvider>
      {unreadable && (
        <Tooltip>
          <TooltipTrigger
            data-testid="cluster-unreadable"
            className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium bg-status-error/10 text-status-error-fg cursor-default"
          >
            <FileWarning className="h-3 w-3" />Unreadable
          </TooltipTrigger>
          <TooltipContent className="max-w-sm">
            <p className="font-medium mb-1">The cluster file does not parse</p>
            <ul className="list-disc pl-4 space-y-0.5">{cluster.problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
          </TooltipContent>
        </Tooltip>
      )}
      {offConvention && (
        <Tooltip>
          <TooltipTrigger
            data-testid="cluster-off-convention"
            aria-label="Name does not follow the naming convention"
            className="inline-flex items-center text-status-warning cursor-default"
          >
            <TriangleAlert className="h-3.5 w-3.5" />
          </TooltipTrigger>
          <TooltipContent className="max-w-sm">
            <p className="font-medium mb-1">Off the naming convention</p>
            <ul className="list-disc pl-4 space-y-0.5">{cluster.naming.problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
          </TooltipContent>
        </Tooltip>
      )}
    </TooltipProvider>
  );
}

function ClusterStatusCell({
  cluster,
  status,
  statusOff,
  isLoading,
  failed,
}: {
  cluster: ClusterStatus;
  status: ClusterLiveStatus | undefined;
  statusOff: boolean;
  isLoading: boolean;
  failed: boolean;
}) {
  if (isLoading) return <Skeleton className="h-5 w-16" />;
  if (!status) {
    const reason = statusOff
      ? "Live status is off in this deployment"
      : failed
      ? "Live status could not be read"
      : "No live status for this cluster";
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger className="text-muted-foreground/60 text-xs cursor-default">—</TooltipTrigger>
          <TooltipContent>{reason}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }
  const errorMsg = status.error ?? status.hc_problems[0];
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Link href={clusterHref(cluster)}>
            <StatusBadge phase={liveStatusToPhase(status)} />
          </Link>
        </TooltipTrigger>
        {errorMsg && <TooltipContent className="max-w-xs">{errorMsg}</TooltipContent>}
      </Tooltip>
    </TooltipProvider>
  );
}

export default function ClustersPage() {
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();

  // Filter / sort / pagination state
  const [search, setSearch] = useState("");
  const [siteFilter, setSiteFilter] = useState<string>("all");
  const [driftFilter, setDriftFilter] = useState<DriftFilter>("all");
  const [sortField, setSortField] = useState<SortField>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const { data: clusters, isLoading, isFetching, error } = useQuery<ClusterStatus[]>({
    queryKey: ["clusters"],
    queryFn: () => api.get<ClusterStatus[]>("/api/day1/clusters"),
    staleTime: 30_000,
  });

  const { data: liveStatuses, isLoading: statusLoading, isError: statusFailed } = useBulkStatus(clusters);

  const { data: driftSummary, isError: driftFailed } = useQuery<DriftSummaryItem[]>({
    queryKey: ["clusters", "drift-summary"],
    queryFn: () => api.get<DriftSummaryItem[]>("/api/day1/clusters/drift-summary"),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const driftMap = useMemo(
    () => new Map((driftSummary ?? []).map((d) => [d.name, d])),
    [driftSummary]
  );

  /** A linked cluster the summary does not list (or a failed summary) is unknown, never in sync. */
  const driftOf = useCallback(
    (c: ClusterStatus): DriftSummaryItem | null => {
      const item = driftMap.get(c.name);
      if (item) return item;
      if (!c.spec_name) return { name: c.name, site: c.site, mce: c.mce, state: "not_linked", is_drifted: false, error: null };
      if (driftSummary === undefined && !driftFailed) return null; // still loading
      return {
        name: c.name, site: c.site, mce: c.mce, state: "unknown", is_drifted: null,
        error: driftFailed ? "The drift summary could not be loaded" : null,
      };
    },
    [driftMap, driftSummary, driftFailed]
  );

  // Prefetch the detail page's data on row hover (debounced, at idle time)
  const prefetchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const prefetchCluster = useCallback((c: ClusterStatus) => {
    if (prefetchTimeoutRef.current) clearTimeout(prefetchTimeoutRef.current);
    prefetchTimeoutRef.current = setTimeout(() => {
      const query = `site=${encodeURIComponent(c.site)}&mce=${encodeURIComponent(c.mce)}`;
      const name = encodeURIComponent(c.name);
      const doPrefetch = () => {
        queryClient.prefetchQuery({
          queryKey: ["clusters", c.name, "detail"],
          queryFn: () => api.get(`/api/day1/clusters/${name}?${query}`),
          staleTime: 60_000,
        });
        queryClient.prefetchQuery({
          queryKey: ["clusters", c.name, "drift"],
          queryFn: () => api.get(`/api/day1/clusters/${name}/drift?${query}`),
          staleTime: 60_000,
        });
        // The entries the cluster's charts page reads (a bare name, narrowed by its MCE)
        queryClient.prefetchQuery({
          queryKey: day2Keys.charts(c.name, c.mce),
          queryFn: () => api.get<DestinationCharts>(day2Api.charts(c.name, c.mce)),
          staleTime: 60_000,
        });
        queryClient.prefetchQuery({
          queryKey: day2Keys.catalog,
          queryFn: () => api.get<CatalogEntry[]>(day2Api.catalog),
          staleTime: 120_000,
        });
      };
      if (typeof window !== "undefined" && "requestIdleCallback" in window) {
        (window as Window & { requestIdleCallback: (cb: () => void) => void }).requestIdleCallback(doPrefetch);
      } else {
        setTimeout(doPrefetch, 0);
      }
    }, 150);
  }, [queryClient]);

  const sites = useMemo(() => {
    const s = new Set(clusters?.map((c) => c.site).filter(Boolean) ?? []);
    return Array.from(s).sort();
  }, [clusters]);

  const driftCounts = useMemo(() => {
    const counts: Record<DriftFilter, number> = { all: 0, in_sync: 0, drifted: 0, unknown: 0, not_linked: 0 };
    for (const c of clusters ?? []) {
      counts.all += 1;
      const d = driftOf(c);
      if (d) counts[d.state] += 1;
    }
    return counts;
  }, [clusters, driftOf]);

  const filtered = useMemo(() => {
    let list = clusters ?? [];
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.site.toLowerCase().includes(q) ||
          c.mce.toLowerCase().includes(q) ||
          (c.spec_name ?? "").toLowerCase().includes(q) ||
          (c.mastertag ?? "").toLowerCase().includes(q)
      );
    }
    if (siteFilter !== "all") list = list.filter((c) => c.site === siteFilter);
    if (driftFilter !== "all") list = list.filter((c) => driftOf(c)?.state === driftFilter);

    return [...list].sort((a, b) => {
      let cmp = 0;
      if (sortField === "name") cmp = a.name.localeCompare(b.name);
      else if (sortField === "site") cmp = `${a.site}/${a.mce}`.localeCompare(`${b.site}/${b.mce}`);
      else if (sortField === "spec") cmp = (a.spec_name ?? "").localeCompare(b.spec_name ?? "");
      else if (sortField === "mastertag") cmp = (a.mastertag ?? "").localeCompare(b.mastertag ?? "", undefined, { numeric: true });
      else if (sortField === "created_at") cmp = (a.created_at ?? "").localeCompare(b.created_at ?? "");
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [clusters, search, siteFilter, driftFilter, sortField, sortDir, driftOf]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginated = filtered.slice((page - 1) * pageSize, page * pageSize);
  const flaggedCount = (clusters ?? []).filter((c) => c.problems.length > 0 || !c.naming.follows_convention).length;

  function setFilter<T>(setter: (v: T) => void): (v: T) => void {
    return (v) => { setter(v); setPage(1); };
  }

  function toggleSort(field: SortField) {
    if (sortField === field) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortField(field); setSortDir("asc"); setPage(1); }
  }

  function clearFilters() {
    setSearch(""); setSiteFilter("all"); setDriftFilter("all"); setPage(1);
  }

  const hasActiveFilters = search || siteFilter !== "all" || driftFilter !== "all";
  const statusOff = liveStatuses === null;

  const sortHeader = (field: SortField, label: string) => (
    <button onClick={() => toggleSort(field)} className="flex items-center gap-1 text-xs font-semibold text-muted-foreground uppercase tracking-wide hover:text-foreground transition-colors whitespace-nowrap">
      {label} <SortIcon field={field} sortField={sortField} sortDir={sortDir} />
    </button>
  );

  return (
    <div className="p-6 lg:p-8 max-w-[1400px] mx-auto space-y-4 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            Clusters
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {clusters
              ? `${filtered.length} of ${clusters.length} cluster${clusters.length !== 1 ? "s" : ""}${hasActiveFilters ? " (filtered)" : ""}`
              : "Hosted clusters in the day1 repo"}
            {flaggedCount > 0 && (
              <span className="ml-2 inline-flex items-center gap-1 text-status-warning-fg">
                <TriangleAlert className="h-3 w-3" />{flaggedCount} flagged
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ["clusters"] })}
            disabled={isFetching}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
            title="Refresh clusters"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            Refresh
          </button>
          {isAdmin && (
            <Link href="/clusters/new" className={buttonVariants({ size: "sm" })}>
              <Plus className="h-4 w-4 mr-1.5" />New Cluster
            </Link>
          )}
        </div>
      </div>

      {/* Filters bar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-48 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search clusters..."
            value={search}
            onChange={(e) => { setFilter(setSearch)(e.target.value); }}
            className="w-full rounded-lg border bg-card pl-8 pr-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
          />
        </div>

        {sites.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs text-muted-foreground font-medium">Site:</span>
            {["all", ...sites].map((s) => (
              <button
                key={s}
                onClick={() => setFilter(setSiteFilter)(siteFilter === s && s !== "all" ? "all" : s)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs font-medium transition-all border",
                  siteFilter === s
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-card text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
                )}
              >{s === "all" ? "All" : s}</button>
            ))}
          </div>
        )}

        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-muted-foreground font-medium">Drift:</span>
          {DRIFT_FILTERS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setFilter(setDriftFilter)(value)}
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-all border",
                driftFilter === value
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-card text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
              )}
            >
              {label}
              {value !== "all" && clusters && (
                <span className="tabular-nums opacity-70">{driftCounts[value]}</span>
              )}
            </button>
          ))}
        </div>

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors ml-1"
          >
            <X className="h-3 w-3" />
            Clear filters
          </button>
        )}

        {filtered.length > 10 && (
          <div className="flex items-center gap-1.5 ml-auto">
            <span className="text-xs text-muted-foreground">Rows:</span>
            <div className="flex items-center rounded-lg border bg-muted/40 p-0.5 gap-0.5">
              {PAGE_SIZE_OPTIONS.map((n) => (
                <button
                  key={n}
                  onClick={() => { setPageSize(n); setPage(1); }}
                  className={cn(
                    "rounded-md px-2 py-0.5 text-xs font-medium transition-all",
                    pageSize === n
                      ? "bg-background shadow-sm text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >{n}</button>
              ))}
            </div>
          </div>
        )}
      </div>

      {error ? (
        <ProblemList error={error} title="The clusters could not be loaded" />
      ) : (
        <>
          <div className="bg-card rounded-xl border shadow-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/30">
                  <th className="text-left px-4 py-3">{sortHeader("name", "Name")}</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Status</th>
                  <th className="text-left px-4 py-3">{sortHeader("site", "Site / MCE")}</th>
                  <th className="text-left px-4 py-3">{sortHeader("mastertag", "Mastertag")}</th>
                  <th className="text-left px-4 py-3">{sortHeader("spec", "Spec")}</th>
                  <th className="text-left px-4 py-3">{sortHeader("created_at", "Last change")}</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Drift</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {isLoading
                  ? Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 7 }).map((_, j) => (
                          <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                        ))}
                      </tr>
                    ))
                  : paginated.map((cluster) => {
                      const drift = driftOf(cluster);
                      return (
                        <tr
                          key={cluster.path}
                          data-testid={`cluster-row-${cluster.name}`}
                          className="hover:bg-primary/[0.03] transition-colors"
                          onMouseEnter={() => prefetchCluster(cluster)}
                        >
                          <td className="px-4 py-3 max-w-[22rem]">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <Link
                                href={clusterHref(cluster)}
                                className="font-semibold text-foreground hover:text-primary transition-colors truncate"
                                title={cluster.name}
                              >
                                {cluster.name}
                              </Link>
                              <ClusterFlags cluster={cluster} />
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <ClusterStatusCell
                              cluster={cluster}
                              status={liveStatuses?.[cluster.name]}
                              statusOff={statusOff}
                              isLoading={statusLoading}
                              failed={statusFailed}
                            />
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <div className="leading-snug">
                              <p className="text-sm text-foreground">{cluster.site}</p>
                              <p className="text-xs text-muted-foreground">{cluster.mce}</p>
                            </div>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap font-mono text-xs text-muted-foreground">
                            {cluster.mastertag ?? "—"}
                          </td>
                          <td className="px-4 py-3">
                            {cluster.spec_name ? (
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <Link href={`/specs/${encodeURIComponent(cluster.spec_name)}`} className="hover:text-primary transition-colors font-medium whitespace-nowrap">
                                  {cluster.spec_name}
                                </Link>
                                {cluster.spec_version && (
                                  <span className="rounded-full px-1.5 py-0.5 text-xs bg-primary/8 text-primary font-medium whitespace-nowrap">
                                    v{cluster.spec_version}
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-muted-foreground text-xs">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                            <div className="leading-snug">
                              <p className="text-sm">{cluster.created_by ?? "—"}</p>
                              <p className="text-xs">
                                {cluster.created_at ? new Date(cluster.created_at).toLocaleDateString("en-GB") : ""}
                              </p>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            {drift ? <DriftBadge state={drift.state} error={drift.error} /> : <Skeleton className="h-5 w-16" />}
                          </td>
                        </tr>
                      );
                    })}
                {!isLoading && clusters?.length === 0 && (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState
                        icon={Server}
                        title="No clusters yet"
                        description="Every hosted cluster file in the day1 repo is listed here."
                        action={isAdmin && <EmptyStateLink href="/clusters/new">New cluster</EmptyStateLink>}
                        data-testid="clusters-empty"
                      />
                    </td>
                  </tr>
                )}
                {!isLoading && clusters && clusters.length > 0 && filtered.length === 0 && (
                  <tr>
                    <td colSpan={7}>
                      <NoMatches what="clusters" onClear={clearFilters} />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <p className="text-xs text-muted-foreground">
                Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filtered.length)} of {filtered.length}
              </p>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className={cn(buttonVariants({ variant: "outline", size: "sm" }), "px-2 py-1 h-7 text-xs disabled:opacity-40")}
                >
                  ← Prev
                </button>
                {(() => {
                  const allPages = Array.from({ length: totalPages }, (_, x) => x + 1);
                  const visible = allPages.filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 1);
                  const withGaps: (number | "...")[] = [];
                  let prev = 0;
                  for (const p of visible) {
                    if (p - prev > 1) withGaps.push("...");
                    withGaps.push(p);
                    prev = p;
                  }
                  return withGaps.map((p, i) =>
                    p === "..." ? (
                      <span key={`ellipsis-${i}`} className="px-1 text-muted-foreground text-xs">…</span>
                    ) : (
                      <button
                        key={p}
                        onClick={() => setPage(p as number)}
                        className={cn(buttonVariants({ variant: p === page ? "default" : "outline", size: "sm" }), "px-2.5 py-1 h-7 text-xs min-w-[28px]")}
                      >{p}</button>
                    )
                  );
                })()}
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className={cn(buttonVariants({ variant: "outline", size: "sm" }), "px-2 py-1 h-7 text-xs disabled:opacity-40")}
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
