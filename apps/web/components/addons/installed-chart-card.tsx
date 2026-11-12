"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { ChevronDown, ExternalLink, Layers, MoreVertical, Package, Pin, Trash2, Unplug } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api-client";
import { day2Api, isRevisionConflict, addonHref, problemOf } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { sameValues, toYaml, type Values } from "@/lib/values";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ProblemList } from "@/components/common/problem-list";
import { ReviewDialog } from "@/components/common/review-dialog";
import { FindingsBadge, FindingsList } from "@/components/addons/findings";
import { ValuesEditor } from "@/components/addons/values-editor";
import { DeploySummary, ValueLayers } from "@/components/addons/value-layers";
import { FilePreview, MessageField, WriteError, type PlannedFile } from "@/components/addons/file-preview";
import { VersionField, inheritedRevision } from "@/components/addons/version-field";
import { useValuesPreview } from "@/components/addons/use-values-preview";
import type { OpenedChanges } from "@/components/addons/change-result";
import type { CatalogEntry, ChangeResult, InstalledChart, UpdateBody } from "@/types/day2";

export interface DestinationRef {
  id: string;
  name: string;
  kind: string;
}

/** The Layers tab while the preview loads: rows shaped like `ValueLayers`'. */
function LayersSkeleton() {
  return (
    <div className="divide-y overflow-hidden rounded-lg border" aria-busy="true" data-testid="layers-loading">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="grid grid-cols-[1.5rem_8.5rem_minmax(0,1fr)_auto] items-center gap-2 px-3 py-2">
          <Skeleton className="h-3 w-3" />
          <Skeleton className="h-4 w-16 rounded-full" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-12" />
        </div>
      ))}
    </div>
  );
}

/** The edit's starting point: the file's content and the commit it was read at (ADR-0006). */
interface EditSession {
  commitId: string | null;
  baseline: Values;
}

/**
 * One chart the platform deploys to the destination: what it is, where its
 * values come from, and (for admins) an editor for the one file Wingman
 * writes for it, `override_path`.
 */
