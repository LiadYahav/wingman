"use client";

import { useState } from "react";
import { day2Api } from "@/lib/day2";
import { AuthoringDialogs } from "@/components/addons/authoring-flow";
import { REPO_URL, TextField } from "@/components/addons/authoring-fields";
import { VersionField } from "@/components/addons/version-field";
import { RepoFileView } from "@/components/operators/repo-file";
import type { AuthoringChange, CatalogEntry, DeployOverride, DestinationDeployBody, ScopeDestination, ScopePanel } from "@/types/day2";

function text(values: Record<string, unknown>, key: string): string {
  const value = values[key];
  return typeof value === "string" ? value : "";
}

/**
 * One destination's own deploy config, the platform's carve-out (ADR-0053):
 * the destination is excluded from the default and deployed from its own
 * `<op>/<op>.yaml`, in one commit. The Application keeps its name (both
 * folders generate the same one), so ArgoCD keeps it. Its values still come
 * from the default's layers. Removing it (`deploy: null`) puts it back under
 * the default.
 */
export function DestinationDeployDialog({
  team,
  chart,
  catalog,
  panel,
  destination,
  open,
  onOpenChange,
  readOnlyReason,
  onOpened,
}: {
  team: string;
  chart: string;
  /** The team default, for its revision and the chart repo's branches; `null` when not in the catalog. */
  catalog: CatalogEntry | null;
  panel: ScopePanel;
  destination: ScopeDestination;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  const d = destination;
  const own = d.own_deploy?.exists ? d.own_deploy : null;
  const current = own?.values ?? {};
  const inherited = catalog?.current_version ?? "HEAD";
  const [removing, setRemoving] = useState(false);
  const [revision, setRevision] = useState(text(current, "targetRevision") || inherited);
  const [emergencyPin, setEmergencyPin] = useState(Boolean(text(current, "targetRevision")));
  const [repourl, setRepourl] = useState(text(current, "repourl"));
  const [path, setPath] = useState(text(current, "path"));
  const [namespace, setNamespace] = useState(text(current, "projectNamespace"));

  const pins = revision !== inherited;
  const deploy: DeployOverride = {
    target_revision: pins ? revision : null,
    repourl: repourl.trim() || null,
    path: path.trim() && path.trim() !== "." ? path.trim() : null,
    project_namespace: namespace.trim() || null,
  };
  const unchanged =
    own !== null &&
    (deploy.target_revision ?? "") === text(current, "targetRevision") &&
    (deploy.repourl ?? "") === text(current, "repourl") &&
    (deploy.path ?? "") === text(current, "path") &&
    (deploy.project_namespace ?? "") === text(current, "projectNamespace");
  const nothingSet = Object.values(deploy).every((v) => v === null);

  const blocker = removing
    ? null
    : nothingSet
      ? "Set at least one key: an own deploy config that sets none changes nothing"
      : pins && !emergencyPin
        ? `Confirm the emergency pin of ${d.name} to ${revision}`
        : deploy.repourl && !REPO_URL.test(deploy.repourl)
          ? "The chart repo URL must be http or https"
          : unchanged
            ? "No changes yet"
            : null;

  function body(): DestinationDeployBody {
    return {
      deploy: removing ? null : deploy,
      last_commit_id: own?.last_commit_id ?? panel.last_commit_id,
      confirm_changes: [],
      expected_digest: null,
      message: null,
    };
  }

  const ownPath = own?.path ?? (d.own_folder ? `${d.own_folder}/${chart}.yaml` : `${d.name}'s own ${chart}/ folder`);
  const meta = catalog?.argocd_metadata;

  return (
    <AuthoringDialogs
      open={open}
      onOpenChange={onOpenChange}
      title={`Own deploy config for ${chart} on ${d.name}`}
      description={`Excludes ${d.name} from the default on ${panel.label} and deploys it from its own folder (${ownPath}), in one commit. The Application keeps its name, so ArgoCD keeps it; its values still come from the default's layers.`}
      blocker={blocker}
      readOnlyReason={readOnlyReason}
      body={body}
      method="put"
      url={(dryRun) => day2Api.destinationDeploy(team, chart, panel.scope, d.id, dryRun)}
      onOpened={onOpened}
    >
      {own && (
        <>
          <RepoFileView file={own} maxHeight="max-h-40" />
          <div role="radiogroup" aria-label="Own deploy config" className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
            <label className="flex items-center gap-2">
              <input type="radio" name="deploy-mode" checked={!removing} onChange={() => setRemoving(false)} />
              Edit it
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name="deploy-mode" checked={removing} onChange={() => setRemoving(true)} />
              Remove it: back to the fleet default
            </label>
          </div>
        </>
      )}
      {removing ? (
        <p className="rounded-lg border border-dashed px-3 py-4 text-xs text-muted-foreground">
          The own folder goes (a non-empty <code>values.yaml</code> there moves to <code>values-{d.name}.yaml</code>) and the
          exclusion entry with it, so the default deploys {d.name} again. The Application keeps its name.
        </p>
      ) : (
        <>
          <VersionField
            versions={catalog?.available_versions ?? []}
            inherited={inherited}
            pinned={Boolean(text(current, "targetRevision"))}
            value={revision}
            onChange={setRevision}
            emergencyPin={emergencyPin}
            onEmergencyPinChange={setEmergencyPin}
            clusterName={d.name}
          />
          <TextField
            label="Chart repo URL (repourl)"
            type="url"
            value={repourl}
            onChange={setRepourl}
            placeholder={meta?.repourl || "inherited"}
            help="Empty: the team default's."
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label="Path" value={path} onChange={setPath} placeholder={meta?.path || "."} help="Empty: the team default's." />
            <TextField
              label="Project namespace"
              value={namespace}
              onChange={setNamespace}
              placeholder={meta?.projectNamespace || "inherited"}
              help="Empty: the team default's."
            />
          </div>
          <p className="text-xs text-muted-foreground">Only the keys set here are written; every other one is inherited.</p>
        </>
      )}
    </AuthoringDialogs>
  );
}
