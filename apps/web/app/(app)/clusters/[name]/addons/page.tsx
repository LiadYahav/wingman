"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Layers, Package, PackageCheck, RefreshCw, Users } from "lucide-react";
import { api } from "@/lib/api-client";
import {
  candidatesOf,
  chartsHref,
  day2Api,
  day2Keys,
  isDestinationId,
  keyFromParam,
  problemOf,
  teamAccess,
} from "@/lib/day2";
import { cn } from "@/lib/utils";
import { useIsAdmin } from "@/stores/auth-store";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { FindingsList } from "@/components/addons/findings";
import { ArgoNote, DestinationFacts, UpgradeCheckPanel } from "@/components/addons/destination-header";
import { InstalledChartCard, type DestinationRef } from "@/components/addons/installed-chart-card";
import { AvailableChartCard, type InstallChoice } from "@/components/addons/available-chart-card";
import { BulkInstallBar, BulkInstallDialog, chartKey } from "@/components/addons/bulk-install";
import { ChangeResultPanel, type OpenedChanges } from "@/components/addons/change-result";
import { ReadOnlyNote, useTeams } from "@/components/addons/team-access";
import type { CatalogEntry, Destination, DestinationCharts, GitLabInfo } from "@/types/day2";

/** Don't retry what the service refused (404 unknown, 422 ambiguous); retry the rest once. */
function retryUnlessRefused(failures: number, error: unknown): boolean {
  const { status } = problemOf(error);
  return failures < 1 && !(status !== undefined && status < 500);
}

function groupByTeam<T extends { team: string }>(items: T[]): [string, T[]][] {
  const groups = new Map<string, T[]>();
  for (const item of items) groups.set(item.team, [...(groups.get(item.team) ?? []), item]);
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

/** `count` is left out when it is unknown (its read failed). */
function SectionHeading({ title, count, children }: { title: string; count?: number; children?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b pb-1">
      <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider">
        {title}
        {count !== undefined && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums text-muted-foreground">{count}</span>
        )}
      </h2>
      {children}
    </div>
  );
}

