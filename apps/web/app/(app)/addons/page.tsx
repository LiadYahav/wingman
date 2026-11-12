"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, ChevronsUpDown, Layers, Package, Pencil, Plus, RefreshCw, Search, Tag } from "lucide-react";
import { api } from "@/lib/api-client";
import { day2Api, day2Keys, syncSummary, teamAccess, uniqueFindings } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { inlineYaml, leaves, pathLabel, toYaml } from "@/lib/values";
import { useIsAdmin } from "@/stores/auth-store";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState, NoMatches } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { FindingsBadge, FindingsList } from "@/components/addons/findings";
import { ChangeResultPanel, type OpenedChanges } from "@/components/addons/change-result";
import { NewAddonDialog } from "@/components/addons/new-addon-dialog";
import { EditTeamDefaultDialog, MakeDefaultDialog } from "@/components/addons/default-dialogs";
import { FleetDefaultsList } from "@/components/addons/fleet-defaults";
import { ReadOnlyBadge, ReadOnlyNote, useTeams } from "@/components/addons/team-access";
import type { AuthoringChange, CatalogEntry, FleetDefault } from "@/types/day2";

/** `HEAD` is the chart repo's default branch, listed first in `available_versions`. */
function revisionLabel(entry: CatalogEntry): string {
  const head = entry.available_versions[0];
  return entry.current_version === "HEAD" && head ? `HEAD (${head})` : entry.current_version;
}

/** What the panel at the top says an authoring write opened. */
function openedFrom(change: AuthoringChange): OpenedChanges {
  const verb = change.action === "create-addon" ? "Create" : change.action === "make-default" ? "Promote" : "Update";
  return { verb, results: [change], failed: [] };
}

/** Write actions on a team: offered to admins, disabled with the reason while the team is read-only (ADR-0043). */
interface TeamWrites {
  isAdmin: boolean;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}

