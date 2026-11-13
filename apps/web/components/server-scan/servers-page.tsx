"use client";

import { useMemo, useState } from "react";
import { SearchX, ServerOff } from "lucide-react";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { DataTable } from "@/components/data-table/data-table";
import { downloadCsv, downloadXlsx } from "@/components/data-table/download";
import { Pager } from "@/components/data-table/pager";
import { useDataTable } from "@/components/data-table/use-data-table";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSearchDraft } from "@/hooks/use-search-draft";
import { errorMessages } from "@/lib/api-client";
import { useServerScanServers, useServerScanSites } from "@/lib/api/server-scan";
import { isSortableField, parseSearch } from "@/lib/server-scan/rows";
import { SHEET_NAME, exportName, serversCsv, serversTable } from "@/lib/server-scan/servers-export";
import { serversModel, type ServersModel } from "@/lib/server-scan/servers-model";
import { clearFilters, filterChips, nextSort, toggleValue, withChange, type ServersView } from "@/lib/server-scan/servers-view";
import { OPENSHIFT_STATES, SOURCE_PROVIDERS } from "@/lib/server-scan/vocabulary";
import { formatDateTime, plural } from "@/lib/utils";
import type { SiteStats } from "@/types/server-scan";
import type { ServerRow, ServerRowsAnswer } from "@/types/server-scan-servers";
import { Blocked, isBlocked } from "./blocked";
import { ClusterSidebar } from "./cluster-sidebar";
import { rowAccent, serverColumns } from "./server-columns";
import { ActiveFilters, ServerDropdowns, ServerExports, ServerSearch, ServerToggles } from "./servers-toolbar";
import { useServersView } from "./use-servers-view";

/** server-scan's search waits this long after the last key before it filters. */
const SEARCH_PAUSE_MS = 300;

function Loading() {
  return (
    <div className="space-y-2 rounded-xl border bg-card p-3" aria-busy="true" data-testid="ss-servers-loading">
      {Array.from({ length: 10 }, (_, i) => (
        <Skeleton key={i} className="h-7 w-full" />
      ))}
    </div>
  );
}

/** The Site dropdown's options: server-scan's sites in its order; without them, the sites the rows name. */
function siteOptions(items: SiteStats[] | undefined, model: ServersModel, selected: string[]) {
  const named = (items ?? []).map((site) => ({ value: site.site_id, label: site.name }));
  const known = new Set(named.map((s) => s.value));
  const extra = [...Object.keys(model.facets.site_id), ...selected].filter((id) => !known.has(id));
  return [...named, ...[...new Set(extra)].map((id) => ({ value: id, label: id }))];
}

function useExports(rows: ServerRow[]) {
  const [exporting, setExporting] = useState(false);
  const onCsv = () => downloadCsv(exportName(new Date(), "csv"), serversCsv(rows));
  const onExcel = async () => {
    setExporting(true);
    try {
      await downloadXlsx(exportName(new Date(), "xlsx"), serversTable(rows), SHEET_NAME);
    } catch (error) {
      toast.error(`Excel export failed: ${errorMessages(error)[0]}`);
    } finally {
      setExporting(false);
    }
  };
  return { exporting, onCsv, onExcel: () => void onExcel() };
}

interface FleetProps {
  data: ServerRowsAnswer;
  model: ServersModel;
  /** A failed re-read: the rows shown are the read before it. */
  error: unknown;
  view: ServersView;
  setView: (next: ServersView) => void;
  sites: SiteStats[] | undefined;
}

