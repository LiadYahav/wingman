"use client";

import { useId, useState } from "react";
import { DEFAULT_SYNC, day2Api, sameSync, scopeLabel, syncSummary } from "@/lib/day2";
import { sameValues, type Values } from "@/lib/values";
import { ProblemList } from "@/components/common/problem-list";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthoringDialogs } from "@/components/addons/authoring-flow";
import { ScopeChoice, TextField, useAddonTemplate } from "@/components/addons/new-addon-dialog";
import { SyncOptionsControl } from "@/components/addons/sync-options";
import { YamlValuesField } from "@/components/addons/yaml-values-field";
import type {
  AuthoringChange,
  CatalogEntry,
  FleetDefault,
  FleetScope,
  MakeDefaultBody,
  SyncSettings,
  UpdateFleetDefaultBody,
  UpdateTeamDefaultBody,
} from "@/types/day2";

/** The team default's `targetRevision` as typed: blank for `HEAD`, which writes no key. */
function revisionText(entry: CatalogEntry): string {
  const revision = entry.argocd_metadata.targetRevision;
  return revision === "HEAD" ? "" : revision;
}

function pathText(entry: CatalogEntry): string {
  const path = entry.argocd_metadata.path;
  return path === "." ? "" : path;
}

/**
 * The add-on's team default (ADR-0043): `operators/<chart>/<chart>.yaml`,
 * edited in place, and its `values.yaml`. Only the fields that change are
 * sent; a blank optional field removes its key. Guarded by the commit the
 * entry was read at (ADR-0006).
 */
