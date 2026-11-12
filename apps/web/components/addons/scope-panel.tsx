"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, Cloud, Layers, Pencil, Plus, Server, ServerCog, SlidersHorizontal } from "lucide-react";
import { syncSummary } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import type { OpenedChanges } from "@/components/addons/change-result";
import { EditFleetDefaultDialog, MakeDefaultDialog } from "@/components/addons/default-dialogs";
import { DestinationValuesDialog, EnvValuesDialog } from "@/components/addons/destination-values-dialog";
import { groupDestinations, stateStyle } from "@/components/addons/destinations";
import { DeployOnMces } from "@/components/addons/mce-installs";
import { RepoFileView } from "@/components/addons/repo-file";
import type { AuthoringChange, FleetScope, AddonDetail, ScopeDestination, ScopePanel } from "@/types/day2";

/** Write actions on the add-on: offered to admins, disabled with the reason while the team is read-only. */
export interface AddonWrites {
  isAdmin: boolean;
  readOnlyReason: string | null;
  /** An authoring MR opened. */
  onOpened: (change: AuthoringChange) => void;
  /** Install or removal MRs opened (and the MCEs that did not get one). */
  onChanges: (changes: OpenedChanges) => void;
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

/** The scopes whose envs and destinations get values of their own here (the hub is one destination). */
const VALUES_SCOPES: readonly FleetScope[] = ["mces", "hosted-clusters", "upi"];

const ENVS = ["prod", "prep", "test"] as const;

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

function DestinationRow({
  destination: d,
  writes,
  onValues,
}: {
  destination: ScopeDestination;
  writes: AddonWrites;
  onValues: (destination: ScopeDestination) => void;
}) {
  const style = stateStyle(d.state);
  const overrideExists = Boolean(d.override?.exists);
  const canOverride = overrideExists || ["default", "duplicate", "own-deploy"].includes(d.state);
  return (
    <li
      className={cn("flex flex-wrap items-start gap-x-3 gap-y-1.5 px-3 py-2.5 text-xs", d.state === "duplicate" && "bg-status-error/5")}
      data-testid={`destination-${d.name}`}
    >
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
        {d.override_shared_with.length > 0 && (
          <p className="text-muted-foreground" data-testid="shared-name">
            Same name as {d.override_shared_with.join(", ")}: one values file for all of them.
          </p>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-1.5">
        <WriteButton
          writes={writes}
          onClick={() => onValues(d)}
          label={`${overrideExists ? "Edit" : "Add"} values override on ${d.name}`}
          disabledBy={canOverride ? null : "No app of the default here to override"}
        >
          <SlidersHorizontal className="h-3 w-3" />
          {overrideExists ? "Values" : "Override values"}
        </WriteButton>
      </div>
    </li>
  );
}

/**
 * Where the default deploys, one row per destination of the scope the team's
 * repo registers, and each destination's own values (`values-<name>.yaml`,
 * ADR-0053). Wingman does not choose destinations by exclusion: a repo's
 * existing `exclusions.yaml` is read and shown, never written.
 */
function DefaultDestinations({ detail, panel, writes }: { detail: AddonDetail; panel: ScopePanel; writes: AddonWrites }) {
  const [editing, setEditing] = useState<ScopeDestination | null>(null);
  const exclusions = panel.exclusions;
  return (
    <div className="space-y-2">
      {exclusions && exclusions.names.length > 0 && (
        <p className="text-xs text-muted-foreground" data-testid="exclusions-note">
          The repo&apos;s <code>{exclusions.path}</code> keeps it off {exclusions.names.join(", ")}: Wingman reads that file and does
          not edit it.
        </p>
      )}
      {panel.destinations.length === 0 ? (
        <p className="rounded-lg border border-dashed px-3 py-3 text-xs text-muted-foreground">
          {detail.team}&apos;s repo registers no {panel.noun}: a default here reaches nothing yet.
        </p>
      ) : (
        groupDestinations(panel.destinations).map(([group, items]) => (
          <div key={group} className="overflow-hidden rounded-lg border" role="group" aria-label={group}>
            <p className="border-b bg-muted/40 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{group}</p>
            <ul className="divide-y">
              {items.map((d) => (
                <DestinationRow key={d.id} destination={d} writes={writes} onValues={setEditing} />
              ))}
            </ul>
          </div>
        ))
      )}
      {editing && (
        <DestinationValuesDialog
          team={detail.team}
          chart={detail.name}
          panel={panel}
          destination={editing}
          open
          onOpenChange={(next) => !next && setEditing(null)}
          readOnlyReason={writes.readOnlyReason}
          onOpened={writes.onOpened}
        />
      )}
    </div>
  );
}

/**
 * One env's values of the default, prod, prep and test (`values-<env>.yaml`):
 * below each destination's own values, above the default's.
 */
function EnvOverrides({ detail, panel, writes }: { detail: AddonDetail; panel: ScopePanel; writes: AddonWrites }) {
  const [editing, setEditing] = useState<string | null>(null);
  const fileOf = (env: string) => panel.env_files.find((e) => e.env === env)?.file ?? null;
  const inEnv = (env: string) =>
    panel.destinations.filter((d) => d.env === env && ["default", "duplicate", "own-deploy"].includes(d.state));
  return (
    <div className="space-y-1" data-testid={`env-overrides-${panel.scope}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Values per env</p>
      <ul className="divide-y rounded-lg border">
        {ENVS.map((env) => {
          const file = fileOf(env);
          const reached = inEnv(env);
          return (
            <li key={env} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-xs" data-testid={`env-${env}`}>
              <span className="w-10 font-semibold">{env}</span>
              {file?.exists ? (
                <span className="rounded-full bg-chart-5/12 px-2 py-px text-[10px] font-medium text-chart-5" title={file.path}>
                  values-{env}.yaml
                </span>
              ) : (
                <span className="text-muted-foreground">the default&apos;s values</span>
              )}
              <span className="text-muted-foreground">
                · {reached.length} {panel.noun} in {env}
              </span>
              <span className="ml-auto">
                <WriteButton
                  writes={writes}
                  onClick={() => setEditing(env)}
                  label={`${file?.exists ? "Edit" : "Add"} values for ${env}`}
                >
                  <SlidersHorizontal className="h-3 w-3" />
                  {file?.exists ? "Values" : "Override values"}
                </WriteButton>
              </span>
            </li>
          );
        })}
      </ul>
      {editing && (
        <EnvValuesDialog
          team={detail.team}
          chart={detail.name}
          panel={panel}
          env={editing}
          file={fileOf(editing)}
          destinations={inEnv(editing)}
          open
          onOpenChange={(next) => !next && setEditing(null)}
          readOnlyReason={writes.readOnlyReason}
          onOpened={writes.onOpened}
        />
      )}
    </div>
  );
}

function HostedClustersNote({ detail, panel }: { detail: AddonDetail; panel: ScopePanel }) {
  return (
    <p className="rounded-lg border border-dashed px-3 py-2.5 text-xs text-muted-foreground" data-testid="hosted-clusters-note">
      {panel.is_default
        ? `${detail.name} is deployed on every hosted cluster, with the values above. `
        : `As a default, ${detail.name} is deployed on every hosted cluster, with values per env and per cluster. `}
      Which add-ons a hosted cluster has of its own
      comes from its flavor and the create form (
      <Link href="/specs" className="font-medium text-primary hover:underline">
        Flavors
      </Link>
      ), managed on each cluster&apos;s page: there is no deploying it on specific hosted clusters here.
    </p>
  );
}

/**
 * The add-on on one fleet scope (ADR-0053): whether it is a default there,
 * making it one or editing it. Below it, on the MCE, hosted-cluster and UPI
 * defaults: values per env and per destination; on MCEs, deploying it on
 * specific ones (an install per MCE). A hosted cluster's own add-ons are its
 * flavor's and the create form's.
 */
export function ScopePanelCard({ detail, panel, writes }: { detail: AddonDetail; panel: ScopePanel; writes: AddonWrites }) {
  const [dialog, setDialog] = useState<"make" | "edit" | null>(null);
  const Icon = SCOPE_ICON[panel.scope] ?? Layers;
  const reach = panel.destinations.filter((d) => d.state === "default" || d.state === "duplicate").length;
  const perDestination = VALUES_SCOPES.includes(panel.scope);
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
              ? `Deployed to ${reach} of the ${panel.destinations.length} ${panel.noun} ${detail.team}'s repo registers · ${syncSummary(panel.sync)}${panel.sync_overridden ? " (set by the default)" : ""}`
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

      {perDestination && panel.is_default && <EnvOverrides detail={detail} panel={panel} writes={writes} />}
      {perDestination && panel.is_default && <DefaultDestinations detail={detail} panel={panel} writes={writes} />}
      {panel.scope === "hosted-clusters" && <HostedClustersNote detail={detail} panel={panel} />}
      {panel.scope === "mces" && <DeployOnMces detail={detail} panel={panel} writes={writes} />}

      {panel.scope === "upi" && panel.unregistered.length > 0 && (
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
