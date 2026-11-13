"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Boxes, GitBranch, Layers, Pencil, RefreshCw } from "lucide-react";
import { api } from "@/lib/api-client";
import { FLEET_SCOPES, day2Api, day2Keys, keyFromParam, problemOf, syncSummary, teamAddonsHref } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { ignoreDifferencesText } from "@/lib/values";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, EmptyStateLink } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { ChangeResultPanel, type OpenedChanges } from "@/components/addons/change-result";
import { EditAddonDialog } from "@/components/addons/default-dialogs";
import { FindingsList } from "@/components/addons/findings";
import { ReadOnlyBadge, ReadOnlyNote } from "@/components/addons/team-access";
import { Breadcrumbs, PageTitle, useAddonAccess } from "@/components/addons/page-header";
import { RepoFileView } from "@/components/addons/repo-file";
import { ScopePanelCard, type AddonWrites } from "@/components/addons/scope-panel";
import { ValuesLevels } from "@/components/addons/values-levels";
import type { AuthoringChange, CatalogEntry, AddonDetail, ScopePanel } from "@/types/day2";

const VERB: Record<string, OpenedChanges["verb"]> = { "create-addon": "Create", "make-default": "Promote" };

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

function Card({ title, icon: Icon, action, children, label }: { title: string; icon: typeof Boxes; action?: React.ReactNode; children: React.ReactNode; label: string }) {
  return (
    <section className="space-y-4 rounded-xl border bg-card p-4 shadow-sm sm:p-5" aria-label={label}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Icon className="h-4 w-4 text-muted-foreground" aria-hidden />
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** `HEAD` is the chart repo's default branch, listed first in `available_versions`. */
function revisionLabel(entry: CatalogEntry): string {
  const head = entry.available_versions[0];
  return entry.current_version === "HEAD" && head ? `HEAD (${head})` : entry.current_version;
}

/** The add-on itself, `operators/<chart>/`: where it deploys from and how, and its Sig values. */
function AddonFiles({ detail, writes }: { detail: AddonDetail; writes: AddonWrites }) {
  const [editing, setEditing] = useState(false);
  const entry = detail.catalog;
  const meta = entry?.argocd_metadata;
  return (
    <Card
      title="Add-on"
      icon={Boxes}
      label="Add-on"
      action={
        entry &&
        writes.isAdmin && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            disabled={Boolean(writes.readOnlyReason)}
            title={writes.readOnlyReason ?? undefined}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7 gap-1.5")}
          >
            <Pencil className="h-3 w-3" />
            Edit add-on
          </button>
        )
      }
    >
      {!entry ? (
        <p className="rounded-lg border border-dashed px-3 py-3 text-xs text-muted-foreground">
          {detail.name} is not in {detail.team}&apos;s catalog: there is no <code>operators/{detail.name}/</code>, only the fleet
          defaults below. Their own files are the whole deploy config.
        </p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            <code>operators/{detail.name}/</code>: where the chart comes from, how ArgoCD syncs it, and its Sig values.
          </p>
          <DefinitionList
            items={[
              [
                "repourl",
                meta?.repourl || (
                  <span className="inline-flex items-center gap-1 font-sans text-status-warning-fg">
                    <AlertTriangle className="h-3 w-3" />
                    none in lowercase: every install must give one
                  </span>
                ),
              ],
              ["chart repo", entry.chart_project ?? "not on this GitLab"],
              ["targetRevision", revisionLabel(entry)],
              ["path", meta?.path || "."],
              ["projectNamespace", meta?.projectNamespace || "—"],
              ["sync", syncSummary(entry.sync)],
              [
                "ignoreDifferences",
                entry.ignore_differences && entry.ignore_differences.length > 0 ? (
                  <pre key="ignore" className="whitespace-pre-wrap">
                    {ignoreDifferencesText(entry.ignore_differences)}
                  </pre>
                ) : (
                  "—"
                ),
              ],
            ]}
          />
        </>
      )}
      <Tabs defaultValue="deploy">
        <TabsList>
          <TabsTrigger value="deploy">{detail.name}.yaml</TabsTrigger>
          <TabsTrigger value="values">Sig values</TabsTrigger>
        </TabsList>
        <TabsContent value="deploy" className="pt-2">
          <RepoFileView file={detail.deploy_config} absent={`No operators/${detail.name}/${detail.name}.yaml.`} />
        </TabsContent>
        <TabsContent value="values" className="space-y-2 pt-2">
          <ValuesLevels current="Sig values" />
          <RepoFileView file={detail.values_file} absent="No values.yaml: the chart's own values apply." />
        </TabsContent>
      </Tabs>
      {editing && entry && (
        <EditAddonDialog
          entry={entry}
          open
          onOpenChange={setEditing}
          readOnlyReason={writes.readOnlyReason}
          onOpened={writes.onOpened}
        />
      )}
    </Card>
  );
}

function OcpVersions({ detail }: { detail: AddonDetail }) {
  return (
    <Card title="OCP-version pins" icon={GitBranch} label="OCP-version pins">
      {detail.ocp_versions.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          None: every OCP version gets the add-on&apos;s revision. A pin is <code>operators/{detail.name}/ocp-versions/&lt;version&gt;/</code>,
          edited in the repo.
        </p>
      ) : (
        <ul className="space-y-2" aria-label="Pins per OCP version">
          {detail.ocp_versions.map((pin) => (
            <li key={pin.version} className="rounded-lg border px-3 py-2" data-testid={`ocp-pin-${pin.version}`}>
              <details>
                <summary className="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                  <span className="font-semibold">OCP {pin.version}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {pin.target_revision ? `targetRevision ${pin.target_revision}` : "values only"}
                  </span>
                </summary>
                <div className="mt-2 grid gap-3 lg:grid-cols-2">
                  <RepoFileView file={pin.deploy_config} absent="No deploy config: the add-on's revision." />
                  <RepoFileView file={pin.values_file} absent="No values.yaml for this version." />
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-muted-foreground">Read-only in Wingman.</p>
    </Card>
  );
}

function sortedScopes(scopes: ScopePanel[]): ScopePanel[] {
  const order = (s: ScopePanel) => {
    const i = FLEET_SCOPES.indexOf(s.scope);
    return i === -1 ? FLEET_SCOPES.length : i;
  };
  return [...scopes].sort((a, b) => order(a) - order(b));
}

function PageSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" data-testid="addon-loading">
      <Skeleton className="h-48 rounded-xl" />
      <Skeleton className="h-24 rounded-xl" />
      <Skeleton className="h-40 rounded-xl" />
    </div>
  );
}

/**
 * One add-on of a team, reached from the Addons page (ADR-0053): the add-on
 * itself (`operators/<chart>/` in the team repo: its deploy config and Sig
 * values), its OCP-version pins, and
 * one panel per fleet scope: whether it is a default there, which destinations
 * get it, and each destination's overrides. Every write is previewed first and
 * confirmed against the previewed plan. One cluster's add-ons stay on that
 * cluster's page.
 */
export default function AddonPage() {
  const params = useParams<{ team: string; addon: string }>();
  const team = keyFromParam(params.team);
  const name = keyFromParam(params.addon);
  const [opened, setOpened] = useState<OpenedChanges | null>(null);
  const query = useQuery<AddonDetail>({
    queryKey: day2Keys.addonDetail(team, name),
    queryFn: () => api.get<AddonDetail>(day2Api.addonDetail(team, name)),
    staleTime: 30_000,
  });
  const detail = query.data;
  const access = useAddonAccess(team, detail);

  const writes: AddonWrites = {
    isAdmin: access.isAdmin,
    readOnlyReason: access.readOnlyReason,
    onOpened: (change: AuthoringChange) => setOpened({ verb: VERB[change.action] ?? "Update", results: [change], failed: [] }),
    onChanges: setOpened,
  };

  const notFound = query.error && problemOf(query.error).status === 404;

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6 lg:p-8">
      <div className="space-y-2">
        <Breadcrumbs items={[{ label: "Addons", href: "/addons" }, { label: team, href: teamAddonsHref(team) }, { label: name }]} />
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <PageTitle>{name}</PageTitle>
              {detail && !detail.in_catalog && (
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">not in the catalog</span>
              )}
              {access.showReason && <ReadOnlyBadge />}
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              An add-on of <strong>{team}</strong>: its deploy config and Sig values, the fleet defaults built from it, which
              destinations they reach and each one&apos;s overrides. Its install on one cluster is on that cluster&apos;s page.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", query.isFetching && "animate-spin")} />
            Refresh
          </button>
        </div>
        {access.isAdmin && access.showReason && access.readOnlyReason && <ReadOnlyNote reason={access.readOnlyReason} />}
      </div>

      {opened && <ChangeResultPanel changes={opened} onDismiss={() => setOpened(null)} />}

      {notFound ? (
        <EmptyState
          bordered
          title={`${team} has no add-on ${name}`}
          description={`Neither operators/${name}/ nor a fleet default of that name is in sigs/${team}.`}
          action={<EmptyStateLink href={teamAddonsHref(team)}>Back to {team}&apos;s add-ons</EmptyStateLink>}
          data-testid="addon-not-found"
        />
      ) : query.error ? (
        <ProblemList error={query.error} title={`${team}/${name} could not be loaded`} />
      ) : !detail ? (
        <PageSkeleton />
      ) : (
        <>
          <FindingsList findings={detail.warnings} showContext />
          <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <AddonFiles detail={detail} writes={writes} />
            <OcpVersions detail={detail} />
          </div>
          <section className="space-y-3" aria-label="Defaults">
            <div>
              <h2 className="flex items-center gap-2 text-base font-semibold">
                <Layers className="h-4 w-4 text-chart-5" aria-hidden />
                Defaults
              </h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                A fleet default deploys {name} to every destination of one kind that {team}&apos;s repo registers. An MCE or a UPI
                cluster can get values of its own; to have {name} on some MCEs only, deploy it on those MCEs.
              </p>
            </div>
            {sortedScopes(detail.scopes).map((panel) => (
              <ScopePanelCard key={panel.scope} detail={detail} panel={panel} writes={writes} />
            ))}
          </section>
        </>
      )}
    </div>
  );
}