export function EditTeamDefaultDialog({
  entry,
  open,
  onOpenChange,
  readOnlyReason,
  onOpened,
}: {
  entry: CatalogEntry;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  const template = useAddonTemplate(entry.team, open);
  const listId = useId();
  const [repourl, setRepourl] = useState(entry.argocd_metadata.repourl);
  const [revision, setRevision] = useState(revisionText(entry));
  const [path, setPath] = useState(pathText(entry));
  const [namespace, setNamespace] = useState(entry.argocd_metadata.projectNamespace);
  const [sync, setSync] = useState<SyncSettings>(entry.sync);
  const [values, setValues] = useState<Values | null>(entry.default_values);

  function body(): UpdateTeamDefaultBody {
    const out: UpdateTeamDefaultBody = { last_commit_id: entry.last_commit_id };
    if (repourl.trim() !== entry.argocd_metadata.repourl) out.repourl = repourl.trim();
    if (revision.trim() !== revisionText(entry)) out.target_revision = revision.trim() || null;
    if (path.trim() !== pathText(entry)) out.path = path.trim() && path.trim() !== "." ? path.trim() : null;
    if (namespace.trim() !== entry.argocd_metadata.projectNamespace) out.project_namespace = namespace.trim() || null;
    if (!sameSync(sync, entry.sync)) out.sync = sync;
    if (values !== null && !sameValues(values, entry.default_values)) out.values = values;
    return out;
  }

  const changed = Object.keys(body()).length > 1;
  const blocker =
    values === null
      ? "Fix the values YAML"
      : !/^https?:\/\/\S+$/.test(repourl.trim())
        ? "Give the chart repo URL (http or https)"
        : !changed
          ? "No changes yet"
          : null;

  return (
    <AuthoringDialogs
      open={open}
      onOpenChange={onOpenChange}
      title={`Edit the team default of ${entry.team}/${entry.name}`}
      description={`Changes operators/${entry.name}/ through one merge request: every cluster that gets ${entry.name} from ${entry.team} and does not override what changes.`}
      blocker={blocker}
      readOnlyReason={readOnlyReason}
      body={body}
      method="put"
      url={(dryRun) => day2Api.teamDefault(entry.team, entry.name, dryRun)}
      onOpened={onOpened}
    >
      <p className="text-xs text-muted-foreground">
        <code>operators/{entry.name}/{entry.name}.yaml</code> is edited in place: only the keys that change are rewritten,
        and its comments stay.
      </p>
      <TextField label="Chart repo URL (repourl)" type="url" value={repourl} onChange={setRepourl} />
      <div className="grid gap-3 sm:grid-cols-3">
        <TextField
          label="Revision (targetRevision)"
          value={revision}
          onChange={setRevision}
          placeholder="HEAD"
          list={listId}
          help="Empty: HEAD, the default branch."
        />
        <datalist id={listId}>
          {entry.available_versions.map((v) => (
            <option key={v} value={v} />
          ))}
        </datalist>
        <TextField label="Path" value={path} onChange={setPath} placeholder="." help="Empty: the repo root." />
        <TextField label="Project namespace" value={namespace} onChange={setNamespace} help="Empty: none is set." />
      </div>
      <SyncOptionsControl value={sync} onChange={setSync} known={template.data?.known_sync_options ?? DEFAULT_SYNC.sync_options} />
      <YamlValuesField
        label="Team values"
        path={`operators/${entry.name}/values.yaml`}
        initial={entry.default_values}
        onChange={setValues}
      />
    </AuthoringDialogs>
  );
}

/** Inherit the team default's sync options, or set the fleet layer's own. */
function SyncInheritance({
  inherit,
  onInheritChange,
  inherited,
  sync,
  onSyncChange,
  known,
  name,
}: {
  inherit: boolean;
  onInheritChange: (inherit: boolean) => void;
  /** What inheriting gives, for the label. */
  inherited: string;
  sync: SyncSettings;
  onSyncChange: (sync: SyncSettings) => void;
  known: readonly string[];
  name: string;
}) {
  return (
    <div className="space-y-2">
      <div role="radiogroup" aria-label={name} className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
        <label className="flex items-center gap-2">
          <input type="radio" name={name} checked={inherit} onChange={() => onInheritChange(true)} />
          Inherit the team default&apos;s <span className="text-muted-foreground">({inherited})</span>
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name={name} checked={!inherit} onChange={() => onInheritChange(false)} />
          Set them for this fleet default
        </label>
      </div>
      {!inherit && <SyncOptionsControl value={sync} onChange={onSyncChange} known={known} />}
    </div>
  );
}

/**
 * Make an add-on a fleet default (ADR-0043): `defaults/<scope>/<chart>/` in one
 * MR. Clusters that have the chart in their own folder move into it in the same
 * MR; the dry run lists them, and each one whose app would change must be
 * confirmed (`confirm_changes`).
 */
export function MakeDefaultDialog({
  entry,
  open,
  onOpenChange,
  readOnlyReason,
  onOpened,
}: {
  entry: CatalogEntry;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  const template = useAddonTemplate(entry.team, open);
  const data = template.data;
  const already = Object.fromEntries(entry.fleet_defaults.map((s) => [s, "a fleet default there already"])) as Partial<
    Record<FleetScope, string>
  >;
  const [scope, setScope] = useState<FleetScope | null>(null);
  const [inherit, setInherit] = useState(true);
  const [sync, setSync] = useState<SyncSettings>(entry.sync);
  const [values, setValues] = useState<Values | null>({});

  const blocker = !data
    ? "Loading the team's fleet scopes"
    : !scope
      ? "Choose where it becomes a default"
      : values === null
        ? "Fix the values YAML"
        : null;

  function body(): MakeDefaultBody {
    return { values: values ?? {}, sync: inherit ? null : sync, confirm_changes: [], message: null };
  }

  return (
    <AuthoringDialogs
      open={open}
      onOpenChange={onOpenChange}
      title={`Make ${entry.team}/${entry.name} a fleet default`}
      description={`Adds defaults/<scope>/${entry.name}/ to sigs/${entry.team}: ArgoCD then deploys ${entry.name} to every destination of that kind the team's repo has a folder for.`}
      blocker={blocker}
      readOnlyReason={readOnlyReason}
      body={body}
      method="post"
      url={(dryRun) => (scope ? day2Api.fleetDefault(entry.team, entry.name, scope, dryRun) : "")}
      withConfirmations
      onOpened={onOpened}
    >
      {template.error && !data ? (
        <ProblemList error={template.error} title={`${entry.team}'s fleet scopes could not be loaded`} />
      ) : !data ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <>
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">A default on</p>
            <ScopeChoice scopes={data.scopes} value={scope} onChange={setScope} allowNone={false} unavailable={already} name="Scope" />
          </div>
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sync options</p>
            <SyncInheritance
              inherit={inherit}
              onInheritChange={setInherit}
              inherited={syncSummary(entry.sync)}
              sync={sync}
              onSyncChange={setSync}
              known={data.known_sync_options}
              name="Fleet default sync options"
            />
          </div>
          <YamlValuesField
            label="Fleet default values"
            path={`defaults/${scope ?? "<scope>"}/${entry.name}/values.yaml`}
            initial={{}}
            onChange={setValues}
            placeholder="# Empty: the team values apply on every destination."
          />
          <p className="text-xs text-muted-foreground">
            The preview lists every cluster that has {entry.name} in its own folder today: it moves into the default in the
            same merge request, keeping its app.
          </p>
        </>
      )}
    </AuthoringDialogs>
  );
}

/**
 * A fleet default's own files (ADR-0043): `defaults/<scope>/<chart>/values.yaml`
 * and the sync options of its `<chart>.yaml`, edited in place. The per-env and
 * per-cluster `values-<x>.yaml` files are not touched.
 */
export function EditFleetDefaultDialog({
  fleetDefault,
  open,
  onOpenChange,
  readOnlyReason,
  onOpened,
}: {
  fleetDefault: FleetDefault;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  const fd = fleetDefault;
  const template = useAddonTemplate(fd.team, open);
  const [inherit, setInherit] = useState(!fd.sync_overridden);
  const [sync, setSync] = useState<SyncSettings>(fd.sync);
  const [values, setValues] = useState<Values | null>(fd.values);

  function body(): UpdateFleetDefaultBody {
    const out: UpdateFleetDefaultBody = { last_commit_id: fd.last_commit_id };
    if (values !== null && !sameValues(values, fd.values)) out.values = values;
    if (inherit && fd.sync_overridden) out.sync = null;
    if (!inherit && !sameSync(sync, fd.sync)) out.sync = sync;
    return out;
  }

  const changed = Object.keys(body()).length > 1;
  const blocker = values === null ? "Fix the values YAML" : !changed ? "No changes yet" : null;

  return (
    <AuthoringDialogs
      open={open}
      onOpenChange={onOpenChange}
      title={`Edit the fleet default ${fd.team}/${fd.chart} on ${fd.scope_label || scopeLabel(fd.scope)}`}
      description={`Changes ${fd.path}/ through one merge request: ${fd.chart} on the ${fd.reach.length} destination${fd.reach.length === 1 ? "" : "s"} it reaches.`}
      blocker={blocker}
      readOnlyReason={readOnlyReason}
      body={body}
      method="put"
      url={(dryRun) => day2Api.fleetDefault(fd.team, fd.chart, fd.scope, dryRun)}
      onOpened={onOpened}
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sync options</p>
        <SyncInheritance
          inherit={inherit}
          onInheritChange={setInherit}
          inherited={fd.in_catalog ? "the team default" : "no team default"}
          sync={sync}
          onSyncChange={setSync}
          known={template.data?.known_sync_options ?? DEFAULT_SYNC.sync_options}
          name="Fleet default sync options"
        />
      </div>
      <YamlValuesField label="Fleet default values" path={`${fd.path}/values.yaml`} initial={fd.values} onChange={setValues} />
      {fd.tweaks.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Not changed here: {fd.tweaks.length} per-env or per-cluster file{fd.tweaks.length === 1 ? "" : "s"} (
          <span className="break-all font-mono text-[11px]">{fd.tweaks.join(", ")}</span>), edited from each cluster&apos;s
          add-on page.
        </p>
      )}
    </AuthoringDialogs>
  );
}
