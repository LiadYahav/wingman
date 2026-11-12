"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Rocket, Trash2 } from "lucide-react";
import { api } from "@/lib/api-client";
import { day2Api } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ReviewDialog } from "@/components/common/review-dialog";
import type { OpenedChanges } from "@/components/addons/change-result";
import { groupDestinations } from "@/components/addons/destinations";
import { WriteError } from "@/components/addons/file-preview";
import { YamlValuesField } from "@/components/addons/yaml-values-field";
import type { Values } from "@/lib/values";
import type { AddonDetail, ChangeResult, MceInstall, MceInstalls, MceInstallsBody, ScopeDestination, ScopePanel } from "@/types/day2";

/** Write actions here: admins only, disabled with the reason while the team is read-only. */
export interface InstallWrites {
  isAdmin: boolean;
  readOnlyReason: string | null;
  onChanges: (changes: OpenedChanges) => void;
}

interface Candidate {
  id: string;
  name: string;
  site: string;
  env: string;
  /** The team's repo has a folder for it already. */
  registered: boolean;
  renders: boolean;
}

const STATUS_TONE: Record<MceInstall["status"], string> = {
  planned: "bg-status-ready/12 text-status-ready-fg",
  opened: "bg-status-ready/12 text-status-ready-fg",
  refused: "bg-status-error/12 text-status-error-fg",
  failed: "bg-status-error/12 text-status-error-fg",
};

/** What the page's panel says the installs opened, and which MCEs did not get one. */
function opened(result: MceInstalls): OpenedChanges {
  return {
    verb: "Install",
    results: result.installs
      .filter((i) => i.merge_request)
      .map((i) => {
        const mr = i.merge_request as NonNullable<MceInstall["merge_request"]>;
        return { team: mr.team, iid: mr.iid, web_url: mr.web_url, title: mr.title, files: i.files, warnings: i.warnings, notes: i.notes };
      }),
    failed: result.installs
      .filter((i) => i.status === "refused" || i.status === "failed")
      .map((i) => ({ team: i.name, error: i.status, detail: i.detail ?? i.status })),
  };
}

function RemoveInstallDialog({
  team,
  chart,
  destination,
  onClose,
  onChanges,
}: {
  team: string;
  chart: string;
  destination: ScopeDestination;
  onClose: () => void;
  onChanges: InstallWrites["onChanges"];
}) {
  const [typed, setTyped] = useState("");
  const app = destination.app_name ?? `${team}-in-cluster-${chart}-deploy`;
  const remove = useMutation({
    mutationFn: () => api.del<ChangeResult>(day2Api.remove(destination.id, team, chart)),
    onSuccess: (result) => {
      onChanges({ verb: "Remove", results: [result], failed: [] });
      onClose();
    },
  });
  return (
    <ReviewDialog
      open
      onOpenChange={(next) => !next && onClose()}
      title={`Remove ${chart} from ${destination.name}`}
      description={`Opens a merge request on ${team}'s repo deleting the chart's folder on this MCE.`}
      onConfirm={() => remove.mutate()}
      isPending={remove.isPending}
      confirmDisabled={typed !== chart}
      confirmLabel="Open removal MR"
      confirmVariant="destructive"
    >
      <div className="space-y-4">
        <div className="rounded-lg border border-status-warning/40 bg-status-warning/8 p-3 text-sm" role="note">
          <p className="font-semibold text-status-warning-fg">The workload keeps running.</p>
          <p className="mt-1 text-xs text-foreground/90">
            Deleting the folder deletes the ArgoCD Application <code className="break-all">{app}</code>, but ArgoCD orphans what it
            deployed: {chart} stays on {destination.name}. To tear it down, run{" "}
            <code className="break-all rounded bg-muted px-1">argocd app delete {app} --cascade</code> on {destination.name}&apos;s
            ArgoCD after the merge (runbook R8). Wingman has no ArgoCD access.
          </p>
        </div>
        {destination.own_folder && (
          <div className="space-y-1 text-xs">
            <p className="text-muted-foreground">Deletes every file under</p>
            <code className="block break-all rounded bg-muted/60 px-2 py-1 font-mono text-[11px]">{destination.own_folder}/</code>
          </div>
        )}
        <label className="block space-y-1.5 text-sm">
          <span>
            Type <code className="rounded bg-muted px-1.5 py-0.5 text-destructive">{chart}</code> to confirm
          </span>
          <input
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={chart}
            autoComplete="off"
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-destructive/50"
          />
        </label>
        <WriteError error={remove.error} />
      </div>
    </ReviewDialog>
  );
}

