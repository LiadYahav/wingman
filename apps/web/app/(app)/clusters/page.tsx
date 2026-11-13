"use client";

import { Fragment, useState, useMemo, useCallback, useRef } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, ChevronsUpDown, ChevronUp, ChevronDown, X, FileWarning, Server, TriangleAlert } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { api } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { useIsAdmin } from "@/stores/auth-store";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatDate } from "@/lib/utils";
import { StatusBadge } from "@/components/clusters/status-badge";
import { FlavorStateBadge } from "@/components/clusters/drift-badge";
import { IntentLink } from "@/components/common/intent-link";
import { ProblemList } from "@/components/common/problem-list";
import { RefreshButton } from "@/components/common/refresh-button";
import { Pagination, PageSizePicker } from "@/components/common/pagination";
import { EmptyState, EmptyStateLink, NoMatches } from "@/components/common/empty-state";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useBulkStatus } from "@/hooks/use-bulk-status";
import { liveStatusToPhase } from "@/lib/live-status";
import { clusterHref, OWNER_KEYS, type OwnerKey } from "@/lib/clusters";
import { flavorDisplayState } from "@/lib/flavor-state";
import {
  ANY_OWNER, compareBy, compareOwner, countBy, DRIFT_FILTERS, filterOf, matchesSearch, NO_OWNER, OWNER_LABEL, ownerOf,
  type DriftFilter, type GroupBy, type SortDir, type SortField,
} from "@/components/clusters/list/model";
import { day2Api, day2Keys } from "@/lib/day2";
import type { CatalogEntry, ClusterLiveStatus, ClusterStatus, DestinationCharts, DriftSummaryItem } from "@/types";

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

function OwnerCell({ cluster }: { cluster: ClusterStatus }) {
  const parts = OWNER_KEYS.map((k) => ownerOf(cluster, k));
  if (parts.every((p) => !p)) return <span className="text-muted-foreground/60 text-xs">—</span>;
  return (
    <span className="font-mono text-xs text-muted-foreground whitespace-nowrap" data-testid="cluster-owner">
      {OWNER_KEYS.map((k, i) => (
        <Fragment key={k}>
          {i > 0 && " / "}
          <span title={`${OWNER_LABEL[k]} ${parts[i] || "not set"}`}>{parts[i] || "—"}</span>
        </Fragment>
      ))}
    </span>
  );
}

function SortIcon({ field, sortField, sortDir }: { field: SortField; sortField: SortField; sortDir: SortDir }) {
  if (sortField !== field) return <ChevronsUpDown className="h-3 w-3 text-muted-foreground/50" />;
  return sortDir === "asc"
    ? <ChevronUp className="h-3 w-3 text-primary" />
    : <ChevronDown className="h-3 w-3 text-primary" />;
}

