"use client";

import { useState, useMemo, useCallback, useRef } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { AddonCatalogEntry, InstalledAddon } from "@/types";
import { Plus, AlertTriangle, CheckCircle2, HelpCircle, RefreshCw, Search, ChevronsUpDown, ChevronUp, ChevronDown, X } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { useIsAdmin } from "@/stores/auth-store";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/clusters/status-badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { ClusterStatus, ClusterLiveStatus } from "@/types";

type SortField = "name" | "site" | "spec" | "created_at";
type SortDir = "asc" | "desc";
type SyncFilter = "all" | "synced" | "drifted" | "na";

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

function SortIcon({ field, sortField, sortDir }: { field: SortField; sortField: SortField; sortDir: SortDir }) {
  if (sortField !== field) return <ChevronsUpDown className="h-3 w-3 text-muted-foreground/50" />;
  return sortDir === "asc"
    ? <ChevronUp className="h-3 w-3 text-primary" />
    : <ChevronDown className="h-3 w-3 text-primary" />;
}

const NO_SPEC_SENTINEL = "(not linked to a cluster spec)";
const hasSpec = (specName: string | undefined) =>
  !!specName && specName !== NO_SPEC_SENTINEL && specName !== "—";

function liveStatusToPhase(s: ClusterLiveStatus): "Ready" | "Error" | "Provisioning" | "Unknown" {
  if (s.error) return "Error";
  if (s.hc_problems.length > 0) return "Error";
  if (s.node_pools.length === 0) return "Unknown";
  const allReady = s.node_pools.every(
    (np) => np.ready_replicas === np.desired_replicas && np.problems.length === 0
  );
  if (allReady) return "Ready";
  return "Provisioning";
}

