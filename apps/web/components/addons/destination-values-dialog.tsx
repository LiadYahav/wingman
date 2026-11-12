"use client";

import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowRight, Share2 } from "lucide-react";
import { api } from "@/lib/api-client";
import { day2Api, day2Keys } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { getAt, hasAt, inlineYaml, leaves, pathLabel, sameValues, sourceAt, stableStringify, type ValuePath, type Values } from "@/lib/values";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ProblemList } from "@/components/common/problem-list";
import { AuthoringDialogs } from "@/components/addons/authoring-flow";
import { RoleChip } from "@/components/addons/role-chip";
import { useDebounced } from "@/components/addons/use-values-preview";
import { ValueLayers } from "@/components/addons/value-layers";
import { ValuesEditor } from "@/components/addons/values-editor";
import type { AuthoringChange, DestinationValuesBody, MergePreviewBody, RepoFile, ScopeDestination, ScopePanel, ValuesPreview } from "@/types/day2";

/**
 * The service's merge of the add-on on one destination (`POST /merge-preview`):
 * with `override` as one of its value files (`path`: a `values-<env>.yaml`;
 * absent: its `values-<name>.yaml`), or as it is today when `override` is
 * `undefined`. The merge is the service's (Helm's), never redone here.
 */
function useMergePreview(team: string, chart: string, cluster: string, override: Values | undefined, enabled: boolean, path?: string) {
  return useQuery<ValuesPreview>({
    queryKey: day2Keys.mergePreview(cluster, team, chart, override === undefined ? null : stableStringify(override), path ?? ""),
    queryFn: () => {
      const body: MergePreviewBody =
        override === undefined
          ? { team, addon: chart, cluster }
          : { team, addon: chart, cluster, override_values: override, ...(path ? { override_path: path } : {}) };
      return api.post<ValuesPreview>(day2Api.mergePreview, body);
    },
    enabled: enabled && Boolean(cluster),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

interface EffectiveChange {
  path: ValuePath;
  before: unknown;
  beforeSet: boolean;
  beforeRole?: string;
  after: unknown;
  afterSet: boolean;
  afterRole?: string;
}

/** Every merged key whose value differs between the two previews, with who set it on each side. */
function effectiveChanges(before: ValuesPreview, after: ValuesPreview): EffectiveChange[] {
  const paths = new Map<string, ValuePath>();
  for (const l of [...leaves(before.merged), ...leaves(after.merged)]) paths.set(JSON.stringify(l.path), l.path);
  const out: EffectiveChange[] = [];
  for (const path of paths.values()) {
    const b = getAt(before.merged, path);
    const a = getAt(after.merged, path);
    const bSet = hasAt(before.merged, path);
    const aSet = hasAt(after.merged, path);
    if (bSet === aSet && sameValues(b, a)) continue;
    out.push({
      path,
      before: b,
      beforeSet: bSet,
      beforeRole: sourceAt(before.provenance, path),
      after: a,
      afterSet: aSet,
      afterRole: sourceAt(after.provenance, path),
    });
  }
  return out;
}

function Cell({ set, value, role }: { set: boolean; value: unknown; role?: string }) {
  if (!set) return <span className="text-muted-foreground">— (not set)</span>;
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-1.5">
      <span className="break-all font-mono">{inlineYaml(value)}</span>
      <RoleChip role={role} />
    </span>
  );
}

/** The effective values before and after the edit, key by key, with the layer that sets each. */
function BeforeAfter({ before, after, stale }: { before: ValuesPreview; after: ValuesPreview; stale: boolean }) {
  const changes = effectiveChanges(before, after);
  return (
    <div className={cn("space-y-1.5 transition-opacity", stale && "opacity-70")} data-testid="before-after" aria-busy={stale || undefined}>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Effective values: before → after{" "}
        <span className="font-normal normal-case tracking-normal">
          ({changes.length === 0 ? "no change" : `${changes.length} key${changes.length === 1 ? "" : "s"}`})
        </span>
      </p>
      {changes.length === 0 ? (
        <p className="rounded-lg border border-dashed px-3 py-3 text-center text-xs text-muted-foreground">
          The merged values are the same as today.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border text-xs">
          <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_1rem_minmax(0,3fr)] border-b bg-muted/40 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            <div className="px-3 py-1.5">Key</div>
            <div className="px-3 py-1.5">Before</div>
            <div />
            <div className="px-3 py-1.5">After</div>
          </div>
          {changes.map((c) => (
            <div
              key={JSON.stringify(c.path)}
              className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_1rem_minmax(0,3fr)] items-start border-b last:border-b-0"
              data-testid={`effective-${pathLabel(c.path)}`}
            >
              <div className="break-all px-3 py-1.5 font-mono text-muted-foreground">{pathLabel(c.path)}</div>
              <div className="px-3 py-1.5">
                <Cell set={c.beforeSet} value={c.before} role={c.beforeRole} />
              </div>
              <ArrowRight className="mt-2 h-3 w-3 text-muted-foreground" aria-hidden />
              <div className="px-3 py-1.5">
                {!c.afterSet && c.beforeSet ? (
                  <span className="text-status-warning-fg">removed: a null deletes it, chart default included</span>
                ) : (
                  <Cell set={c.afterSet} value={c.after} role={c.afterRole} />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * One destination's value override of a fleet default (ADR-0053):
 * `defaults/<scope>/<op>/values-<name>.yaml`, added, edited or deleted
 * (`values: null`, back to the default's values). The effective values
 * before and after come from the service's merge preview, with provenance.
 */
export function DestinationValuesDialog({
  team,
  chart,
  panel,
  destination,
  open,
  onOpenChange,
  readOnlyReason,
  onOpened,
}: {
  team: string;
  chart: string;
  panel: ScopePanel;
  destination: ScopeDestination;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  const d = destination;
  const file = d.override;
  const path = file?.path ?? `${panel.folder}/values-${d.name}.yaml`;
  const baseline = file?.exists ? file.values : {};
  const [draft, setDraft] = useState<Values>(baseline);
  const [removing, setRemoving] = useState(false);
  const debounced = useDebounced(removing ? {} : draft, 300);

  const before = useMergePreview(team, chart, d.id, undefined, open);
  const after = useMergePreview(team, chart, d.id, debounced, open);
  const stale = after.isPlaceholderData || !sameValues(removing ? {} : draft, debounced);

  const edited = removing || !sameValues(draft, baseline);
  const blocker = !edited ? "No changes yet" : !removing && !file?.exists && leaves(draft).length === 0 ? "Set at least one value" : null;

  function body(): DestinationValuesBody {
    return {
      values: removing || leaves(draft).length === 0 ? null : draft,
      last_commit_id: file?.last_commit_id ?? null,
      confirm_changes: [],
      expected_digest: null,
      message: null,
    };
  }

  return (
    <AuthoringDialogs
      open={open}
      onOpenChange={onOpenChange}
      title={`${chart} values on ${d.name}`}
      description={`${file?.exists ? "Edits" : "Adds"} ${path}: the fleet default's values for ${d.name} alone, above the default's values.yaml and values-<env>.yaml. One merge request; the preview lists every destination it changes.`}
      blocker={blocker}
      readOnlyReason={readOnlyReason}
      body={body}
      method="put"
      url={(dryRun) => day2Api.destinationValues(team, chart, panel.scope, d.id, dryRun)}
      wide
      onOpened={onOpened}
    >
      {d.override_shared_with.length > 0 && (
        <p className="flex items-start gap-1.5 rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 text-xs" data-testid="override-shared">
          <Share2 className="mt-0.5 h-3 w-3 shrink-0 text-primary" aria-hidden />
          <span>
            The same file applies to {d.override_shared_with.join(", ")}: {d.override_shared_with.length === 1 ? "it has" : "they have"} the
            name {d.name} too.
          </span>
        </p>
      )}
      {file?.exists && (
        <div role="radiogroup" aria-label="Override" className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
          <label className="flex items-center gap-2">
            <input type="radio" name="override-mode" checked={!removing} onChange={() => setRemoving(false)} />
            Edit <code>values-{d.name}.yaml</code>
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name="override-mode" checked={removing} onChange={() => setRemoving(true)} />
            Delete it: back to the fleet default&apos;s values
          </label>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="min-w-0">
          {removing ? (
            <p className="rounded-lg border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">
              <code className="break-all">{path}</code> is deleted: {d.name} gets the fleet default&apos;s values again.
            </p>
          ) : (
            <ValuesEditor
              preview={after.data}
              loading={after.isLoading}
              stale={stale}
              file={{ role: "fleet-target", path }}
              draft={draft}
              baseline={baseline}
              onDraftChange={setDraft}
            />
          )}
          {after.error && <ProblemList error={after.error} title="The values after the edit could not be previewed" />}
        </div>
        <div className="min-w-0 space-y-3">
          {before.error ? (
            <ProblemList error={before.error} title={`The values on ${d.name} today could not be read`} />
          ) : before.data && after.data ? (
            <BeforeAfter before={before.data} after={after.data} stale={stale} />
          ) : (
            <div className="space-y-1.5" aria-busy="true">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-16 w-full" />
            </div>
          )}
          {before.data && after.data && (
            <Tabs defaultValue="after">
              <TabsList>
                <TabsTrigger value="after">Layers after</TabsTrigger>
                <TabsTrigger value="before">Layers today</TabsTrigger>
              </TabsList>
              <TabsContent value="after" className="pt-2">
                <ValueLayers preview={after.data} editedPath={path} />
              </TabsContent>
              <TabsContent value="before" className="pt-2">
                <ValueLayers preview={before.data} editedPath="" />
              </TabsContent>
            </Tabs>
          )}
        </div>
      </div>
    </AuthoringDialogs>
  );
}

/**
 * One env's values of a fleet default (ADR-0053): `values-<env>.yaml` in the
 * default's folder, read by every destination of the scope in that env,
 * above the default's `values.yaml` and below each destination's own
 * `values-<name>.yaml`. The effective values before and after are shown on
 * one destination of that env (a choice when there are several).
 */
export function EnvValuesDialog({
  team,
  chart,
  panel,
  env,
  file,
  destinations,
  open,
  onOpenChange,
  readOnlyReason,
  onOpened,
}: {
  team: string;
  chart: string;
  panel: ScopePanel;
  env: string;
  /** The env file as read, or `null` when absent. */
  file: RepoFile | null;
  /** The scope's destinations in `env` the default deploys to: where the preview is shown. */
  destinations: ScopeDestination[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  const path = file?.path ?? `${panel.folder}/values-${env}.yaml`;
  const exists = Boolean(file?.exists);
  const baseline = exists && file ? file.values : {};
  const [draft, setDraft] = useState<Values>(baseline);
  const [removing, setRemoving] = useState(false);
  const [shownOn, setShownOn] = useState(destinations[0]?.id ?? "");
  const debounced = useDebounced(removing ? {} : draft, 300);
  const where = destinations.find((d) => d.id === shownOn);

  const before = useMergePreview(team, chart, shownOn, undefined, open);
  const after = useMergePreview(team, chart, shownOn, debounced, open, path);
  const stale = after.isPlaceholderData || !sameValues(removing ? {} : draft, debounced);

  const edited = removing || !sameValues(draft, baseline);
  const blocker = !edited ? "No changes yet" : !removing && !exists && leaves(draft).length === 0 ? "Set at least one value" : null;

  function body(): DestinationValuesBody {
    return {
      values: removing || leaves(draft).length === 0 ? null : draft,
      last_commit_id: file?.last_commit_id ?? null,
      confirm_changes: [],
      expected_digest: null,
      message: null,
    };
  }

  return (
    <AuthoringDialogs
      open={open}
      onOpenChange={onOpenChange}
      title={`${chart} values for ${env}`}
      description={`${exists ? "Edits" : "Adds"} ${path}: the fleet default's values for every ${panel.noun} in ${env} (${destinations.length} today), above the default's values.yaml and below each one's own values-<name>.yaml. One merge request; the preview lists every destination it changes.`}
      blocker={blocker}
      readOnlyReason={readOnlyReason}
      body={body}
      method="put"
      url={(dryRun) => day2Api.envValues(team, chart, panel.scope, env, dryRun)}
      wide
      onOpened={onOpened}
    >
      {exists && (
        <div role="radiogroup" aria-label="Env values" className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
          <label className="flex items-center gap-2">
            <input type="radio" name="env-mode" checked={!removing} onChange={() => setRemoving(false)} />
            Edit <code>values-{env}.yaml</code>
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name="env-mode" checked={removing} onChange={() => setRemoving(true)} />
            Delete it: back to the fleet default&apos;s values
          </label>
        </div>
      )}
      {destinations.length > 1 && (
        <label className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted-foreground">Effective values shown on</span>
          <select
            value={shownOn}
            onChange={(e) => setShownOn(e.target.value)}
            className="rounded-md border bg-background px-2 py-1 text-xs"
            aria-label="Effective values shown on"
          >
            {destinations.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="min-w-0">
          {removing ? (
            <p className="rounded-lg border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">
              <code className="break-all">{path}</code> is deleted: the {env} {panel.noun} get the fleet default&apos;s values again.
            </p>
          ) : (
            <ValuesEditor
              preview={after.data}
              loading={after.isLoading}
              stale={stale}
              file={{ role: "fleet-env", path }}
              draft={draft}
              baseline={baseline}
              onDraftChange={setDraft}
            />
          )}
          {after.error && <ProblemList error={after.error} title="The values after the edit could not be previewed" />}
        </div>
        <div className="min-w-0 space-y-3">
          {!where ? (
            <p className="rounded-lg border border-dashed px-3 py-3 text-xs text-muted-foreground">
              No {panel.noun} of the default is in {env} yet: the file applies once one is.
            </p>
          ) : before.error ? (
            <ProblemList error={before.error} title={`The values on ${where.name} today could not be read`} />
          ) : before.data && after.data ? (
            <BeforeAfter before={before.data} after={after.data} stale={stale} />
          ) : (
            <div className="space-y-1.5" aria-busy="true">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-16 w-full" />
            </div>
          )}
          {where && before.data && after.data && (
            <Tabs defaultValue="after">
              <TabsList>
                <TabsTrigger value="after">Layers after</TabsTrigger>
                <TabsTrigger value="before">Layers today</TabsTrigger>
              </TabsList>
              <TabsContent value="after" className="pt-2">
                <ValueLayers preview={after.data} editedPath={path} />
              </TabsContent>
              <TabsContent value="before" className="pt-2">
                <ValueLayers preview={before.data} editedPath="" />
              </TabsContent>
            </Tabs>
          )}
        </div>
      </div>
    </AuthoringDialogs>
  );
}