export function InstalledChartCard({
  chart,
  destination,
  catalog,
  isAdmin,
  lastOfTeam,
  onOpened,
  reloadChart,
}: {
  chart: InstalledChart;
  destination: DestinationRef;
  catalog: CatalogEntry | undefined;
  isAdmin: boolean;
  /** Removing it would leave the team no chart folder on the destination. */
  lastOfTeam: boolean;
  onOpened: (changes: OpenedChanges) => void;
  /** Read the chart again after a conflict; resolves to the latest listing entry. */
  reloadChart: () => Promise<InstalledChart | undefined>;
}) {
  const fleetDefault = chart.source === "fleet-default";
  const [expanded, setExpanded] = useState(false);
  const [session, setSession] = useState<EditSession>({
    commitId: chart.last_commit_id,
    baseline: chart.override_values,
  });
  const [draft, setDraft] = useState<Values>(chart.override_values);
  const [version, setVersion] = useState<string | null>(null);
  const [emergencyPin, setEmergencyPin] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [writeError, setWriteError] = useState<unknown>(null);

  const valuesEdited = !sameValues(draft, session.baseline);
  // Follow the listing while nothing is edited; an edit keeps the commit it started from.
  if (chart.last_commit_id !== session.commitId && !valuesEdited && version === null) {
    setSession({ commitId: chart.last_commit_id, baseline: chart.override_values });
    setDraft(chart.override_values);
  }

  function restart(latest: InstalledChart | undefined) {
    const next = latest ?? chart;
    setSession({ commitId: next.last_commit_id, baseline: next.override_values });
    setDraft(next.override_values);
    setVersion(null);
    setEmergencyPin(false);
  }

  const preview = useValuesPreview({
    clusterId: destination.id,
    team: chart.team,
    chart: chart.name,
    version: version !== null && version !== chart.version ? version : undefined,
    draft,
    baseline: session.baseline,
    enabled: expanded,
  });
  const data = preview.data;
  const ownDeployLayer = data?.deploy.layers.find((l) => l.role === "cluster");
  const inherited = data ? inheritedRevision(data.deploy.layers) : chart.version;
  const chosenVersion = version ?? chart.version;
  const versionChanged = version !== null && version !== chart.version;
  const pinBlocked = versionChanged && version !== inherited && !emergencyPin;
  const canSubmit = (valuesEdited || versionChanged) && !pinBlocked;
  const overrideExists = data?.layers.find((l) => l.path === chart.override_path)?.exists ?? true;

  const planned: PlannedFile[] = [];
  if (valuesEdited) {
    const after = toYaml(draft);
    planned.push(
      !overrideExists
        ? { action: "create", path: chart.override_path, after }
        : fleetDefault && after === ""
          ? { action: "delete", path: chart.override_path }
          : { action: "update", path: chart.override_path, before: toYaml(session.baseline), after },
    );
  }
  if (versionChanged && ownDeployLayer) {
    const doc: Values = { ...ownDeployLayer.values };
    if (version === inherited) delete doc.targetRevision;
    else doc.targetRevision = version;
    planned.push(
      !ownDeployLayer.exists
        ? { action: "create", path: ownDeployLayer.path, after: toYaml(doc) }
        : Object.keys(doc).length === 0
          ? { action: "delete", path: ownDeployLayer.path }
          : { action: "update", path: ownDeployLayer.path, before: toYaml(ownDeployLayer.values), after: toYaml(doc) },
    );
  }

  /**
   * A refused write. If the file moved on since the edit started (a 409, or
   * a newer commit in the listing), reload it: the guard did its job
   * (ADR-0006) and the edit has to be redone on the new content.
   */
  async function onWriteError(error: unknown) {
    const problem = problemOf(error);
    const latest = await reloadChart();
    const moved = latest !== undefined && latest.last_commit_id !== session.commitId;
    if (isRevisionConflict(problem) || moved) {
      toast.error(`${chart.override_path} changed since you opened it. Reloaded the latest version: redo your edit on it.`, {
        duration: 10_000,
      });
      restart(latest);
      setReviewOpen(false);
      setRemoveOpen(false);
      return;
    }
    setWriteError(error);
  }

  const update = useMutation({
    mutationFn: () => {
      const body: UpdateBody = {
        override_values: draft,
        last_commit_id: session.commitId,
        ...(versionChanged ? { version: chosenVersion, emergency_pin: version !== inherited } : {}),
        ...(message.trim() ? { message: message.trim() } : {}),
      };
      return api.put<ChangeResult>(day2Api.chart(destination.id, chart.team, chart.name), body);
    },
    onMutate: () => setWriteError(null),
    onSuccess: (mr) => {
      onOpened({ verb: "Update", results: [mr], failed: [] });
      setReviewOpen(false);
      setMessage("");
      restart(chart);
    },
    onError: onWriteError,
  });

  const remove = useMutation({
    mutationFn: () =>
      api.del<ChangeResult>(day2Api.remove(destination.id, chart.team, chart.name, session.commitId)),
    onMutate: () => setWriteError(null),
    onSuccess: (mr) => {
      onOpened({ verb: "Remove", results: [mr], failed: [] });
      setRemoveOpen(false);
    },
    onError: onWriteError,
  });

  const hasYamlError = chart.parse_errors.length > 0;

  return (
    <>
      <div className="overflow-hidden rounded-xl border bg-card shadow-sm" data-testid={`installed-${chart.team}-${chart.name}`}>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
          <button
            type="button"
            className="flex min-w-0 flex-1 basis-48 items-center gap-3 text-left"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            <span
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                fleetDefault ? "bg-chart-5/15 text-chart-5" : "bg-status-ready/15 text-status-ready",
              )}
            >
              {fleetDefault ? <Layers className="h-4 w-4" /> : <Package className="h-4 w-4" />}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold" title={chart.name}>
                {chart.name}
              </span>
              <span className="block truncate text-xs text-muted-foreground">
                {chart.team}
                {fleetDefault ? " · fleet default" : ""}
              </span>
            </span>
          </button>
          <div className="ml-auto flex shrink-0 flex-wrap items-center justify-end gap-1.5">
            <span className="max-w-40 truncate rounded-full bg-primary/8 px-2 py-0.5 font-mono text-xs font-medium text-primary" title={`targetRevision ${chart.version}`}>
              {chart.version}
            </span>
            {chart.pinned && (
              <span
                className="inline-flex items-center gap-1 rounded-full bg-status-warning/12 px-2 py-0.5 text-xs font-medium text-status-warning-fg"
                title="Emergency pin: this cluster's folder sets its own targetRevision"
              >
                <Pin className="h-3 w-3" />
                pinned
              </span>
            )}
            {!chart.deploy.auto_sync && (
              <span
                className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                title="Manual sync: nothing deploys after a merge until someone syncs the app"
              >
                manual sync
              </span>
            )}
            {hasYamlError && (
              <span className="rounded-full bg-status-error/12 px-2 py-0.5 text-xs font-medium text-status-error-fg">YAML error</span>
            )}
            <FindingsBadge findings={chart.warnings} />
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
              aria-label={expanded ? "Collapse" : "Expand"}
            >
              <ChevronDown className={cn("h-4 w-4 transition-transform duration-150", expanded && "rotate-180")} />
            </button>
            <Popover>
              <PopoverTrigger className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted" aria-label={`Actions for ${chart.name}`}>
                <MoreVertical className="h-4 w-4" />
              </PopoverTrigger>
              <PopoverContent align="end" className="w-60 p-1">
                {chart.gitlab_url && (
                  <a
                    href={chart.gitlab_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"
                  >
                    <ExternalLink className="h-4 w-4" />
                    Open folder in GitLab
                  </a>
                )}
                {isAdmin &&
                  (fleetDefault ? (
                    <p className="flex gap-2 px-3 py-2 text-xs text-muted-foreground">
                      <Unplug className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      <span>
                        A fleet default is not removed per cluster: it is on every destination of its kind. Its values
                        here are edited above; the default itself is on{" "}
                        <Link href={addonHref(chart.team, chart.name)} className="font-medium text-primary hover:underline">
                          its add-on page
                        </Link>
                        .
                      </span>
                    </p>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setRemoveOpen(true)}
                      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-destructive hover:bg-destructive/10"
                    >
                      <Trash2 className="h-4 w-4" />
                      Remove from {destination.kind === "hub" ? "the hub" : "this cluster"}
                    </button>
                  ))}
              </PopoverContent>
            </Popover>
          </div>
        </div>

        {expanded && (
          <div className="space-y-4 border-t bg-muted/10 p-4">
            <FindingsList findings={chart.warnings} showContext />
            {hasYamlError && isAdmin && (
              <p className="text-xs text-muted-foreground">
                {chart.override_path} does not parse; saving replaces it with what you write here.
              </p>
            )}
            {preview.error && !data ? (
              <ProblemList error={preview.error} title="The values could not be loaded" />
            ) : (
              <Tabs defaultValue="values">
                <TabsList>
                  <TabsTrigger value="values">Values</TabsTrigger>
                  <TabsTrigger value="layers">Layers</TabsTrigger>
                  <TabsTrigger value="deploy">Deployment</TabsTrigger>
                </TabsList>
                <TabsContent value="values" className="space-y-3 pt-2">
                  {isAdmin && !fleetDefault && catalog && catalog.available_versions.length > 0 && data && (
                    <VersionField
                      versions={catalog.available_versions}
                      inherited={inherited}
                      pinned={chart.pinned}
                      value={chosenVersion}
                      onChange={(v) => {
                        setVersion(v === chart.version ? null : v);
                        setEmergencyPin(false);
                      }}
                      emergencyPin={emergencyPin}
                      onEmergencyPinChange={setEmergencyPin}
                      clusterName={destination.name}
                    />
                  )}
                  <ValuesEditor
                    preview={data}
                    loading={preview.isLoading}
                    stale={preview.stale}
                    file={{ role: fleetDefault ? "fleet-target" : "cluster", path: chart.override_path }}
                    draft={draft}
                    baseline={session.baseline}
                    onDraftChange={isAdmin ? setDraft : undefined}
                  />
                  {isAdmin && (
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setReviewOpen(true)}
                        disabled={!canSubmit || preview.stale}
                        title={!canSubmit ? (pinBlocked ? "Confirm the emergency pin first" : "No changes yet") : undefined}
                        className="inline-flex h-7 items-center rounded-lg bg-primary px-3 text-xs font-semibold text-primary-foreground transition-[background-color,transform] duration-150 hover:bg-primary/90 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Review update
                      </button>
                      {(valuesEdited || versionChanged) && (
                        <button
                          type="button"
                          onClick={() => restart(chart)}
                          className="h-7 rounded-lg px-2 text-xs text-muted-foreground transition-colors hover:text-foreground"
                        >
                          Discard changes
                        </button>
                      )}
                    </div>
                  )}
                </TabsContent>
                <TabsContent value="layers" className="pt-2">
                  {data ? <ValueLayers preview={data} editedPath={chart.override_path} /> : <LayersSkeleton />}
                </TabsContent>
                <TabsContent value="deploy" className="pt-2">
                  <DeploySummary deploy={chart.deploy} />
                </TabsContent>
              </Tabs>
            )}
          </div>
        )}
      </div>

      <ReviewDialog
        open={reviewOpen}
        onOpenChange={(open) => {
          setReviewOpen(open);
          setWriteError(null);
        }}
        title={`Update ${chart.name} on ${destination.name}`}
        description={`Opens a merge request on ${chart.team}'s repo. Nothing changes on the cluster until it is merged${chart.deploy.auto_sync ? "" : " and someone syncs the app"}.`}
        onConfirm={() => update.mutate()}
        isPending={update.isPending}
        size="lg"
      >
        <div className="space-y-3">
          {planned.map((file) => (
            <FilePreview key={file.path} file={file} />
          ))}
          <MessageField value={message} onChange={setMessage} />
          <WriteError error={writeError} />
        </div>
      </ReviewDialog>

      <RemoveDialog
        open={removeOpen}
        onOpenChange={(open) => {
          setRemoveOpen(open);
          setWriteError(null);
        }}
        error={writeError}
        chart={chart}
        destination={destination}
        lastOfTeam={lastOfTeam}
        isPending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}

