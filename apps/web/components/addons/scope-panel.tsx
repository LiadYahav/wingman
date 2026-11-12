"use client";

import { useState } from "react";
import { AlertTriangle, Cloud, Layers, Pencil, Plus, RotateCcw, Server, ServerCog, SlidersHorizontal, Unplug, Wrench } from "lucide-react";
import { day2Api, syncSummary } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { AuthoringReview, useAuthoringWrite } from "@/components/addons/authoring-flow";
import { EditFleetDefaultDialog, MakeDefaultDialog } from "@/components/addons/default-dialogs";
import { WriteError } from "@/components/addons/file-preview";
import { DestinationDeployDialog } from "@/components/addons/destination-deploy-dialog";
import { DestinationValuesDialog } from "@/components/addons/destination-values-dialog";
import { excludedIds, groupDestinations, lockedReason, nameOf, stateStyle } from "@/components/addons/destinations";
import { RepoFileView } from "@/components/addons/repo-file";
import type { AuthoringChange, FleetScope, AddonDetail, ScopeDestination, ScopePanel, SetExclusionsBody } from "@/types/day2";

/** Write actions on the add-on: offered to admins, disabled with the reason while the team is read-only. */
export interface AddonWrites {
  isAdmin: boolean;
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}

const SCOPE_ICON: Record<FleetScope, typeof Server> = {
  "hosted-clusters": Cloud,
  mces: ServerCog,
  hub: Layers,
  upi: Server,
};

const SCOPE_TITLE: Record<FleetScope, string> = {
  "hosted-clusters": "Hosted clusters",
  mces: "MCEs",
  hub: "Hub",
  upi: "UPI clusters",
};

function WriteButton({
  writes,
  onClick,
  children,
  label,
  disabledBy,
}: {
  writes: AddonWrites;
  onClick: () => void;
  children: React.ReactNode;
  label?: string;
  /** Another reason it cannot be pressed. */
  disabledBy?: string | null;
}) {
  if (!writes.isAdmin) return null;
  const reason = writes.readOnlyReason ?? disabledBy ?? null;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={Boolean(reason)}
      title={reason ?? undefined}
      aria-label={label}
      className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7 gap-1.5")}
    >
      {children}
    </button>
  );
}

type RowDialog = { kind: "values" | "deploy"; destination: ScopeDestination } | null;

function DestinationRow({
  panel,
  destination: d,
  checkbox,
  writes,
  onDialog,
}: {
  panel: ScopePanel;
  destination: ScopeDestination;
  /** The "deployed by this default" checkbox, or `null` where there is none (the hub, not a default). */
  checkbox: { checked: boolean; disabledBy: string | null; onChange: (on: boolean) => void; changed: boolean } | null;
  writes: AddonWrites;
  onDialog: (dialog: RowDialog) => void;
}) {
  const style = stateStyle(d.state);
  const locked = lockedReason(d);
  const overrides = panel.is_default && panel.scope !== "hub";
  const overrideExists = Boolean(d.override?.exists);
  const canOverrideValues = overrideExists || ["default", "own-deploy", "duplicate"].includes(d.state);
  const canOwnDeploy = d.renders && ["default", "excluded", "own-deploy", "duplicate"].includes(d.state);
  return (
    <li
      className={cn(
        "flex flex-wrap items-start gap-x-3 gap-y-1.5 px-3 py-2.5 text-xs",
        d.state === "duplicate" && "bg-status-error/5",
        checkbox?.changed && (checkbox.checked ? "bg-status-ready/5" : "bg-status-error/5"),
      )}
      data-testid={`destination-${d.name}`}
    >
      {checkbox && (
        <label className="mt-0.5 flex items-center" title={checkbox.disabledBy ?? undefined}>
          <Checkbox checked={checkbox.checked} onCheckedChange={checkbox.onChange} disabled={Boolean(checkbox.disabledBy)} />
          <span className="sr-only">Deployed by this default on {d.name}</span>
        </label>
      )}
      <div className="min-w-0 flex-1 basis-56 space-y-0.5">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-semibold">{d.name}</span>
          <span className={cn("rounded-full px-2 py-px text-[10px] font-medium", style.tone)} title={style.description}>
            {style.label}
          </span>
          {overrideExists && (
            <span className="rounded-full bg-chart-5/12 px-2 py-px text-[10px] font-medium text-chart-5" title={d.override?.path}>
              values-{d.name}.yaml
            </span>
          )}
          {checkbox?.changed && (
            <span className={cn("text-[10px] font-semibold uppercase", checkbox.checked ? "text-status-ready-fg" : "text-status-error-fg")}>
              {checkbox.checked ? "will be included" : "will be excluded"}
            </span>
          )}
        </p>
        <p className="break-all font-mono text-[11px] text-muted-foreground">
          {d.id}
          {d.ocp_version && <span className="font-sans"> · OCP {d.ocp_version}</span>}
          {d.app_name && <span> · {d.app_name}</span>}
        </p>
        {d.state === "duplicate" && (
          <p className="flex items-start gap-1 text-status-error-fg" role="note">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
            {style.description}
          </p>
        )}
        {locked && checkbox && <p className="text-muted-foreground">{locked}</p>}
        {d.override_shared_with.length > 0 && (
          <p className="text-muted-foreground" data-testid="shared-name">
            Same name as {d.override_shared_with.join(", ")}: {checkbox ? "excluded or included together, and " : ""}one values file for
            all of them.
          </p>
        )}
      </div>
      {overrides && (
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          <WriteButton
            writes={writes}
            onClick={() => onDialog({ kind: "values", destination: d })}
            label={`${overrideExists ? "Edit" : "Add"} values override on ${d.name}`}
            disabledBy={canOverrideValues ? null : "No app of the default here to override"}
          >
            <SlidersHorizontal className="h-3 w-3" />
            {overrideExists ? "Values" : "Override values"}
          </WriteButton>
          <WriteButton
            writes={writes}
            onClick={() => onDialog({ kind: "deploy", destination: d })}
            label={`${d.own_deploy?.exists ? "Edit own" : "Set an own"} deploy config on ${d.name}`}
            disabledBy={canOwnDeploy ? null : "The platform renders nothing here"}
          >
            <Wrench className="h-3 w-3" />
            {d.own_deploy?.exists ? "Own deploy" : "Override deploy"}
          </WriteButton>
        </div>
      )}
    </li>
  );
}

