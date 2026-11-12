"use client";

import { useId, useState } from "react";
import { DEFAULT_SYNC, day2Api, sameSync, syncSummary } from "@/lib/day2";
import { ignoreDifferencesText, parseIgnoreDifferences, sameValues, type Values } from "@/lib/values";
import { AuthoringDialogs } from "@/components/addons/authoring-flow";
import { IgnoreDifferencesField, REPO_URL, TextField, useAddonTemplate } from "@/components/addons/authoring-fields";
import { SyncOptionsControl } from "@/components/addons/sync-options";
import { YamlValuesField } from "@/components/addons/yaml-values-field";
import type {
  AuthoringChange,
  CatalogEntry,
  MakeDefaultBody,
  ScopePanel,
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
 * entry was read at (ADR-0006); the plan says which destinations change, and
 * they are confirmed before the MR opens (ADR-0053).
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
  const initialIgnore = ignoreDifferencesText(entry.ignore_differences);
  const [ignoreText, setIgnoreText] = useState(initialIgnore);
  const ignore = parseIgnoreDifferences(ignoreText);

  function body(): UpdateTeamDefaultBody {
    const out: UpdateTeamDefaultBody = { last_commit_id: entry.last_commit_id };
    if (repourl.trim() !== entry.argocd_metadata.repourl) out.repourl = repourl.trim();
    if (revision.trim() !== revisionText(entry)) out.target_revision = revision.trim() || null;
    if (path.trim() !== pathText(entry)) out.path = path.trim() && path.trim() !== "." ? path.trim() : null;
    if (namespace.trim() !== entry.argocd_metadata.projectNamespace) out.project_namespace = namespace.trim() || null;
    if (!sameSync(sync, entry.sync)) out.sync = sync;
    if (ignore.ok && ignoreText !== initialIgnore && !sameValues(ignore.value, entry.ignore_differences ?? null))
      out.ignore_differences = ignore.value;
    if (values !== null && !sameValues(values, entry.default_values)) out.values = values;
    return out;
  }

  const changed = Object.keys(body()).length > 1;
  const blocker =
    values === null
      ? "Fix the values YAML"
      : !ignore.ok
        ? "Fix the ignoreDifferences YAML"
        : !REPO_URL.test(repourl.trim())
          ? "Give the chart repo URL (http or https)"
          : !changed
            ? "No changes yet"
            : null;

  return (
    <AuthoringDialogs
      open={open}
      onOpenChange={onOpenChange}
      title={`Edit the team default of ${entry.team}/${entry.name}`}
      description={`Changes operators/${entry.name}/ through one merge request: every destination that gets ${entry.name} from ${entry.team} and does not override what changes. The preview lists each one.`}
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
      <IgnoreDifferencesField path={`operators/${entry.name}/${entry.name}.yaml`} text={ignoreText} onTextChange={setIgnoreText} />
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
 * Make an add-on a fleet default on one scope (ADR-0043):
 * `defaults/<scope>/<chart>/` in one MR. Clusters that have the chart in their
 * own folder move into it in the same MR; the dry run lists them, and each one
 * whose app would change is confirmed (`confirm_changes`).
 */
export function MakeDefaultDialog({
  entry,
  panel,
  open,
  onOpenChange,
  readOnlyReason,
  onOpened,
}: {
  entry: CatalogEntry;
  /** The scope it becomes a default on. */
  panel: ScopePanel;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  const template = useAddonTemplate(entry.team, open);
  const [inherit, setInherit] = useState(true);
  const [sync, setSync] = useState<SyncSettings>(entry.sync);
  const [values, setValues] = useState<Values | null>({});
  const reach = panel.destinations.filter((d) => d.renders).length;
  const ownFolders = panel.destinations.filter((d) => d.state === "own-folder");

  const blocker = values === null ? "Fix the values YAML" : null;

  function body(): MakeDefaultBody {
    return { values: values ?? {}, sync: inherit ? null : sync, confirm_changes: [], message: null };
  }

  return (
    <AuthoringDialogs
      open={open}
      onOpenChange={onOpenChange}
      title={`Make ${entry.team}/${entry.name} a default on ${panel.label}`}
      description={`Adds ${panel.folder}/ to sigs/${entry.team}: ArgoCD then deploys ${entry.name} to every ${panel.noun} the team's repo has a folder for (${reach} today).`}
      blocker={blocker}
      readOnlyReason={readOnlyReason}
      body={body}
      method="post"
      url={(dryRun) => day2Api.fleetDefault(entry.team, entry.name, panel.scope, dryRun)}
      onOpened={onOpened}
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sync options</p>
        <SyncInheritance
          inherit={inherit}
          onInheritChange={setInherit}
          inherited={syncSummary(entry.sync)}
          sync={sync}
          onSyncChange={setSync}
          known={template.data?.known_sync_options ?? DEFAULT_SYNC.sync_options}
          name="Fleet default sync options"
        />
      </div>
      <YamlValuesField
        label="Fleet default values"
        path={`${panel.folder}/values.yaml`}
        initial={{}}
        onChange={setValues}
        placeholder="# Empty: the team values apply on every destination."
      />
      <p className="text-xs text-muted-foreground">
        {ownFolders.length > 0
          ? `${ownFolders.map((d) => d.name).join(", ")} ${ownFolders.length === 1 ? "has" : "have"} ${entry.name} in ${ownFolders.length === 1 ? "its" : "their"} own folder today: it moves into the default in the same merge request, keeping its app. The preview shows what changes.`
          : `No ${panel.noun} has ${entry.name} in its own folder today.`}
      </p>
    </AuthoringDialogs>
  );
}

/**
 * A fleet default's own files (ADR-0043): `defaults/<scope>/<chart>/values.yaml`
 * and the sync options of its `<chart>.yaml`, edited in place. The per-env and
 * per-destination `values-<x>.yaml` files are not touched (each destination's
 * override is edited from its row).
 */
export function EditFleetDefaultDialog({
  team,
  chart,
  inCatalog,
  panel,
  open,
  onOpenChange,
  readOnlyReason,
  onOpened,
}: {
  team: string;
  chart: string;
  inCatalog: boolean;
  panel: ScopePanel;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  const template = useAddonTemplate(team, open);
  const initialValues = panel.values_file.values;
  const [inherit, setInherit] = useState(!panel.sync_overridden);
  const [sync, setSync] = useState<SyncSettings>(panel.sync);
  const [values, setValues] = useState<Values | null>(initialValues);
  const reach = panel.destinations.filter((d) => d.state === "default" || d.state === "duplicate").length;

  function body(): UpdateFleetDefaultBody {
    const out: UpdateFleetDefaultBody = { last_commit_id: panel.values_file.last_commit_id ?? panel.last_commit_id };
    if (values !== null && !sameValues(values, initialValues)) out.values = values;
    if (inherit && panel.sync_overridden) out.sync = null;
    if (!inherit && !sameSync(sync, panel.sync)) out.sync = sync;
    return out;
  }

  const changed = Object.keys(body()).length > 1;
  const blocker = values === null ? "Fix the values YAML" : !changed ? "No changes yet" : null;
  const tweaks = panel.destinations.filter((d) => d.override?.exists).length + panel.env_files.length;

  return (
    <AuthoringDialogs
      open={open}
      onOpenChange={onOpenChange}
      title={`Edit the default ${team}/${chart} on ${panel.label}`}
      description={`Changes ${panel.folder}/ through one merge request: ${chart} on the ${reach} destination${reach === 1 ? "" : "s"} it deploys to. The preview lists each one that changes.`}
      blocker={blocker}
      readOnlyReason={readOnlyReason}
      body={body}
      method="put"
      url={(dryRun) => day2Api.fleetDefault(team, chart, panel.scope, dryRun)}
      onOpened={onOpened}
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sync options</p>
        <SyncInheritance
          inherit={inherit}
          onInheritChange={setInherit}
          inherited={inCatalog ? "the team default" : "no team default"}
          sync={sync}
          onSyncChange={setSync}
          known={template.data?.known_sync_options ?? DEFAULT_SYNC.sync_options}
          name="Fleet default sync options"
        />
      </div>
      <YamlValuesField label="Fleet default values" path={panel.values_file.path} initial={initialValues} onChange={setValues} />
      {tweaks > 0 && (
        <p className="text-xs text-muted-foreground">
          Not changed here: {tweaks} per-env or per-destination file{tweaks === 1 ? "" : "s"}. Each destination&apos;s own
          file is edited from its row below.
        </p>
      )}
    </AuthoringDialogs>
  );
}