function RemoveDialog({
  open,
  onOpenChange,
  chart,
  destination,
  lastOfTeam,
  isPending,
  onConfirm,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The refused removal, or null. */
  error: unknown;
  chart: InstalledChart;
  destination: DestinationRef;
  lastOfTeam: boolean;
  isPending: boolean;
  onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const app = chart.deploy.app_name;
  return (
    <ReviewDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setTyped("");
      }}
      title={`Remove ${chart.name} from ${destination.name}`}
      description={`Opens a merge request on ${chart.team}'s repo deleting the chart's folder.`}
      onConfirm={onConfirm}
      isPending={isPending}
      confirmDisabled={typed !== chart.name}
      confirmLabel="Open removal MR"
      confirmVariant="destructive"
    >
      <div className="space-y-4">
        <div className="rounded-lg border border-status-warning/40 bg-status-warning/8 p-3 text-sm" role="note">
          <p className="font-semibold text-status-warning-fg">The workload keeps running.</p>
          <p className="mt-1 text-xs text-foreground/90">
            Deleting the folder deletes the ArgoCD Application <code className="break-all">{app}</code>, but ArgoCD orphans
            what it deployed: {chart.name} stays on {destination.name}. To tear it down, run{" "}
            <code className="break-all rounded bg-muted px-1">argocd app delete {app} --cascade</code> on {chart.deploy.argo}
            &apos;s ArgoCD after the merge (runbook R8). Wingman has no ArgoCD access.
          </p>
        </div>
        <div className="space-y-1 text-xs">
          <p className="text-muted-foreground">Deletes every file under</p>
          <code className="block break-all rounded bg-muted/60 px-2 py-1 font-mono text-[11px]">{chart.path}/</code>
          {lastOfTeam && destination.kind !== "hub" && (
            <p className="text-muted-foreground">
              It is {chart.team}&apos;s last chart folder here, so the MR adds a <code>.gitkeep</code> to keep{" "}
              {destination.name} registered and {chart.team}&apos;s fleet defaults on it managed.
            </p>
          )}
        </div>
        <label className="block space-y-1.5 text-sm">
          <span>
            Type <code className="rounded bg-muted px-1.5 py-0.5 text-destructive">{chart.name}</code> to confirm
          </span>
          <input
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={chart.name}
            autoComplete="off"
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-destructive/50"
          />
        </label>
        <WriteError error={error} />
      </div>
    </ReviewDialog>
  );
}