/**
 * Which destinations the default deploys to (ADR-0053): every destination of
 * the scope the team's repo registers, a checkbox each. Saving writes the
 * full excluded set to `defaults/<scope>/exclusions.yaml` in place. Excluding
 * deletes the Application and orphans the workload (`prune: false`): the
 * page says so beside the checkbox, and the plan has the user confirm
 * exactly those destinations.
 */
function DestinationsEditor({ detail, panel, writes }: { detail: AddonDetail; panel: ScopePanel; writes: AddonWrites }) {
  const initial = excludedIds(panel);
  const [excluded, setExcluded] = useState<Set<string>>(initial);
  const [dialog, setDialog] = useState<RowDialog>(null);
  const exclusions = panel.exclusions;
  const editable = writes.isAdmin && !writes.readOnlyReason && Boolean(exclusions?.editable) && panel.is_default;
  const write = useAuthoringWrite<SetExclusionsBody>({
    method: "put",
    url: (dryRun) => day2Api.exclusions(detail.team, detail.name, panel.scope, dryRun),
    onOpened: (change) => {
      writes.onOpened(change);
      setExcluded(initial);
    },
  });

  const newlyExcluded = [...excluded].filter((id) => !initial.has(id));
  const newlyIncluded = [...initial].filter((id) => !excluded.has(id));
  const dirty = newlyExcluded.length > 0 || newlyIncluded.length > 0;
  const showBoxes = panel.is_default && exclusions !== null;

  /**
   * `exclusions.yaml` names destinations by name, so two of the scope with the
   * same name are excluded together or not at all (the service's rule
   * `exclusion-shared`): a checkbox moves its namesakes too.
   */
  function toggle(d: ScopeDestination, on: boolean) {
    const ids = [d.id, ...d.override_shared_with.filter((id) => panel.destinations.some((x) => x.id === id))];
    setExcluded((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (on) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }

  function body(): SetExclusionsBody {
    // The full set, in the panel's order: the others are included.
    return {
      excluded: panel.destinations.filter((d) => excluded.has(d.id)).map((d) => d.id),
      last_commit_id: exclusions?.last_commit_id ?? panel.last_commit_id,
      confirm_changes: [],
      expected_digest: null,
      message: null,
    };
  }

  const groups = groupDestinations(panel.destinations);
  return (
    <div className="space-y-3">
      {exclusions && !exclusions.editable && (
        <p className="flex items-start gap-1.5 rounded-lg border border-status-warning/30 bg-status-warning/8 px-3 py-2 text-xs text-status-warning-fg" role="note">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          <span className="min-w-0 break-words">
            Wingman cannot edit <code>{exclusions.path}</code> in place{exclusions.problem ? `: ${exclusions.problem}` : "."} Edit it by hand.
          </span>
        </p>
      )}
      {exclusions && exclusions.unknown_names.length > 0 && (
        <p className="text-xs text-status-warning-fg">
          <code>{exclusions.path}</code> also names {exclusions.unknown_names.join(", ")}, which{" "}
          {exclusions.unknown_names.length === 1 ? "is" : "are"} no destination of {detail.team}: kept as written (lint{" "}
          <code>exclusions-unknown-target</code>).
        </p>
      )}
      {panel.destinations.length === 0 ? (
        <p className="rounded-lg border border-dashed px-3 py-3 text-xs text-muted-foreground">
          {detail.team}&apos;s repo registers no {panel.noun}: a default here reaches nothing yet.
        </p>
      ) : (
        <div className="space-y-2">
          {groups.map(([group, items]) => (
            <div key={group} className="overflow-hidden rounded-lg border" role="group" aria-label={group}>
              <p className="border-b bg-muted/40 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{group}</p>
              <ul className="divide-y">
                {items.map((d) => {
                  const locked = lockedReason(d);
                  const checkbox = showBoxes
                    ? {
                        // Nothing is deployed where the platform renders nothing, excluded or not.
                        checked: !excluded.has(d.id) && d.state !== "not-rendered",
                        disabledBy: locked ?? (editable ? null : writes.readOnlyReason ?? exclusions?.problem ?? (writes.isAdmin ? "Wingman cannot edit the exclusions file in place" : "Only admins edit exclusions")),
                        onChange: (on: boolean) => toggle(d, on),
                        changed: initial.has(d.id) !== excluded.has(d.id),
                      }
                    : null;
                  return <DestinationRow key={d.id} panel={panel} destination={d} checkbox={checkbox} writes={writes} onDialog={setDialog} />;
                })}
              </ul>
            </div>
          ))}
        </div>
      )}

      {newlyExcluded.length > 0 && (
        <div className="space-y-1 rounded-lg border border-status-error/40 bg-status-error/8 p-3 text-xs" role="note" data-testid="exclude-warning">
          <p className="flex items-start gap-2 font-semibold text-status-error-fg">
            <Unplug className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            Excluding deletes the Application on {newlyExcluded.map((id) => nameOf(panel, id)).join(", ")}: the workload keeps
            running, unmanaged.
          </p>
          <p className="text-foreground/90">
            Leaf apps have <code>prune: false</code>, so ArgoCD orphans what {detail.name} deployed there. The preview lists each
            one, and you confirm them before the merge request opens.
          </p>
        </div>
      )}
      {newlyIncluded.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Including {newlyIncluded.map((id) => nameOf(panel, id)).join(", ")} generates the app there again; the new Application
          adopts what is still running.
        </p>
      )}
      {showBoxes && editable && (
        <div className="flex flex-wrap items-center justify-end gap-2">
          {dirty && (
            <button type="button" onClick={() => setExcluded(initial)} className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "h-7 gap-1.5")}>
              <RotateCcw className="h-3 w-3" />
              Reset
            </button>
          )}
          <button
            type="button"
            onClick={() => write.preview(body())}
            disabled={!dirty || write.previewing}
            title={dirty ? undefined : "Tick or untick a destination first"}
            className={cn(buttonVariants({ size: "sm" }), "h-7")}
          >
            {write.previewing ? "Checking…" : "Preview exclusions"}
          </button>
        </div>
      )}
      <WriteError error={write.previewError} />
      <AuthoringReview write={write} title={`Which ${panel.noun} get ${detail.team}/${detail.name}`} />

      {dialog?.kind === "values" && (
        <DestinationValuesDialog
          team={detail.team}
          chart={detail.name}
          panel={panel}
          destination={dialog.destination}
          open
          onOpenChange={(next) => !next && setDialog(null)}
          readOnlyReason={writes.readOnlyReason}
          onOpened={writes.onOpened}
        />
      )}
      {dialog?.kind === "deploy" && (
        <DestinationDeployDialog
          team={detail.team}
          chart={detail.name}
          catalog={detail.catalog}
          panel={panel}
          destination={dialog.destination}
          open
          onOpenChange={(next) => !next && setDialog(null)}
          readOnlyReason={writes.readOnlyReason}
          onOpened={writes.onOpened}
        />
      )}
    </div>
  );
}