/** The installed section while the charts load: its heading, the Argo note and a team of cards. */
function ChartsSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" data-testid="charts-loading">
      <div className="flex items-center gap-2 border-b pb-1.5">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-5 w-7 rounded-full" />
      </div>
      <Skeleton className="h-3.5 w-3/4" />
      {Array.from({ length: 2 }).map((_, i) => (
        <div key={i} className="space-y-2">
          <div className="flex items-center gap-2">
            <Skeleton className="h-3.5 w-3.5 rounded-full" />
            <Skeleton className="h-3.5 w-28" />
          </div>
          <div className="space-y-2 pl-5">
            {Array.from({ length: 2 - i }).map((_, j) => (
              <Skeleton key={j} className="h-14 rounded-xl" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function TeamHeading({ team, count, readOnlyReason }: { team: string; count: number; readOnlyReason?: string | null }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <Users className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{team}</span>
        <span className="text-xs tabular-nums text-muted-foreground">({count})</span>
      </div>
      {/* The team has not given Wingman write access (ADR-0043): its charts here are read-only. */}
      {readOnlyReason && <ReadOnlyNote reason={readOnlyReason} className="ml-5" />}
    </div>
  );
}

/** A bare name that several destinations share: pick one by id (ADR-0020). */
function CandidatePicker({ name, candidates }: { name: string; candidates: string[] }) {
  return (
    <div className="space-y-3 rounded-xl border bg-card p-5">
      <p className="text-sm">
        <strong>{name}</strong> names {candidates.length} destinations. Pick the one you mean:
      </p>
      <ul className="space-y-1.5">
        {candidates.map((id) => (
          <li key={id}>
            <Link
              href={chartsHref(id)}
              className="block break-all rounded-lg border px-3 py-2 font-mono text-xs transition-colors hover:border-primary/50 hover:bg-primary/5"
            >
              {id}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ClusterCharts() {
  const params = useParams<{ name: string }>();
  const searchParams = useSearchParams();
  const key = keyFromParam(params.name);
  const mce = searchParams.get("mce") ?? undefined;
  const isAdmin = useIsAdmin();

  const [opened, setOpened] = useState<OpenedChanges | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [choices, setChoices] = useState<Record<string, InstallChoice>>({});
  const [bulkOpen, setBulkOpen] = useState(false);

  // Both resolve a bare name; asked together so neither waits for the other.
  const charts = useQuery<DestinationCharts>({
    queryKey: day2Keys.charts(key, mce),
    queryFn: () => api.get<DestinationCharts>(day2Api.charts(key, mce)),
    staleTime: 30_000,
    retry: retryUnlessRefused,
  });
  const destination = useQuery<Destination>({
    queryKey: [...day2Keys.destinations, "one", key, mce ?? ""],
    queryFn: () => api.get<Destination>(day2Api.destination(key, mce)),
    staleTime: 60_000,
    retry: retryUnlessRefused,
  });
  const catalog = useQuery<CatalogEntry[]>({
    queryKey: day2Keys.catalog,
    queryFn: () => api.get<CatalogEntry[]>(day2Api.catalog),
    staleTime: 120_000,
  });
  const teams = useTeams();
  const accessOf = (team: string) => teamAccess(teams.data, team);
  const gitlabInfo = useQuery<GitLabInfo>({
    queryKey: day2Keys.gitlabInfo,
    queryFn: () => api.get<GitLabInfo>(day2Api.gitlabInfo),
    staleTime: 300_000,
  });
  // An ambiguous bare name: the candidates come with the 422, or from the destination list.
  const ambiguous = Boolean(charts.error) && !isDestinationId(key);
  const all = useQuery<Destination[]>({
    queryKey: day2Keys.destinations,
    queryFn: () => api.get<Destination[]>(day2Api.destinations),
    enabled: ambiguous,
    staleTime: 60_000,
  });

  const data = charts.data;
  const installed = data?.installed ?? [];
  const installedKeys = new Set(installed.map(chartKey));
  const available = (catalog.data ?? []).filter((e) => !installedKeys.has(chartKey(e)));
  const excludedKeys = new Set((data?.excluded ?? []).map(chartKey));
  // The service refuses writes to a destination whose env it cannot place (rule env-unknown).
  const writable = Boolean(data) && (data?.kind === "hub" || Boolean(data?.env));
  const canWrite = isAdmin && writable;
  const ref: DestinationRef | null = data ? { id: data.id, name: data.cluster, kind: data.kind } : null;
  const selectable = available.filter((e) => accessOf(e.team).writable);
  const selectedEntries = available.filter((e) => selected.has(chartKey(e)));
  const isFetching = charts.isFetching || catalog.isFetching;

  const backHref =
    data?.kind === "hosted" && destination.data?.in_day1 !== false
      ? `/clusters/${encodeURIComponent(data.cluster)}?site=${encodeURIComponent(data.site)}&mce=${encodeURIComponent(data.mce)}`
      : "/destinations";

  function showOpened(changes: OpenedChanges) {
    setOpened(changes);
    void charts.refetch();
  }

  function toggle(entry: CatalogEntry, on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(chartKey(entry));
      else next.delete(chartKey(entry));
      return next;
    });
  }

  function clearSelection() {
    setSelected(new Set());
    setChoices({});
  }

  let body: React.ReactNode;
  if (charts.error) {
    const problem = problemOf(charts.error);
    const fromList = (all.data ?? []).filter((d) => d.name === key && (!mce || d.mce === mce)).map((d) => d.id);
    const candidates = candidatesOf(problem).length > 0 ? candidatesOf(problem) : fromList;
    body =
      candidates.length > 1 ? (
        <CandidatePicker name={key} candidates={candidates} />
      ) : (
        <div className="space-y-3">
          <ProblemList error={charts.error} title={`The charts of ${key} could not be loaded`} />
          <Link href="/destinations" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Browse destinations
          </Link>
        </div>
      );
  } else if (!data || !ref || catalog.isLoading) {
    body = <ChartsSkeleton />;
  } else {
    body = (
      <div className="space-y-10">
        <section className="space-y-4" aria-label="Installed">
          <SectionHeading title="Installed" count={installed.length} />
          <ArgoNote note={data.argocd_note} />
          {installed.length === 0 ? (
            <EmptyState
              icon={Package}
              bordered
              title={`No team deploys a chart to ${data.cluster} yet`}
              description={
                available.length === 0
                  ? undefined
                  : canWrite
                    ? "Install one from the Available charts below."
                    : "The charts that can be installed here are listed under Available below."
              }
              data-testid="installed-empty"
            />
          ) : (
            <div className="space-y-6">
              {groupByTeam(installed).map(([team, items]) => (
                <div key={team} className="space-y-2">
                  <TeamHeading team={team} count={items.length} readOnlyReason={canWrite ? accessOf(team).reason : null} />
                  <div className="space-y-2 pl-5">
                    {[...items]
                      .sort((a, b) => Number(a.source === "fleet-default") - Number(b.source === "fleet-default") || a.name.localeCompare(b.name))
                      .map((chart) => (
                        <InstalledChartCard
                          key={chartKey(chart)}
                          chart={chart}
                          destination={ref}
                          catalog={catalog.data?.find((e) => chartKey(e) === chartKey(chart))}
                          isAdmin={canWrite && accessOf(team).writable}
                          lastOfTeam={items.filter((c) => c.source === "cluster").length === 1}
                          onOpened={showOpened}
                          reloadChart={async () =>
                            (await charts.refetch()).data?.installed.find((c) => chartKey(c) === chartKey(chart))
                          }
                        />
                      ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          {data.excluded.length > 0 && (
            <div className="space-y-1.5 rounded-xl border bg-muted/20 p-4">
              <p className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
                <Layers className="h-3.5 w-3.5" />
                Fleet defaults excluded here by exclusions.yaml
              </p>
              <ul className="flex flex-wrap gap-1.5">
                {data.excluded.map((e) => (
                  <li key={`${chartKey(e)}|${e.scope}`} className="rounded-md border bg-card px-2 py-0.5 font-mono text-[11px]">
                    {e.team}/{e.name} <span className="text-muted-foreground">· {e.scope}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.kind !== "hub" && <UpgradeCheckPanel clusterId={data.id} from={data.ocp_version} />}
        </section>

        {!catalog.data ? (
          <section className="space-y-4" aria-label="Available">
            <SectionHeading title="Available" />
            {catalog.error ? (
              <ProblemList error={catalog.error} title="The catalog could not be loaded, so the charts to install are unknown" />
            ) : (
              <Skeleton className="h-14 rounded-xl" />
            )}
          </section>
        ) : available.length === 0 ? (
          <section className="space-y-4" aria-label="Available">
            <SectionHeading title="Available" count={0} />
            {catalog.data.length === 0 ? (
              <EmptyState
                icon={Package}
                bordered
                title="The catalog is empty"
                description={
                  <>
                    A team&apos;s charts appear here once its repo has <code>operators/&lt;chart&gt;/</code>.
                  </>
                }
                data-testid="available-empty"
              />
            ) : (
              <EmptyState
                icon={PackageCheck}
                bordered
                title="Every catalog chart is installed here"
                data-testid="available-empty"
              />
            )}
          </section>
        ) : (
          <section className="space-y-4" aria-label="Available">
            <SectionHeading title="Available" count={available.length}>
              {canWrite && selectable.length > 0 && (
                <button
                  type="button"
                  onClick={() =>
                    selected.size === selectable.length
                      ? clearSelection()
                      : setSelected(new Set(selectable.map(chartKey)))
                  }
                  className="text-xs text-muted-foreground transition-colors hover:text-primary"
                >
                  {selected.size === selectable.length ? "Deselect all" : "Select all"}
                </button>
              )}
            </SectionHeading>
            <div className="space-y-6">
              {groupByTeam(available).map(([team, items]) => (
                <div key={team} className="space-y-2">
                  <TeamHeading team={team} count={items.length} readOnlyReason={canWrite ? accessOf(team).reason : null} />
                  <div className="space-y-2 pl-5">
                    {items.map((entry) => (
                      <AvailableChartCard
                        key={chartKey(entry)}
                        entry={entry}
                        destination={ref}
                        isAdmin={canWrite}
                        readOnlyReason={accessOf(team).reason}
                        excludedHere={excludedKeys.has(chartKey(entry))}
                        selected={selected.has(chartKey(entry))}
                        onSelectChange={(on) => toggle(entry, on)}
                        selecting={selected.size > 0}
                        onOpened={showOpened}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    );
  }

  return (
    <div className={cn("mx-auto max-w-4xl space-y-6 p-6 lg:p-8", selected.size > 0 && "pb-24")}>
      <header className="flex flex-wrap items-start gap-3">
        <Link href={backHref} className={buttonVariants({ variant: "ghost", size: "icon" })} aria-label="Back">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="min-w-0 flex-1 basis-60 space-y-1">
          <h1 className="break-words text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            {data?.cluster ?? key}
            <span className="text-muted-foreground"> · Charts</span>
          </h1>
          {data ? (
            <DestinationFacts charts={data} destination={destination.data} />
          ) : (
            !charts.error && <Skeleton className="h-4 w-72" />
          )}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          {gitlabInfo.data?.sigs_group_url && (
            <a
              href={gitlabInfo.data.sigs_group_url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
              title="The team repos in GitLab"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              GitLab
            </a>
          )}
          <button
            type="button"
            onClick={() => {
              void charts.refetch();
              void catalog.refetch();
            }}
            disabled={isFetching}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            Refresh
          </button>
        </div>
      </header>

      {opened && <ChangeResultPanel changes={opened} onDismiss={() => setOpened(null)} />}

      {data && (
        <>
          <FindingsList findings={data.warnings} showContext />
          {isAdmin && !writable && (
            <p className="rounded-lg border border-status-warning/30 bg-status-warning/8 px-3 py-2 text-xs text-status-warning-fg">
              {data.cluster}&apos;s env is unknown, so Wingman cannot write to it: place it in a team repo first.
            </p>
          )}
        </>
      )}

      {body}

      {ref && (
        <>
          <BulkInstallBar count={selected.size} onClear={clearSelection} onInstall={() => setBulkOpen(true)} />
          <BulkInstallDialog
            open={bulkOpen}
            onOpenChange={setBulkOpen}
            entries={selectedEntries}
            choices={choices}
            onChoiceChange={(k, choice) => setChoices((prev) => ({ ...prev, [k]: choice }))}
            destination={ref}
            onOpened={(changes) => {
              showOpened(changes);
              clearSelection();
            }}
          />
        </>
      )}
    </div>
  );
}

export default function ClusterChartsPage() {
  return (
    <Suspense>
      <ClusterCharts />
    </Suspense>
  );
}

