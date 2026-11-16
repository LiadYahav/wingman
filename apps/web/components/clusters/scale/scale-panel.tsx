"use client";

import { useState } from "react";
import { Lock, Scaling } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { ProblemList } from "@/components/common/problem-list";
import { useScaleBusy, useScaleOptions, useScaleRun } from "@/lib/scale";
import { needsRestore } from "@/lib/scale-model";
import { cn } from "@/lib/utils";
import type { ScaleNodePool, ScaleOptions } from "@/types";
import { RestoreReplicas } from "./restore-replicas";
import { ScaleDialog } from "./scale-dialog";
import { ScaleRunCard } from "./scale-run-card";

function PoolRow({ pool, name, where, isAdmin }: { pool: ScaleNodePool; name: string; where: string; isAdmin: boolean }) {
  const restore = needsRestore(pool);
  return (
    <li data-testid={`scale-pool-${pool.index}`} className="grid gap-x-4 gap-y-1 px-4 py-2.5 sm:grid-cols-[minmax(0,1fr)_5.5rem]">
      <div className="min-w-0">
        <p className="font-mono text-sm font-medium break-all">{pool.name ?? `nodepool[${pool.index}]`}</p>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
          {pool.infra_env && <span className="font-mono break-all">{pool.infra_env}</span>}
          {pool.locked_by && (
            <span className="inline-flex items-center gap-1" data-testid="scale-pool-locked">
              <Lock className="h-3 w-3 shrink-0" aria-hidden />
              Locked by flavor {pool.locked_by} at {pool.locked_replicas ?? "—"}
            </span>
          )}
          {pool.unnamed && <span className="break-words">{pool.unnamed}</span>}
        </p>
        {restore && isAdmin && pool.name && pool.locked_replicas !== null && (
          <div className="mt-1.5">
            <RestoreReplicas
              name={name}
              where={where}
              nodepool={pool.name}
              current={pool.replicas}
              target={pool.locked_replicas}
              runShows="below"
            />
          </div>
        )}
      </div>
      <p className={cn("text-sm tabular-nums sm:text-right", restore && "font-medium text-status-warning-fg")}>
        {pool.replicas ?? "—"}
        <span className="text-xs font-normal text-muted-foreground"> replica{pool.replicas === 1 ? "" : "s"}</span>
      </p>
    </li>
  );
}

function Header({
  options,
  isAdmin,
  busy,
  onScale,
}: {
  options: ScaleOptions;
  isAdmin: boolean;
  busy: string | null;
  onScale: (trigger: HTMLElement) => void;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2 px-4 pb-3 pt-3.5">
      <div className="min-w-0 space-y-1">
        <h2 id="scale-heading" className="flex items-center gap-2 text-sm font-semibold">
          <Scaling className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          NodePool sizes
        </h2>
        <p className="text-xs text-muted-foreground max-w-2xl">
          As the day1 file sets them. They change only through the platform&apos;s update-nodepool workflow: one commit to day1
          main, applied by Argo CD{options.flavor ? <>; replicas flavor {options.flavor} locks stay as it sets them</> : null}.
        </p>
      </div>
      {isAdmin && (
        <button
          type="button"
          data-testid="scale-action"
          onClick={(e) => onScale(e.currentTarget)}
          disabled={busy !== null}
          aria-describedby={busy ? "scale-busy-reason" : undefined}
          title="Start the platform's update-nodepool workflow"
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          <Scaling aria-hidden />
          Scale
        </button>
      )}
    </header>
  );
}

/**
 * The Nodes tab's NodePool sizes, from the cluster's day1 file, and Scale
 * (ADR-0062): an admin starts the platform's update-nodepool workflow on a
 * hardware kind or one NodePool, and the run shows here for everyone. It
 * needs no live status: the file names the NodePools as the chart does. A
 * locked NodePool whose replicas drifted from its flavor offers a restore.
 * Nothing at all while scaling is off. Mount it where it is shown.
 */
export function ScalePanel({ name, where, isAdmin, enabled = true }: { name: string; where: string; isAdmin: boolean; enabled?: boolean }) {
  const options = useScaleOptions(name, where, { enabled });
  const run = useScaleRun(name, where, { enabled });
  const busy = useScaleBusy(name, where);
  const [scaling, setScaling] = useState<{ trigger: HTMLElement } | null>(null);
  const shown = run.data?.state === "run" ? run.data.run : null;

  if (options.error) {
    return (
      <div data-testid="scale-error-read">
        <ProblemList error={options.error} title="The NodePool sizes could not be read" />
      </div>
    );
  }
  if (options.data?.state !== "on") return null;
  const read = options.data.options;

  const close = () => {
    const trigger = scaling?.trigger;
    setScaling(null);
    requestAnimationFrame(() => {
      if (trigger?.isConnected) trigger.focus();
    });
  };

  return (
    <div className="space-y-3">
      <section aria-labelledby="scale-heading" data-testid="scale-panel" className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <Header options={read} isAdmin={isAdmin} busy={busy} onScale={(trigger) => setScaling({ trigger })} />
        {isAdmin && busy && (
          <p id="scale-busy-reason" data-testid="scale-busy-reason" className="border-t bg-muted/30 px-4 py-2 text-xs text-muted-foreground">
            {busy}
          </p>
        )}
        {read.nodepools.length === 0 ? (
          <p className="border-t px-4 py-3 text-xs text-muted-foreground">The cluster file has no NodePool.</p>
        ) : (
          <ul className="divide-y border-t" aria-label="NodePools in the day1 file">
            {read.nodepools.map((p) => (
              <PoolRow key={p.index} pool={p} name={name} where={where} isAdmin={isAdmin} />
            ))}
          </ul>
        )}
      </section>
      {run.error ? (
        <ProblemList error={run.error} title="The cluster's update-nodepool run could not be read" />
      ) : (
        shown && <ScaleRunCard run={shown} />
      )}
      {scaling && <ScaleDialog name={name} where={where} options={read} onClose={close} />}
    </div>
  );
}
