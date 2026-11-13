"use client";

import { useMemo } from "react";
import type { VisibilityState } from "@tanstack/react-table";
import { Info, Lock, Network, TriangleAlert, Unplug } from "lucide-react";
import { toast } from "sonner";
import { ColumnPicker } from "@/components/data-table/column-picker";
import { DataTable } from "@/components/data-table/data-table";
import { downloadCsv } from "@/components/data-table/download";
import { useDataTable } from "@/components/data-table/use-data-table";
import { useStoredVisibility } from "@/components/data-table/use-stored-visibility";
import { EmptyState, NoMatches } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessages, isApiError } from "@/lib/api-client";
import { useRefreshSegments, useSegmentList, useSegmentSites, useSegmentStats } from "@/lib/api/segments";
import { COLUMN_IDS, COLUMN_LABELS, isColumnId } from "@/lib/segments/columns";
import { segmentsCsv } from "@/lib/segments/csv";
import { baseSegments, shownSegments, statusCounts } from "@/lib/segments/filter";
import { clearFilters, isFiltered, nextSort, type SegmentsView } from "@/lib/segments/view";
import { describeFilter, setColumnFilter } from "@/lib/table/column-filters";
import type { Segment, SegmentList } from "@/types/segments";
import { SEGMENT_COLUMNS } from "./segment-columns";
import { SegmentsHeader } from "./segments-header";
import { FilterChip, MismatchToggle, SegmentSearch, SiteFilter, StatusTabs } from "./segments-toolbar";
import { SiteCards, SiteCardsSkeleton } from "./site-cards";
import { useSearchDraft, useSegmentsView } from "./use-segments-view";

const COLUMNS_KEY = "wingman-segments-columns";

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Why the page cannot show segments at all: not an admin, or segments-manager not configured. */
function Blocked({ error }: { error: unknown }) {
  if (isApiError(error, "FORBIDDEN")) {
    return (
      <EmptyState
        icon={Lock}
        bordered
        title="For admins"
        description="Segments is for Wingman's admins for now, until Wingman has finer roles."
        data-testid="segments-forbidden"
      />
    );
  }
  return (
    <EmptyState
      icon={Unplug}
      bordered
      title="Segments is not set up"
      description="Wingman shows segments-manager's segments once day1 knows where it is: set segmentsManager.url in the chart (SEGMENTS_MANAGER_URL)."
      data-testid="segments-off"
    />
  );
}