function DefinitionList({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[9rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-xs">
      {items.map(([term, value]) => (
        <div key={term} className="contents">
          <dt className="text-muted-foreground">{term}</dt>
          <dd className="break-all font-mono text-[11px]">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ChartDialog({
  entry,
  open,
  onOpenChange,
  writes,
  onEdit,
  onMakeDefault,
}: {
  entry: CatalogEntry;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  writes: TeamWrites;
  onEdit: () => void;
  onMakeDefault: () => void;
}) {
  const [view, setView] = useState<"table" | "yaml">("table");
  const values = leaves(entry.default_values);
  const meta = entry.argocd_metadata;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="break-words pr-8">{entry.name}</DialogTitle>
          <DialogDescription>
            Team <strong>{entry.team}</strong> · revision <strong className="font-mono">{revisionLabel(entry)}</strong>
          </DialogDescription>
        </DialogHeader>
        <FindingsList findings={entry.warnings} showContext />
        <Tabs defaultValue="values">
          <TabsList>
            <TabsTrigger value="values">Team values</TabsTrigger>
            <TabsTrigger value="deploy">Deploy config</TabsTrigger>
            <TabsTrigger value="versions">Versions</TabsTrigger>
          </TabsList>
          <TabsContent value="values" className="space-y-2 pt-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                <code>operators/{entry.name}/values.yaml</code>: the team default every destination starts from, above the chart&apos;s own values.
              </p>
              {values.length > 0 && (
                <div className="inline-flex shrink-0 rounded-lg border bg-muted/40 p-0.5" role="group" aria-label="View">
                  {(["table", "yaml"] as const).map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setView(v)}
                      aria-pressed={view === v}
                      className={cn(
                        "rounded-md px-2 py-0.5 text-xs font-medium transition-colors",
                        view === v ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {v === "table" ? "Table" : "YAML"}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="max-h-[55vh] overflow-auto">
              {values.length === 0 ? (
                <p className="py-4 text-center text-sm italic text-muted-foreground">The team sets no values: the chart&apos;s own values apply.</p>
              ) : view === "yaml" ? (
                <pre className="whitespace-pre rounded-lg border bg-muted/50 p-4 font-mono text-xs leading-relaxed">{toYaml(entry.default_values)}</pre>
              ) : (
                <table className="w-full border-collapse text-xs">
                  <tbody>
                    {values.map(({ path, value }) => (
                      <tr key={JSON.stringify(path)} className="border-b border-border/50 last:border-0">
                        <td className="w-2/5 break-all px-3 py-1.5 align-top font-mono font-medium">{pathLabel(path)}</td>
                        <td className="break-all px-3 py-1.5 font-mono text-muted-foreground">{inlineYaml(value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </TabsContent>
          <TabsContent value="deploy" className="space-y-3 pt-2">
            <p className="text-xs text-muted-foreground">
              <code>operators/{entry.name}/{entry.name}.yaml</code>: where the chart comes from.
            </p>
            <DefinitionList
              items={[
                [
                  "repourl",
                  meta.repourl || (
                    <span className="inline-flex items-center gap-1 font-sans text-status-warning-fg">
                      <AlertTriangle className="h-3 w-3" />
                      none in lowercase: every install must give one
                    </span>
                  ),
                ],
                ["chart repo", entry.chart_project ?? "not on this GitLab"],
                ["path", meta.path],
                ["targetRevision", revisionLabel(entry)],
                ["projectNamespace", meta.projectNamespace || "—"],
                ["sync", syncSummary(entry.sync)],
                ["syncPolicy", <pre key="sync" className="whitespace-pre-wrap">{toYaml(meta.syncPolicy) || "—"}</pre>],
                ["fleet default on", entry.fleet_defaults.length > 0 ? entry.fleet_defaults.join(", ") : "—"],
              ]}
            />
          </TabsContent>
          <TabsContent value="versions" className="space-y-3 pt-2">
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground">Chart repo branches, default first</p>
              {entry.available_versions.length === 0 ? (
                <p className="text-xs text-muted-foreground">None readable{entry.chart_project ? "" : ": the chart repo is unknown"}.</p>
              ) : (
                <ul className="flex flex-wrap gap-1.5">
                  {entry.available_versions.map((v, i) => (
                    <li key={v} className={cn("rounded-full px-2 py-0.5 font-mono text-xs", i === 0 ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground")}>
                      {v}
                      {i === 0 && <span className="font-sans"> · default</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground">Pins per OCP version (ocp-versions/)</p>
              {entry.ocp_version_pins.length === 0 ? (
                <p className="text-xs text-muted-foreground">None: every OCP version gets {revisionLabel(entry)}.</p>
              ) : (
                <DefinitionList items={entry.ocp_version_pins.map((p) => [p.version, p.target_revision ?? "values only"])} />
              )}
            </div>
          </TabsContent>
        </Tabs>
        {writes.isAdmin && writes.readOnlyReason && <ReadOnlyNote reason={writes.readOnlyReason} />}
        <DialogFooter showCloseButton>
          {writes.isAdmin && (
            <>
              <button
                type="button"
                onClick={onMakeDefault}
                disabled={Boolean(writes.readOnlyReason)}
                title={writes.readOnlyReason ?? "Deploy it to every destination of one kind"}
                className={cn(buttonVariants({ variant: "outline" }), "gap-1.5")}
              >
                <Layers className="h-3.5 w-3.5" />
                Make default
              </button>
              <button
                type="button"
                onClick={onEdit}
                disabled={Boolean(writes.readOnlyReason)}
                title={writes.readOnlyReason ?? undefined}
                className={cn(buttonVariants({ variant: "outline" }), "gap-1.5")}
              >
                <Pencil className="h-3.5 w-3.5" />
                Edit team default
              </button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChartCard({ entry, writes }: { entry: CatalogEntry; writes: TeamWrites }) {
  const [dialog, setDialog] = useState<"details" | "edit" | "default" | null>(null);
  const count = leaves(entry.default_values).length;
  const warned = uniqueFindings(entry.warnings).length > 0;
  return (
    <>
      <button
        type="button"
        onClick={() => setDialog("details")}
        className={cn(
          "w-full rounded-xl border bg-card p-4 text-left shadow-sm transition-[box-shadow,border-color,transform] duration-150 hover:border-primary/30 hover:shadow-md active:scale-[0.99]",
          warned && "border-status-warning/40",
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/8 text-primary dark:bg-primary/15">
              <Package className="h-4 w-4" />
            </span>
            <h3 className="truncate text-sm font-semibold" title={entry.name}>
              {entry.name}
            </h3>
          </div>
          <span className="inline-flex max-w-[45%] shrink-0 items-center gap-1 rounded-full bg-primary/8 px-2 py-0.5 text-xs font-medium text-primary dark:bg-primary/20" title={revisionLabel(entry)}>
            <Tag className="h-2.5 w-2.5 shrink-0" />
            <span className="truncate font-mono">{entry.current_version}</span>
          </span>
        </div>
        <p className="mt-2 truncate text-xs text-muted-foreground" title={entry.argocd_metadata.repourl || undefined}>
          {entry.argocd_metadata.repourl ? (
            entry.argocd_metadata.repourl.replace(/^https?:\/\//, "")
          ) : (
            <span className="inline-flex items-center gap-1 text-status-warning-fg">
              <AlertTriangle className="h-3 w-3" />
              No lowercase repourl
            </span>
          )}
        </p>
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          {entry.fleet_defaults.map((scope) => (
            <span key={scope} className="inline-flex items-center gap-1 rounded-full bg-chart-5/12 px-2 py-0.5 text-xs text-chart-5" title={`A fleet default: deployed to every ${scope} destination`}>
              <Layers className="h-3 w-3" />
              {scope}
            </span>
          ))}
          {entry.ocp_version_pins.length > 0 && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              {entry.ocp_version_pins.length} OCP pin{entry.ocp_version_pins.length === 1 ? "" : "s"}
            </span>
          )}
          <span className="text-xs text-muted-foreground">
            {entry.available_versions.length} version{entry.available_versions.length === 1 ? "" : "s"} · {count} team value{count === 1 ? "" : "s"}
          </span>
          <span className="ml-auto">
            <FindingsBadge findings={entry.warnings} />
          </span>
        </div>
      </button>
      <ChartDialog
        entry={entry}
        open={dialog === "details"}
        onOpenChange={(next) => setDialog(next ? "details" : null)}
        writes={writes}
        onEdit={() => setDialog("edit")}
        onMakeDefault={() => setDialog("default")}
      />
      {dialog === "edit" && (
        <EditTeamDefaultDialog
          entry={entry}
          open
          onOpenChange={(next) => setDialog(next ? "edit" : null)}
          readOnlyReason={writes.readOnlyReason}
          onOpened={writes.onOpened}
        />
      )}
      {dialog === "default" && (
        <MakeDefaultDialog
          entry={entry}
          open
          onOpenChange={(next) => setDialog(next ? "default" : null)}
          readOnlyReason={writes.readOnlyReason}
          onOpened={writes.onOpened}
        />
      )}
    </>
  );
}

function TeamSection({
  team,
  entries,
  fleetDefaults,
  writes,
  catalogNames,
}: {
  team: string;
  entries: CatalogEntry[];
  fleetDefaults: FleetDefault[];
  writes: TeamWrites;
  /** Every catalog name of the team, which a new add-on cannot take (a search may hide some). */
  catalogNames: string[];
}) {
  const [expanded, setExpanded] = useState(true);
  const [creating, setCreating] = useState(false);
  return (
    <section className="space-y-3" aria-label={`Team ${team}`} data-testid={`team-${team}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <button type="button" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded} className="group flex items-center gap-2 text-left">
          <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform duration-150", !expanded && "-rotate-90")} />
          <span className="text-sm font-semibold transition-colors group-hover:text-primary">{team}</span>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">{entries.length}</span>
        </button>
        {writes.readOnlyReason && <ReadOnlyBadge />}
        {writes.isAdmin && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            disabled={Boolean(writes.readOnlyReason)}
            title={writes.readOnlyReason ?? `Add a new add-on to sigs/${team}`}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "ml-auto h-7 gap-1.5")}
          >
            <Plus className="h-3.5 w-3.5" />
            New add-on
          </button>
        )}
      </div>
      {writes.isAdmin && writes.readOnlyReason && <ReadOnlyNote reason={writes.readOnlyReason} className="ml-6" />}
      {expanded && (
        <div className="space-y-4 pl-6">
          {entries.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {entries.map((entry) => (
                <ChartCard key={`${entry.team}/${entry.name}`} entry={entry} writes={writes} />
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              No add-on in <code>operators/</code> yet{writes.isAdmin && !writes.readOnlyReason ? ": add one with New add-on." : "."}
            </p>
          )}
          <FleetDefaultsList
            team={team}
            items={fleetDefaults}
            canWrite={writes.isAdmin}
            readOnlyReason={writes.readOnlyReason}
            onOpened={writes.onOpened}
          />
        </div>
      )}
      {creating && (
        <NewAddonDialog
          team={team}
          open
          onOpenChange={setCreating}
          existing={catalogNames}
          readOnlyReason={writes.readOnlyReason}
          onOpened={writes.onOpened}
        />
      )}
    </section>
  );
}

type Sort = "name-asc" | "name-desc" | "team-asc";

export default function AddonsPage() {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<Sort>("name-asc");
  const [opened, setOpened] = useState<OpenedChanges | null>(null);
  const isAdmin = useIsAdmin();
  const { data, isLoading, isFetching, error, refetch } = useQuery<CatalogEntry[]>({
    queryKey: day2Keys.catalog,
    queryFn: () => api.get<CatalogEntry[]>(day2Api.catalog),
    staleTime: 120_000,
  });
  const teamList = useTeams();
  const fleet = useQuery<FleetDefault[]>({
    queryKey: day2Keys.fleetDefaults,
    queryFn: () => api.get<FleetDefault[]>(day2Api.fleetDefaults()),
    staleTime: 120_000,
  });

  const writesOf = (team: string): TeamWrites => ({
    isAdmin,
    readOnlyReason: teamAccess(teamList.data, team).reason,
    onOpened: (change) => setOpened(openedFrom(change)),
  });

  const needle = search.trim().toLowerCase();
  const filtered = (data ?? [])
    .filter((e) => !needle || e.name.toLowerCase().includes(needle) || e.team.toLowerCase().includes(needle))
    .sort((a, b) =>
      sort === "name-desc"
        ? b.name.localeCompare(a.name)
        : sort === "team-asc"
          ? a.team.localeCompare(b.team) || a.name.localeCompare(b.name)
          : a.name.localeCompare(b.name),
    );
  const byTeam = new Map<string, CatalogEntry[]>();
  for (const entry of filtered) byTeam.set(entry.team, [...(byTeam.get(entry.team) ?? []), entry]);
  // Without a search every team is listed, with or without add-ons: each can get a new one.
  if (!needle) for (const team of teamList.data ?? []) if (!byTeam.has(team.name)) byTeam.set(team.name, []);
  const fleetOf = (team: string) =>
    (fleet.data ?? []).filter(
      (fd) => fd.team === team && (!needle || fd.chart.toLowerCase().includes(needle) || team.toLowerCase().includes(needle)),
    );
  const namesOf = (team: string) => (data ?? []).filter((e) => e.team === team).map((e) => e.name);
  const total = data?.length ?? 0;
  const teams = new Set((data ?? []).map((e) => e.team)).size;
  const warned = (data ?? []).filter((e) => e.warnings.length > 0).length;

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6 lg:p-8">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            Addon Catalog
          </h1>
          {isLoading ? (
            <Skeleton className="mt-1.5 h-4 w-56" />
          ) : (
            <p className="mt-0.5 text-sm text-muted-foreground">
              {data
                ? `${total} chart${total === 1 ? "" : "s"} across ${teams} team${teams === 1 ? "" : "s"}${warned ? ` · ${warned} with warnings` : ""}`
                : "The charts the team repos offer"}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => {
            void refetch();
            void teamList.refetch();
            void fleet.refetch();
          }}
          disabled={isFetching}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          Refresh
        </button>
      </div>

      {opened && <ChangeResultPanel changes={opened} onDismiss={() => setOpened(null)} />}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-40 max-w-sm flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search addons or teams..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border bg-card py-2 pl-9 pr-4 text-sm transition-shadow focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>
        <div className="flex items-center gap-1.5">
          <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground" />
          <div className="flex items-center gap-0.5 rounded-lg border bg-muted/40 p-0.5">
            {(
              [
                ["name-asc", "A→Z"],
                ["name-desc", "Z→A"],
                ["team-asc", "Team"],
              ] as [Sort, string][]
            ).map(([v, label]) => (
              <button
                key={v}
                type="button"
                onClick={() => setSort(v)}
                aria-pressed={sort === v}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  sort === v ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {fleet.error && <ProblemList error={fleet.error} title="The fleet defaults could not be loaded" />}

      {error ? (
        <ProblemList error={error} title="The catalog could not be loaded" />
      ) : isLoading ? (
        <div className="space-y-6">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="space-y-3">
              <Skeleton className="h-5 w-32" />
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 3 }).map((_, j) => (
                  <Skeleton key={j} className="h-28 rounded-xl" />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : byTeam.size === 0 && total > 0 ? (
        <NoMatches what="charts" onClear={() => setSearch("")} clearLabel="Clear search" bordered />
      ) : (
        <div className="space-y-8">
          {total === 0 && (
            <EmptyState
              icon={Package}
              bordered
              title="No charts yet"
              description={
                <>
                  A team&apos;s charts appear here once its repo has <code>operators/&lt;chart&gt;/</code>
                  {isAdmin && byTeam.size > 0 ? ": add one with a team's New add-on." : "."}
                </>
              }
              data-testid="catalog-empty"
            />
          )}
          {[...byTeam.entries()]
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([team, entries]) => (
              <TeamSection
                key={team}
                team={team}
                entries={entries}
                fleetDefaults={fleetOf(team)}
                writes={writesOf(team)}
                catalogNames={namesOf(team)}
              />
            ))}
        </div>
      )}
    </div>
  );
}