/** The fleet: the cluster sidebar, the filters, the table and its pages. */
function Fleet({ data, model, error, view, setView, sites }: FleetProps) {
  const search = useSearchDraft(view.search, (q) => setView(withChange(view, { search: q })), SEARCH_PAUSE_MS);
  const searchError = useMemo(() => parseSearch(search.draft).error, [search.draft]);
  const siteList = siteOptions(sites, model, view.multi.site_id);
  const columns = useMemo(() => serverColumns(model.withMce), [model.withMce]);
  const table = useDataTable<ServerRow>({
    data: model.page.items,
    columns,
    getRowId: (row) => row.id,
    columnVisibility: {},
    onColumnVisibilityChange: () => {},
  });
  const chips = filterChips(view, {
    site: (id) => siteList.find((s) => s.value === id)?.label ?? id,
    source: (value) => SOURCE_PROVIDERS.find((s) => s.value === value)?.label ?? value,
    state: (value) => OPENSHIFT_STATES.find((s) => s.value === value)?.label ?? value,
  });
  const exports = useExports(model.matched);
  const clear = () => {
    search.setDraft("");
    setView(clearFilters(view));
  };
  const empty =
    data.items.length === 0 ? (
      <EmptyState icon={ServerOff} title="No servers yet" description="server-scan has collected no server. Its collectors fill this page, every few hours." data-testid="ss-servers-empty" />
    ) : (
      <EmptyState
        icon={SearchX}
        title="No servers match"
        description={chips.length > 0 ? `No servers match: ${chips.map((c) => c.label).join(", ")}.` : "No servers match the current filters."}
        action={
          <button type="button" onClick={clear} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Clear filters
          </button>
        }
        data-testid="ss-servers-no-matches"
      />
    );

  return (
    <div className="flex items-start gap-4">
      <ClusterSidebar
        facets={model.clusters}
        mce={view.multi.mce}
        cluster={view.multi.cluster}
        onToggle={(key, value) => setView(toggleValue(view, key, value))}
      />
      <section aria-label="Servers" className="min-w-0 flex-1 space-y-3">
        {error !== null && <ProblemList error={error} title="The last re-read failed; these are the servers read before it" />}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <ServerSearch value={search.draft} error={searchError} onChange={search.setDraft} onCommit={search.flush} />
          <ServerExports shown={model.matched.length} {...exports} />
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <ServerDropdowns view={view} setView={setView} facets={model.facets} sites={siteList} />
        </div>
        <ServerToggles view={view} setView={setView} total={model.matched.length} />
        <ActiveFilters
          chips={chips}
          view={view}
          setView={(next) => {
            if (next.search !== view.search) search.setDraft(next.search);
            setView(next);
          }}
          onClear={clear}
        />
        <DataTable
          table={table}
          label="Servers"
          sort={{ id: view.sort, desc: view.sortDesc }}
          onSort={(id) => isSortableField(id) && setView(nextSort(view, id))}
          filters={{ rows: model.base, value: view.columns, onChange: (columns) => setView(withChange(view, { columns })) }}
          rowProps={(row) => ({ "data-testid": "ss-server-row", "data-server": row.name, className: rowAccent(row) })}
          className="max-h-[70vh]"
          empty={empty}
        />
        {model.matched.length > 0 && <Pager page={model.page.page} pageCount={model.page.pageCount} onPage={(page) => setView({ ...view, page })} />}
      </section>
    </div>
  );
}

/** "Servers", how many the filters keep, and when server-scan's inventory last changed. */
function Header({ data, shown }: { data: ServerRowsAnswer | undefined; shown: number | null }) {
  return (
    <header>
      <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
        Servers
      </h1>
      <p className="mt-0.5 text-sm text-muted-foreground" aria-live="polite">
        <span data-testid="ss-servers-summary">{shown === null ? "Browse and filter discovered servers." : plural(shown, "server")}</span>
        {data?.generated_at && (
          <span className="ml-2 text-xs" data-testid="ss-servers-updated">
            Updated {formatDateTime(data.generated_at)}
          </span>
        )}
      </p>
    </header>
  );
}

/**
 * The Server Scan area's second page (ADR-0048's 3.23.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §8): server-scan's Servers
 * page, the fleet filtered, searched, sorted and paged in the browser, every
 * filter in the URL under server-scan's names. Read every 30 seconds.
 */
export function ServersPage() {
  const [view, setView] = useServersView();
  const servers = useServerScanServers();
  const sites = useServerScanSites();
  const blocked = isBlocked(servers.error);
  const data = blocked ? undefined : servers.data;
  const model = useMemo(() => (data ? serversModel(data.items, view) : null), [data, view]);
  return (
    <div className="space-y-5 p-6 lg:p-8">
      <Header data={data} shown={model ? model.matched.length : null} />
      {blocked ? (
        <Blocked error={servers.error} />
      ) : servers.isPending ? (
        <Loading />
      ) : !data || !model ? (
        <ProblemList error={servers.error} title="The servers could not be loaded from server-scan" />
      ) : (
        <Fleet data={data} model={model} error={servers.error} view={view} setView={setView} sites={sites.data?.items} />
      )}
    </div>
  );
}