/** What the answer could not carry: records day1 could not read, cluster files it could not read, a failed re-read. */
function Notices({ data, error }: { data: SegmentList; error: unknown }) {
  return (
    <>
      {error !== null && (
        <ProblemList error={error} title="The last re-read failed; this is the read before it" />
      )}
      {data.unreadable.length > 0 && (
        <div role="status" data-testid="segments-unreadable" className="rounded-lg border border-status-warning/40 bg-status-warning/10 px-3.5 py-3 text-sm text-status-warning-fg">
          <p className="flex items-center gap-2 font-medium">
            <TriangleAlert aria-hidden className="h-4 w-4 shrink-0" />
            {plural(data.unreadable.length, "record")} from segments-manager could not be read and {data.unreadable.length === 1 ? "is" : "are"} not shown
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-10 text-xs">
            {data.unreadable.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </div>
      )}
      {data.clusters_error && (
        <p role="status" data-testid="segments-clusters-error" className="flex items-start gap-2 text-xs text-muted-foreground">
          <Info aria-hidden className="mt-px h-3.5 w-3.5 shrink-0" />
          <span>The day1 repo could not be read, so clusters are not linked: {data.clusters_error}</span>
        </p>
      )}
    </>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-2 rounded-xl border bg-card p-3" aria-busy="true">
      {Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-6 w-full" />)}
    </div>
  );
}

interface TableProps {
  data: SegmentList;
  /** The rows before the column filters: the header popovers list their values from them. */
  base: Segment[];
  /** The rows the view shows, in its order. */
  shown: Segment[];
  view: SegmentsView;
  setView: (v: SegmentsView) => void;
  sites: string[];
  visibility: VisibilityState;
  onVisibility: (next: VisibilityState) => void;
}

/** The table and everything that filters it. */
function SegmentsTable({ data, base, shown, view, setView, sites, visibility, onVisibility }: TableProps) {
  const search = useSearchDraft(view.q, (q) => setView({ ...view, q }));
  const counts = useMemo(() => statusCounts(data.segments, view), [data.segments, view]);
  const disagreeing = useMemo(() => data.segments.filter((s) => s.mismatches.length > 0).length, [data.segments]);
  const table = useDataTable<Segment>({
    data: shown,
    columns: SEGMENT_COLUMNS,
    getRowId: (s) => s.segment,
    columnVisibility: visibility,
    onColumnVisibilityChange: onVisibility,
  });
  const clear = () => {
    search.setDraft("");
    setView(clearFilters(view));
  };
  return (
    <section aria-label="Segments" className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <SegmentSearch value={search.draft} onChange={search.setDraft} onCommit={search.flush} />
        <StatusTabs value={view.status} counts={counts} onChange={(status) => setView({ ...view, status })} />
        <div className="flex-1" />
        <ColumnPicker table={table} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <SiteFilter sites={sites} value={view.site} onChange={(site) => setView({ ...view, site })} />
        <MismatchToggle count={disagreeing} value={view.mismatch} onChange={(mismatch) => setView({ ...view, mismatch })} />
        {view.cluster && <FilterChip label="Cluster" value={view.cluster} onRemove={() => setView({ ...view, cluster: null })} />}
        {COLUMN_IDS.filter((id) => view.filters[id]).map((id) => (
          <FilterChip
            key={id}
            label={COLUMN_LABELS[id]}
            value={describeFilter(view.filters[id])}
            column
            onRemove={() => setView({ ...view, filters: setColumnFilter(view.filters, id, null, []) })}
          />
        ))}
      </div>
      <DataTable
        table={table}
        label="Segments"
        sort={view.sort}
        onSort={(id) => isColumnId(id) && setView({ ...view, sort: nextSort(view.sort, id) })}
        filters={{ rows: base, value: view.filters, onChange: (filters) => setView({ ...view, filters }) }}
        rowProps={(s) => ({
          "data-testid": "segment-row",
          "data-segment": s.segment,
          "data-mismatch": s.mismatches.length > 0 ? "true" : undefined,
          className: s.mismatches.length > 0 ? "bg-status-warning/5" : undefined,
        })}
        className="max-h-[70vh]"
        empty={
          data.segments.length === 0 ? (
            <EmptyState icon={Network} title="No segments" description="segments-manager has no segments yet." data-testid="segments-empty" />
          ) : (
            <NoMatches what="segments" onClear={clear} data-testid="segments-no-matches" />
          )
        }
      />
    </section>
  );
}

export function SegmentsPage() {
  const [view, setView] = useSegmentsView();
  const list = useSegmentList();
  const stats = useSegmentStats();
  const sites = useSegmentSites();
  const { refresh, refreshing } = useRefreshSegments();
  const [visibility, setVisibility] = useStoredVisibility(COLUMNS_KEY);
  const blocked = isApiError(list.error, "FORBIDDEN") || isApiError(list.error, "FEATURE_DISABLED");
  const data = list.data;
  const base = useMemo(() => (data ? baseSegments(data.segments, view) : []), [data, view]);
  const shown = useMemo(() => (data ? shownSegments(data.segments, view) : []), [data, view]);
  const siteNames = sites.data?.sites ?? stats.data?.sites.map((s) => s.site) ?? [];

  const onRefresh = async () => {
    try {
      const read = await refresh();
      toast.success(read.fresh ? "Read fresh from segments-manager" : "Read fresh a moment ago: showing that read");
    } catch (error) {
      toast.error(`Refresh failed: ${errorMessages(error)[0]}`);
    }
  };
  const onCsv = () => {
    // What is shown: the rows after every filter and the search, in the shown order and columns
    const columns = COLUMN_IDS.filter((id) => visibility[id] !== false);
    downloadCsv("segments.csv", segmentsCsv(shown, columns));
  };
  const summary = !data
    ? "segments-manager's segments, per site"
    : isFiltered(view)
      ? `${shown.length} of ${plural(data.segments.length, "segment")}`
      : `${plural(data.segments.length, "segment")} in ${plural(siteNames.length, "site")}`;

  return (
    <div className="mx-auto max-w-[1600px] space-y-5 p-6 lg:p-8">
      <SegmentsHeader
        summary={summary}
        updatedAt={data ? list.dataUpdatedAt : null}
        shown={data && !blocked ? shown.length : null}
        refreshing={refreshing}
        onRefresh={() => void onRefresh()}
        onCsv={onCsv}
      />
      {blocked ? (
        <Blocked error={list.error} />
      ) : list.isPending ? (
        <>
          <SiteCardsSkeleton />
          <TableSkeleton />
        </>
      ) : !data ? (
        <ProblemList error={list.error} title="Segments could not be loaded" />
      ) : (
        <>
          {stats.data ? (
            <SiteCards stats={stats.data.sites} site={view.site} onSite={(site) => setView({ ...view, site })} />
          ) : stats.error ? (
            <ProblemList error={stats.error} title="The site cards could not be loaded" />
          ) : (
            <SiteCardsSkeleton />
          )}
          <Notices data={data} error={list.error} />
          <SegmentsTable
            data={data}
            base={base}
            shown={shown}
            view={view}
            setView={setView}
            sites={siteNames}
            visibility={visibility}
            onVisibility={setVisibility}
          />
        </>
      )}
    </div>
  );
}