/**
 * The add-on on one fleet scope (ADR-0053): whether it is a default there;
 * if not, making it one; if so, its values and sync override, which
 * destinations it deploys to, and each destination's overrides.
 */
export function ScopePanelCard({ detail, panel, writes }: { detail: AddonDetail; panel: ScopePanel; writes: AddonWrites }) {
  const [dialog, setDialog] = useState<"make" | "edit" | null>(null);
  const Icon = SCOPE_ICON[panel.scope] ?? Layers;
  const reach = panel.destinations.filter((d) => d.state === "default" || d.state === "duplicate").length;
  const skipped = panel.destinations.filter((d) => d.state === "excluded" || d.state === "own-deploy").length;
  return (
    <section
      className={cn("space-y-4 rounded-xl border bg-card p-4 shadow-sm sm:p-5", panel.is_default && "border-chart-5/30")}
      aria-label={`Default on ${panel.label}`}
      data-testid={`scope-${panel.scope}`}
    >
      <div className="flex flex-wrap items-start gap-3">
        <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", panel.is_default ? "bg-chart-5/15 text-chart-5" : "bg-muted text-muted-foreground")}>
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold">
            {SCOPE_TITLE[panel.scope] ?? panel.label}{" "}
            <span
              className={cn(
                "ml-1 rounded-full px-2 py-0.5 align-middle text-[11px] font-medium",
                panel.is_default ? "bg-chart-5/12 text-chart-5" : "bg-muted text-muted-foreground",
              )}
              data-testid="scope-status"
            >
              {panel.is_default ? "a default" : "not a default"}
            </span>
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {panel.is_default
              ? `Deployed to ${reach} of the ${panel.destinations.length} ${panel.noun} ${detail.team}'s repo registers${skipped ? ` · ${skipped} excluded` : ""} · ${syncSummary(panel.sync)}${panel.sync_overridden ? " (set by the default)" : ""}`
              : `${detail.team}'s repo registers ${panel.destinations.length} ${panel.noun}: making it a default there deploys it to each one.`}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {panel.is_default ? (
            <WriteButton writes={writes} onClick={() => setDialog("edit")} label={`Edit the default on ${panel.label}`}>
              <Pencil className="h-3 w-3" />
              Edit default
            </WriteButton>
          ) : (
            <WriteButton
              writes={writes}
              onClick={() => setDialog("make")}
              label={`Make it a default on ${panel.label}`}
              disabledBy={detail.catalog ? null : `${detail.name} is not in ${detail.team}'s catalog (operators/${detail.name}/)`}
            >
              <Plus className="h-3 w-3" />
              Make it a default
            </WriteButton>
          )}
        </div>
      </div>

      {panel.is_default && (
        <details className="group rounded-lg border bg-muted/10 px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium">
            Files of the default <code className="font-mono text-[11px] text-muted-foreground">{panel.folder}/</code>
          </summary>
          <div className="mt-2 grid gap-3 lg:grid-cols-2">
            <RepoFileView file={panel.values_file} absent="No values.yaml: the team values apply." />
            <RepoFileView file={panel.deploy_config} absent={`No ${detail.name}.yaml: the team default's deploy config and sync options apply.`} />
            {panel.env_files.map((e) => (
              <RepoFileView key={e.env} file={e.file} />
            ))}
          </div>
        </details>
      )}

      <DestinationsEditor key={`${panel.last_commit_id}|${panel.exclusions?.last_commit_id ?? ""}`} detail={detail} panel={panel} writes={writes} />

      {panel.unregistered.length > 0 && (
        <div className="space-y-1 text-xs" data-testid={`unregistered-${panel.scope}`}>
          <p className="font-semibold uppercase tracking-wide text-muted-foreground">Other {panel.noun} Wingman knows</p>
          <ul className="space-y-0.5">
            {panel.unregistered.map((u) => (
              <li key={u.id} className="text-muted-foreground">
                <span className="font-medium text-foreground">{u.name}</span>
                {u.site && ` · ${u.site}`}
                {u.env && ` · ${u.env}`}: not registered with {detail.team}, a default does not reach it.
              </li>
            ))}
          </ul>
        </div>
      )}

      {dialog === "make" && detail.catalog && (
        <MakeDefaultDialog
          entry={detail.catalog}
          panel={panel}
          open
          onOpenChange={(next) => !next && setDialog(null)}
          readOnlyReason={writes.readOnlyReason}
          onOpened={writes.onOpened}
        />
      )}
      {dialog === "edit" && (
        <EditFleetDefaultDialog
          team={detail.team}
          chart={detail.name}
          inCatalog={detail.in_catalog}
          panel={panel}
          open
          onOpenChange={(next) => !next && setDialog(null)}
          readOnlyReason={writes.readOnlyReason}
          onOpened={writes.onOpened}
        />
      )}
    </section>
  );
}