/** A flag whose tooltip lists why: its trigger takes the remaining props. */
function FlagTooltip({ title, problems, ...trigger }: { title: string; problems: string[] } & React.ComponentProps<typeof TooltipTrigger>) {
  return (
    <Tooltip>
      <TooltipTrigger {...trigger} />
      <TooltipContent className="max-w-sm">
        <p className="font-medium mb-1">{title}</p>
        <ul className="list-disc pl-4 space-y-0.5">{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
      </TooltipContent>
    </Tooltip>
  );
}

/** Off-convention names and unreadable files are flagged in place, never hidden. */
function ClusterFlags({ cluster }: { cluster: ClusterStatus }) {
  const offConvention = !cluster.naming.follows_convention;
  const unreadable = cluster.problems.length > 0;
  if (!offConvention && !unreadable) return null;
  return (
    <TooltipProvider>
      {unreadable && (
        <FlagTooltip
          title="The cluster file does not parse"
          problems={cluster.problems}
          data-testid="cluster-unreadable"
          className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium bg-status-error/10 text-status-error-fg cursor-default"
        >
          <FileWarning className="h-3 w-3" />Unreadable
        </FlagTooltip>
      )}
      {offConvention && (
        <FlagTooltip
          title="Off the naming convention"
          problems={cluster.naming.problems}
          data-testid="cluster-off-convention"
          aria-label="Name does not follow the naming convention"
          className="inline-flex items-center text-status-warning cursor-default"
        >
          <TriangleAlert className="h-3.5 w-3.5" />
        </FlagTooltip>
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
          <IntentLink href={clusterHref(cluster)}>
            <StatusBadge phase={liveStatusToPhase(status)} />
          </IntentLink>
        </TooltipTrigger>
        {errorMsg && <TooltipContent className="max-w-xs">{errorMsg}</TooltipContent>}
      </Tooltip>
    </TooltipProvider>
  );
}

// eslint-disable-next-line max-lines-per-function -- size baseline (ADR-0056)
export default function ClustersPage() {
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();

  // Filter / sort / pagination state
  const [search, setSearch] = useState("");
  const [siteFilter, setSiteFilter] = useState<string>("all");
  const [driftFilter, setDriftFilter] = useState<DriftFilter>("all");
  const [ownerFilter, setOwnerFilter] = useState<Record<OwnerKey, string | null>>({ merkaz: null, anaf: null, mador: null });
  const [groupBy, setGroupBy] = useState<GroupBy>("none");
  const [sortField, setSortField] = useState<SortField>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const { data: clusters, isLoading, isFetching, error } = useQuery<ClusterStatus[]>({
    queryKey: day1Keys.clusters.all,
    queryFn: day1Api.clusters.list,
    staleTime: 30_000,
  });

  const { data: liveStatuses, isLoading: statusLoading, isError: statusFailed } = useBulkStatus(clusters);

  const { data: driftSummary, isError: driftFailed } = useQuery<DriftSummaryItem[]>({
    queryKey: day1Keys.clusters.driftSummary,
    queryFn: day1Api.clusters.driftSummary,
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
      const row = { name: c.name, site: c.site, mce: c.mce, spec_name: c.spec_name, spec_version: c.spec_version, update: null };
      if (!c.spec_name) return { ...row, state: "not_linked", is_drifted: false, error: null };
      if (driftSummary === undefined && !driftFailed) return null; // still loading
      return { ...row, state: "unknown", is_drifted: null, error: driftFailed ? "The drift summary could not be loaded" : null };
    },
    [driftMap, driftSummary, driftFailed]
  );

  // Prefetch the detail page's data on row hover (debounced, at idle time)
  const prefetchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const prefetchCluster = useCallback((c: ClusterStatus) => {
    if (prefetchTimeoutRef.current) clearTimeout(prefetchTimeoutRef.current);
    prefetchTimeoutRef.current = setTimeout(() => {
      const where = `?site=${encodeURIComponent(c.site)}&mce=${encodeURIComponent(c.mce)}`;
      const doPrefetch = () => {
        queryClient.prefetchQuery({
          queryKey: day1Keys.clusters.detail(c.name),
          queryFn: () => day1Api.clusters.detail(c.name, where),
          staleTime: 60_000,
        });
        queryClient.prefetchQuery({
          queryKey: day1Keys.clusters.drift(c.name),
          queryFn: () => day1Api.clusters.drift(c.name, where),
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
    const counts: Record<DriftFilter, number> = { all: 0, in_sync: 0, update: 0, drifted: 0, unknown: 0, not_linked: 0 };
    for (const c of clusters ?? []) {
      counts.all += 1;
      const d = driftOf(c);
      if (d) counts[filterOf(flavorDisplayState(d))] += 1;
    }
    return counts;
  }, [clusters, driftOf]);

  /** Each owner filter's choices: every number the files carry, with its count, and "not set" when some lack it. */
  const ownerOptions = useMemo(() => {
    const options = {} as Record<OwnerKey, ComboboxOption[]>;
    for (const key of OWNER_KEYS) {
      const counts = countBy(clusters ?? [], (c) => ownerOf(c, key));
      const numbers = [...counts.keys()].filter(Boolean).sort(compareOwner);
      const count = (n: number) => `${n} cluster${n !== 1 ? "s" : ""}`;
      options[key] = [
        { value: ANY_OWNER, label: `Any ${key}` },
        ...numbers.map((n) => ({ value: n, label: `${OWNER_LABEL[key]} ${n}`, description: count(counts.get(n) ?? 0) })),
        ...(counts.has("") ? [{ value: NO_OWNER, label: `No ${key}`, description: count(counts.get("") ?? 0) }] : []),
      ];
    }
    return options;
  }, [clusters]);

  const filtered = useMemo(() => {
    let list = clusters ?? [];
    if (search.trim()) list = list.filter((c) => matchesSearch(c, search.toLowerCase()));
    if (siteFilter !== "all") list = list.filter((c) => c.site === siteFilter);
    if (driftFilter !== "all") {
      list = list.filter((c) => {
        const d = driftOf(c);
        return d !== null && filterOf(flavorDisplayState(d)) === driftFilter;
      });
    }
    for (const key of OWNER_KEYS) {
      const wanted = ownerFilter[key];
      if (wanted !== null) list = list.filter((c) => ownerOf(c, key) === (wanted === NO_OWNER ? "" : wanted));
    }

    return [...list].sort((a, b) => {
      // Grouped: the group first, then the chosen order within it
      if (groupBy !== "none") {
        const group = compareOwner(ownerOf(a, groupBy), ownerOf(b, groupBy));
        if (group !== 0) return group;
      }
      const cmp = compareBy(sortField, a, b);
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [clusters, search, siteFilter, driftFilter, ownerFilter, groupBy, sortField, sortDir, driftOf]);

  /** How many filtered clusters each group has, for its heading (a group can span pages). */
  const groupSizes = useMemo(
    () => (groupBy === "none" ? new Map<string, number>() : countBy(filtered, (c) => ownerOf(c, groupBy))),
    [filtered, groupBy]
  );

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
    setSearch(""); setSiteFilter("all"); setDriftFilter("all"); setOwnerFilter({ merkaz: null, anaf: null, mador: null }); setPage(1);
  }

  const setOwner = (key: OwnerKey, value: string | null) => {
    setOwnerFilter((prev) => ({ ...prev, [key]: value === ANY_OWNER ? null : value }));
    setPage(1);
  };

  const hasActiveFilters =
    search || siteFilter !== "all" || driftFilter !== "all" || OWNER_KEYS.some((k) => ownerFilter[k] !== null);
  const hasOwners = (clusters ?? []).some((c) => OWNER_KEYS.some((k) => ownerOf(c, k)));
  const columns = 8;
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
          <RefreshButton queryKey={day1Keys.clusters.all} fetching={isFetching} title="Refresh clusters" />
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

        {hasOwners && (
          <div className="flex items-center gap-1.5 flex-wrap" role="group" aria-label="Owner filters">
            <span className="text-xs text-muted-foreground font-medium">Owner:</span>
            {OWNER_KEYS.map((key) => (
              <Combobox
                key={key}
                size="sm"
                options={ownerOptions[key]}
                value={ownerFilter[key]}
                onValueChange={(v) => setOwner(key, v)}
                placeholder={OWNER_LABEL[key]}
                searchPlaceholder={`Search ${key} numbers…`}
                emptyMessage={`No ${key} number matches.`}
                aria-label={`Filter by ${key}`}
                data-testid={`owner-filter-${key}`}
                className={cn(
                  "w-auto min-w-24 max-w-40 text-xs",
                  ownerFilter[key] !== null && "border-primary text-primary"
                )}
              />
            ))}
          </div>
        )}

        {hasOwners && (
          <div className="flex items-center gap-1.5 flex-wrap" role="group" aria-label="Group by owner">
            <span className="text-xs text-muted-foreground font-medium">Group:</span>
            {(["none", ...OWNER_KEYS] as const).map((g) => (
              <button
                key={g}
                onClick={() => { setGroupBy(g); setPage(1); }}
                aria-pressed={groupBy === g}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs font-medium transition-all border",
                  groupBy === g
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-card text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
                )}
              >{g === "none" ? "None" : OWNER_LABEL[g]}</button>
            ))}
          </div>
        )}

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors ml-1"
          >
            <X className="h-3 w-3" />
            Clear filters
          </button>
        )}

        <PageSizePicker total={filtered.length} sizes={PAGE_SIZE_OPTIONS} pageSize={pageSize} onPageSize={(n) => { setPageSize(n); setPage(1); }} />
      </div>

      {error ? (
        <ProblemList error={error} title="The clusters could not be loaded" />
      ) : (
        <>
          <div className="bg-card rounded-xl border shadow-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/30">
                  <th className="text-left px-3 py-3">{sortHeader("name", "Name")}</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Status</th>
                  <th className="text-left px-3 py-3">{sortHeader("site", "Site / MCE")}</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap" title="Merkaz / anaf / mador">
                    Owner
                  </th>
                  <th className="text-left px-3 py-3">{sortHeader("mastertag", "Mastertag")}</th>
                  <th className="text-left px-3 py-3">{sortHeader("spec", "Flavor")}</th>
                  <th className="text-left px-3 py-3">{sortHeader("created_at", "Last change")}</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Drift</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {isLoading
                  ? Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i}>
                        {Array.from({ length: columns }).map((_, j) => (
                          <td key={j} className="px-3 py-3"><Skeleton className="h-4 w-full" /></td>
                        ))}
                      </tr>
                    ))
                  : paginated.map((cluster, i) => {
                      const drift = driftOf(cluster);
                      const group = groupBy === "none" ? null : ownerOf(cluster, groupBy);
                      // A group's heading opens it, and each page it continues on
                      const startsGroup = group !== null && (i === 0 || ownerOf(paginated[i - 1], groupBy as OwnerKey) !== group);
                      const size = group !== null ? groupSizes.get(group) ?? 0 : 0;
                      return (
                        <Fragment key={cluster.path}>
                          {startsGroup && (
                            <tr data-testid={`owner-group-${groupBy}-${group || "none"}`} className="bg-muted/40">
                              <td colSpan={columns} className="px-3 py-2 text-xs font-semibold text-foreground">
                                {group ? `${OWNER_LABEL[groupBy as OwnerKey]} ${group}` : `No ${groupBy}`}
                                <span className="ml-2 font-normal text-muted-foreground">
                                  {size} cluster{size !== 1 ? "s" : ""}
                                </span>
                              </td>
                            </tr>
                          )}
                          <tr
                            data-testid={`cluster-row-${cluster.name}`}
                            className="hover:bg-primary/[0.03] transition-colors"
                            onMouseEnter={() => prefetchCluster(cluster)}
                          >
                            <td className="px-3 py-3 max-w-[22rem]">
                              <div className="flex items-center gap-1.5 min-w-0">
                                <IntentLink
                                  href={clusterHref(cluster)}
                                  className="font-semibold text-foreground hover:text-primary transition-colors truncate"
                                  title={cluster.name}
                                >
                                  {cluster.name}
                                </IntentLink>
                                <ClusterFlags cluster={cluster} />
                              </div>
                            </td>
                            <td className="px-3 py-3">
                              <ClusterStatusCell
                                cluster={cluster}
                                status={liveStatuses?.[cluster.name]}
                                statusOff={statusOff}
                                isLoading={statusLoading}
                                failed={statusFailed}
                              />
                            </td>
                            <td className="px-3 py-3 whitespace-nowrap">
                              <div className="leading-snug">
                                <p className="text-sm text-foreground">{cluster.site}</p>
                                <p className="text-xs text-muted-foreground">{cluster.mce}</p>
                              </div>
                            </td>
                            <td className="px-3 py-3">
                              <OwnerCell cluster={cluster} />
                            </td>
                            <td className="px-3 py-3 whitespace-nowrap font-mono text-xs text-muted-foreground">
                              {cluster.mastertag ?? "—"}
                            </td>
                            <td className="px-3 py-3">
                              {cluster.spec_name ? (
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <IntentLink href={`/specs/${encodeURIComponent(cluster.spec_name)}`} className="hover:text-primary transition-colors font-medium whitespace-nowrap">
                                    {cluster.spec_name}
                                  </IntentLink>
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
                            <td className="px-3 py-3 text-muted-foreground whitespace-nowrap">
                              <div className="leading-snug">
                                <p className="text-sm">{cluster.created_by ?? "—"}</p>
                                <p className="text-xs">
                                  {cluster.created_at ? formatDate(cluster.created_at) : ""}
                                </p>
                              </div>
                            </td>
                            <td className="px-3 py-3">
                              {drift ? <FlavorStateBadge row={drift} /> : <Skeleton className="h-5 w-16" />}
                            </td>
                          </tr>
                        </Fragment>
                      );
                    })}
                {!isLoading && clusters?.length === 0 && (
                  <tr>
                    <td colSpan={columns}>
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
                    <td colSpan={columns}>
                      <NoMatches what="clusters" onClear={clearFilters} />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <Pagination page={page} pageSize={pageSize} total={filtered.length} onPage={setPage} />
        </>
      )}
    </div>
  );
}