function ClusterStatusCell({ name, mce, site }: { name: string; mce: string; site: string }) {
  const { data: liveStatus, isLoading } = useQuery<ClusterLiveStatus | null>({
    queryKey: ["clusters", name, "live-status", mce],
    queryFn: async () => {
      try {
        return await api.get<ClusterLiveStatus>(`/api/day1/clusters/${name}/status?mce=${mce}`);
      } catch (err) {
        // 501 = feature disabled — show nothing
        if (err instanceof Error && err.message.startsWith("API error 501")) return null;
        throw err;
      }
    },
    staleTime: 2 * 60_000,   // 2 min — match global
    refetchInterval: 2 * 60_000, // 2 min polling
    retry: false,
    enabled: Boolean(mce),
  });

  if (isLoading) {
    return (
      <Link href={`/clusters/${name}?site=${site}&mce=${mce}`} className="block">
        <Skeleton className="h-5 w-16" />
      </Link>
    );
  }

  // Feature disabled or query failed — fall back to "—" link
  if (!liveStatus) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <Link
              href={`/clusters/${name}?site=${site}&mce=${mce}`}
              className="text-muted-foreground/60 text-xs hover:text-primary transition-colors"
            >
              —
            </Link>
          </TooltipTrigger>
          <TooltipContent>Click to view live status</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  const phase = liveStatusToPhase(liveStatus);
  const errorMsg = liveStatus.error ?? liveStatus.hc_problems[0];

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Link href={`/clusters/${name}?site=${site}&mce=${mce}`}>
            <StatusBadge phase={phase} />
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
  const [syncFilter, setSyncFilter] = useState<SyncFilter>("all");
  const [sortField, setSortField] = useState<SortField>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const { data: clusters, isLoading, isFetching, error } = useQuery<ClusterStatus[]>({
    queryKey: ["clusters"],
    queryFn: () => api.get<ClusterStatus[]>("/api/day1/clusters"),
    staleTime: 30_000,
  });

  const { data: driftSummary } = useQuery<{ name: string; is_drifted: boolean }[]>({
    queryKey: ["clusters", "drift-summary"],
    queryFn: () => api.get("/api/day1/clusters/drift-summary"),
    staleTime: 30_000, // Cache for 30 seconds
    refetchOnWindowFocus: false, // Don't refetch on focus to avoid blocking
  });

  const driftMap = useMemo(
    () => new Map(driftSummary?.map((d) => [d.name, d.is_drifted]) ?? []),
    [driftSummary]
  );

  // Prefetch cluster detail and addons on row hover for faster navigation
  // Uses debouncing and requestIdleCallback to ensure it never blocks the UI
  const prefetchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const prefetchCluster = useCallback((name: string, site: string, mce: string) => {
    // Clear any pending prefetch to debounce
    if (prefetchTimeoutRef.current) {
      clearTimeout(prefetchTimeoutRef.current);
    }

    // Debounce: only prefetch if user hovers for 150ms
    prefetchTimeoutRef.current = setTimeout(() => {
      // Use requestIdleCallback to ensure prefetching never blocks UI
      const doPrefetch = () => {
        // Prefetch cluster detail
        queryClient.prefetchQuery({
          queryKey: ["clusters", name, "detail"],
          queryFn: () => api.get(`/api/day1/clusters/${name}?site=${site}&mce=${mce}`),
          staleTime: 60_000,
        });
        // Prefetch cluster drift
        queryClient.prefetchQuery({
          queryKey: ["clusters", name, "drift"],
          queryFn: () => api.get(`/api/day1/clusters/${name}/drift?site=${site}&mce=${mce}`),
          staleTime: 60_000,
        });
        // Prefetch installed addons (key matches addons page)
        queryClient.prefetchQuery({
          queryKey: ["clusters", name, "addons"],
          queryFn: () => api.get<{ installed: InstalledAddon[] }>(`/api/day2/clusters/${name}/addons?mce=${mce}`),
          staleTime: 60_000,
        });
        // Prefetch addon catalog (key matches addons page) - only if not already cached
        queryClient.prefetchQuery({
          queryKey: ["addons", "catalog"],
          queryFn: () => api.get<AddonCatalogEntry[]>("/api/day2/addons"),
          staleTime: 120_000,
        });
      };

      // requestIdleCallback with fallback for older browsers
      if (typeof window !== "undefined" && "requestIdleCallback" in window) {
        (window as Window & { requestIdleCallback: (cb: () => void) => void }).requestIdleCallback(doPrefetch);
      } else {
        // Fallback: use setTimeout with 0 to defer to next event loop
        setTimeout(doPrefetch, 0);
      }
    }, 150);
  }, [queryClient]);

  // Unique sites for filter chips
  const sites = useMemo(() => {
    const s = new Set(clusters?.map((c) => c.site).filter(Boolean) ?? []);
    return Array.from(s).sort();
  }, [clusters]);

  // Filtering + sorting
  const filtered = useMemo(() => {
    let list = clusters ?? [];
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.site?.toLowerCase().includes(q) ||
          c.mce?.toLowerCase().includes(q) ||
          c.spec_name?.toLowerCase().includes(q)
      );
    }
    if (siteFilter !== "all") list = list.filter((c) => c.site === siteFilter);
    if (syncFilter !== "all") {
      list = list.filter((c) => {
        const linked = hasSpec(c.spec_name);
        if (syncFilter === "na") return !linked;
        if (!linked) return false;
        const drifted = driftMap.get(c.name);
        if (syncFilter === "drifted") return drifted === true;
        if (syncFilter === "synced") return drifted === false;
        return true;
      });
    }

    list = [...list].sort((a, b) => {
      let cmp = 0;
      if (sortField === "name") cmp = a.name.localeCompare(b.name);
      else if (sortField === "site") cmp = (a.site ?? "").localeCompare(b.site ?? "");
      else if (sortField === "spec") cmp = (a.spec_name ?? "").localeCompare(b.spec_name ?? "");
      else if (sortField === "created_at") cmp = (a.created_at ?? "").localeCompare(b.created_at ?? "");
      return sortDir === "asc" ? cmp : -cmp;
    });

    return list;
  }, [clusters, search, siteFilter, syncFilter, sortField, sortDir, driftMap]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginated = filtered.slice((page - 1) * pageSize, page * pageSize);

  // Reset to page 1 when filters change
  function setFilter<T>(setter: (v: T) => void): (v: T) => void {
    return (v) => { setter(v); setPage(1); };
  }

  function toggleSort(field: SortField) {
    if (sortField === field) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortField(field); setSortDir("asc"); setPage(1); }
  }

  const hasActiveFilters = search || siteFilter !== "all" || syncFilter !== "all";

  return (
    <div className="p-6 lg:p-8 max-w-[1400px] mx-auto space-y-4 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            Clusters
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {clusters
              ? `${filtered.length} of ${clusters.length} cluster${clusters.length !== 1 ? "s" : ""}${hasActiveFilters ? " (filtered)" : ""}`
              : "Manage your HostedControlPlane clusters"}
          </p>
        </div>
        <div className="flex items-center gap-2">
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
        {/* Search */}
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

        {/* Site filter chips */}
        {sites.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs text-muted-foreground font-medium">Site:</span>
            <button
              onClick={() => setFilter(setSiteFilter)("all")}
              className={cn(
                "rounded-full px-2.5 py-1 text-xs font-medium transition-all border",
                siteFilter === "all"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-card text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
              )}
            >All</button>
            {sites.map((s) => (
              <button
                key={s}
                onClick={() => setFilter(setSiteFilter)(siteFilter === s ? "all" : s)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs font-medium transition-all border",
                  siteFilter === s
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-card text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
                )}
              >{s}</button>
            ))}
          </div>
        )}

        {/* Sync filter chips */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-muted-foreground font-medium">Sync:</span>
          {(["all", "synced", "drifted", "na"] as SyncFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(setSyncFilter)(f)}
              className={cn(
                "rounded-full px-2.5 py-1 text-xs font-medium transition-all border capitalize",
                syncFilter === f
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-card text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
              )}
            >{f === "na" ? "N/A" : f}</button>
          ))}
        </div>

        {/* Clear filters */}
        {hasActiveFilters && (
          <button
            onClick={() => { setSearch(""); setSiteFilter("all"); setSyncFilter("all"); setPage(1); }}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors ml-1"
          >
            <X className="h-3 w-3" />
            Clear filters
          </button>
        )}

        {/* Page size */}
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
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Failed to load clusters. Please try again.
        </div>
      ) : (
        <>
          <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/30">
                  <th className="text-left px-4 py-3">
                    <button onClick={() => toggleSort("name")} className="flex items-center gap-1 text-xs font-semibold text-muted-foreground uppercase tracking-wide hover:text-foreground transition-colors">
                      Name <SortIcon field="name" sortField={sortField} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Status</th>
                  <th className="text-left px-4 py-3">
                    <button onClick={() => toggleSort("site")} className="flex items-center gap-1 text-xs font-semibold text-muted-foreground uppercase tracking-wide hover:text-foreground transition-colors">
                      Site / MCE <SortIcon field="site" sortField={sortField} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="text-left px-4 py-3">
                    <button onClick={() => toggleSort("spec")} className="flex items-center gap-1 text-xs font-semibold text-muted-foreground uppercase tracking-wide hover:text-foreground transition-colors">
                      Spec <SortIcon field="spec" sortField={sortField} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Created By</th>
                  <th className="text-left px-4 py-3">
                    <button onClick={() => toggleSort("created_at")} className="flex items-center gap-1 text-xs font-semibold text-muted-foreground uppercase tracking-wide hover:text-foreground transition-colors">
                      Created At <SortIcon field="created_at" sortField={sortField} sortDir={sortDir} />
                    </button>
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Sync</th>
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
                  : paginated.map((cluster) => (
                      <tr
                        key={cluster.name}
                        className="hover:bg-primary/[0.03] transition-colors"
                        onMouseEnter={() => prefetchCluster(cluster.name, cluster.site, cluster.mce)}
                      >
                        <td className="px-4 py-3 whitespace-nowrap">
                          <Link
                            href={`/clusters/${cluster.name}?site=${cluster.site}&mce=${cluster.mce}`}
                            className="font-semibold text-foreground hover:text-primary transition-colors"
                          >
                            {cluster.name}
                          </Link>
                        </td>
                        <td className="px-4 py-3">
                          <ClusterStatusCell
                            name={cluster.name}
                            mce={cluster.mce}
                            site={cluster.site}
                          />
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="leading-snug">
                            <p className="text-sm text-foreground">{cluster.site}</p>
                            <p className="text-xs text-muted-foreground">{cluster.mce}</p>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {cluster.spec_name ? (
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <Link href={`/specs/${cluster.spec_name}`} className="hover:text-primary transition-colors font-medium whitespace-nowrap">
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
                        <td className="px-4 py-3 text-muted-foreground">{cluster.created_by ?? "—"}</td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {cluster.created_at ? new Date(cluster.created_at).toLocaleDateString("en-GB") : "—"}
                        </td>
                        <td className="px-4 py-3">
                          {!hasSpec(cluster.spec_name) ? (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium text-muted-foreground cursor-default">
                                  <HelpCircle className="h-3 w-3" />
                                  N/A
                                </TooltipTrigger>
                                <TooltipContent>Not active — cluster is not linked to a spec</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          ) : driftSummary === undefined ? (
                            <Skeleton className="h-5 w-16" />
                          ) : driftMap.get(cluster.name) ? (
                            <span className="relative inline-flex">
                              <span className="absolute inset-0 rounded-full bg-[#fdab3d]/30 animate-ping" />
                              <Link
                                href={`/clusters/${cluster.name}?site=${cluster.site}&mce=${cluster.mce}`}
                                className="relative inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-[#fdab3d]/10 text-[#c07800] dark:text-[#fdab3d] hover:bg-[#fdab3d]/20 transition-colors"
                              >
                                <AlertTriangle className="h-3 w-3" />
                                Drifted
                              </Link>
                            </span>
                          ) : (
                            <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-[#00c875]/8 text-[#007038] dark:text-[#00c875]")}>
                              <CheckCircle2 className="h-3 w-3" />
                              Synced
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                {!isLoading && clusters?.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-16 text-center text-muted-foreground">
                      No clusters yet.{" "}
                      <Link href="/clusters/new" className="text-primary hover:underline font-medium">
                        Create your first cluster
                      </Link>.
                    </td>
                  </tr>
                )}
                {!isLoading && clusters && clusters.length > 0 && filtered.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-muted-foreground text-sm">
                      No clusters match your filters.{" "}
                      <button
                        onClick={() => { setSearch(""); setSiteFilter("all"); setSyncFilter("all"); setPage(1); }}
                        className="text-primary hover:underline"
                      >Clear filters</button>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
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