/**
 * Deploy on specific MCEs (ADR-0053's amendment; ADR-0022's install): an
 * add-on wanted on some MCEs only is not a default with exclusions, it is
 * installed in each chosen MCE's own `in-cluster/<chart>/`, one merge request
 * per MCE. The preview plans each MCE (or says why one is refused); confirming
 * opens the planned ones. Where it is installed is listed per MCE, with the
 * usual remove (which orphans the workload).
 */
export function DeployOnMces({ detail, panel, writes }: { detail: AddonDetail; panel: ScopePanel; writes: InstallWrites }) {
  const installed = panel.destinations.filter((d) => d.state === "own-folder");
  const candidates: Candidate[] = [
    ...panel.destinations
      .filter((d) => d.state === "none" || d.state === "not-rendered")
      .map((d) => ({ id: d.id, name: d.name, site: d.site, env: d.env, registered: true, renders: d.renders })),
    ...panel.unregistered.map((u) => ({ id: u.id, name: u.name, site: u.site, env: u.env, registered: false, renders: Boolean(u.env) })),
  ];
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [values, setValues] = useState<Values | null>({});
  const [plan, setPlan] = useState<MceInstalls | null>(null);
  const [sent, setSent] = useState<MceInstallsBody | null>(null);
  const [removing, setRemoving] = useState<ScopeDestination | null>(null);

  const blockedBy = panel.is_default
    ? `${detail.name} is a default on every MCE: installing it in an MCE's own folder too would generate its app twice (the XOR rule). Give one MCE its own values above instead.`
    : !detail.catalog
      ? `${detail.name} is not in ${detail.team}'s catalog (operators/${detail.name}/): an install starts from its team default.`
      : null;
  const writable = writes.isAdmin && !writes.readOnlyReason && !blockedBy;
  const valuesPath = `sites/<site>/<env>/mces/<mce>/in-cluster/${detail.name}/values.yaml`;

  const preview = useMutation({
    mutationFn: (body: MceInstallsBody) => api.post<MceInstalls>(day2Api.mceInstalls(detail.team, detail.name, true), body),
    onSuccess: (result, body) => {
      setPlan(result);
      setSent(body);
    },
  });
  const open = useMutation({
    mutationFn: (body: MceInstallsBody) => api.post<MceInstalls>(day2Api.mceInstalls(detail.team, detail.name, false), body),
    onSuccess: (result) => {
      writes.onChanges(opened(result));
      setPlan(null);
      setSent(null);
      setChosen(new Set());
    },
  });
  const planned = plan?.installs.filter((i) => i.status === "planned") ?? [];

  function body(): MceInstallsBody {
    return { clusters: candidates.filter((c) => chosen.has(c.id)).map((c) => c.id), values: values ?? {}, message: null };
  }

  return (
    <section className="space-y-3 rounded-lg border bg-muted/10 p-3" aria-label="Deploy on specific MCEs" data-testid="deploy-on-mces">
      <div>
        <h4 className="flex items-center gap-1.5 text-xs font-semibold">
          <Rocket className="h-3.5 w-3.5 text-primary" aria-hidden />
          Deploy on specific MCEs
        </h4>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Installs {detail.name} in each chosen MCE&apos;s own folder, <code>in-cluster/{detail.name}/</code>: one merge request per
          MCE, each checked on its own. For every MCE, make it a default instead.
        </p>
      </div>

      {installed.length > 0 && (
        <div className="space-y-1" data-testid="installed-mces">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Installed on</p>
          <ul className="divide-y rounded-lg border bg-card">
            {installed.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-xs" data-testid={`installed-${d.name}`}>
                <span className="font-semibold">{d.name}</span>
                <span className="break-all font-mono text-[11px] text-muted-foreground">{d.own_folder ?? d.id}</span>
                {writes.isAdmin && (
                  <button
                    type="button"
                    onClick={() => setRemoving(d)}
                    disabled={Boolean(writes.readOnlyReason)}
                    title={writes.readOnlyReason ?? undefined}
                    aria-label={`Remove ${detail.name} from ${d.name}`}
                    className={cn(buttonVariants({ variant: "outline", size: "sm" }), "ml-auto h-7 gap-1.5")}
                  >
                    <Trash2 className="h-3 w-3" />
                    Remove
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {blockedBy ? (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground" role="note" data-testid="deploy-on-mces-blocked">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          {blockedBy}
        </p>
      ) : candidates.length === 0 ? (
        <p className="text-xs text-muted-foreground">Every MCE Wingman knows has it already.</p>
      ) : (
        <>
          <div className="space-y-2">
            {groupDestinations(candidates).map(([group, items]) => (
              <div key={group} className="overflow-hidden rounded-lg border bg-card" role="group" aria-label={group}>
                <p className="border-b bg-muted/40 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{group}</p>
                <ul className="divide-y">
                  {items.map((c) => (
                    <li key={c.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-3 py-2 text-xs">
                      <label className="mt-0.5 flex items-center" title={c.renders ? undefined : "The platform renders nothing for it (no day1 version)"}>
                        <Checkbox
                          checked={chosen.has(c.id)}
                          disabled={!writable || !c.renders}
                          onCheckedChange={(on) =>
                            setChosen((prev) => {
                              const next = new Set(prev);
                              if (on) next.add(c.id);
                              else next.delete(c.id);
                              return next;
                            })
                          }
                        />
                        <span className="sr-only">Deploy on {c.name}</span>
                      </label>
                      <div className="min-w-0 flex-1 space-y-0.5">
                        <p className="font-semibold">{c.name}</p>
                        <p className="break-all font-mono text-[11px] text-muted-foreground">{c.id}</p>
                        {!c.registered && (
                          <p className="text-muted-foreground">
                            Not registered with {detail.team} yet: installing registers it, so {detail.team}&apos;s MCE defaults reach it
                            too.
                          </p>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          {writable && (
            <>
              <YamlValuesField
                label="Values for each chosen MCE"
                path={valuesPath}
                initial={{}}
                onChange={setValues}
                placeholder="# Empty: the team values apply."
              />
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => preview.mutate(body())}
                  disabled={chosen.size === 0 || values === null || preview.isPending}
                  title={chosen.size === 0 ? "Choose at least one MCE" : values === null ? "Fix the values YAML" : undefined}
                  className={cn(buttonVariants({ size: "sm" }), "h-7")}
                >
                  {preview.isPending
                    ? "Checking…"
                    : chosen.size === 0
                      ? "Preview installs"
                      : `Preview ${chosen.size} install${chosen.size === 1 ? "" : "s"}`}
                </button>
              </div>
            </>
          )}
          <WriteError error={preview.error} />
        </>
      )}

      {plan && sent && (
        <ReviewDialog
          open
          onOpenChange={(next) => {
            if (!next) {
              setPlan(null);
              setSent(null);
              open.reset();
            }
          }}
          title={`Deploy ${detail.team}/${detail.name} on specific MCEs`}
          description="One merge request per MCE, checked by the service on its own. Nothing is opened until you confirm."
          onConfirm={() => open.mutate({ ...sent, clusters: planned.map((i) => i.cluster) })}
          isPending={open.isPending}
          confirmDisabled={planned.length === 0}
          confirmLabel={`Open ${planned.length} merge request${planned.length === 1 ? "" : "s"}`}
          size="lg"
        >
          <ul className="space-y-2" aria-label="Per MCE" data-testid="mce-install-plan">
            {plan.installs.map((i) => (
              <li key={i.cluster} className="space-y-1 rounded-lg border px-3 py-2 text-xs" data-testid={`plan-${i.name}`}>
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{i.name}</span>
                  <span className={cn("rounded-full px-2 py-px text-[10px] font-medium", STATUS_TONE[i.status])}>
                    {i.status === "planned" ? "one merge request" : i.status}
                  </span>
                </p>
                {i.detail && <p className="text-status-error-fg">{i.detail}</p>}
                {i.files.map((f) => (
                  <p key={f.path} className="break-all font-mono text-[11px] text-muted-foreground">
                    {f.action} {f.path}
                  </p>
                ))}
                {i.notes.map((n) => (
                  <p key={n} className="text-muted-foreground">
                    {n}
                  </p>
                ))}
              </li>
            ))}
          </ul>
          <WriteError error={open.error} />
        </ReviewDialog>
      )}
      {removing && (
        <RemoveInstallDialog
          team={detail.team}
          chart={detail.name}
          destination={removing}
          onClose={() => setRemoving(null)}
          onChanges={writes.onChanges}
        />
      )}
    </section>
  );
}
