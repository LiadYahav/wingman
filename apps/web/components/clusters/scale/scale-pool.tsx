"use client";

import { Lock } from "lucide-react";
import { needsRestore, nodepoolBlock } from "@/lib/scale-model";
import { cn } from "@/lib/utils";
import type { ScaleNodePool } from "@/types";
import { ReplicasStepper, stepperInputId } from "./replicas-stepper";
import { RestoreReplicas } from "./restore-replicas";
import { PendingChange } from "./scale-pending";
import { BUSY_ID, useScaleTab, type ScaleTabValue } from "./scale-tab";

const whyIdOf = (pool: ScaleNodePool) => `scale-pool-${pool.index}-why`;

/** `3 replicas`, or a dash when the file's is not a number. */
function Count({ replicas, className }: { replicas: number | null; className?: string }) {
  return (
    <p className={cn("ml-auto shrink-0 text-sm tabular-nums", className)}>
      {replicas ?? "—"}
      <span className="text-xs font-normal text-muted-foreground"> {replicas === 1 ? "replica" : "replicas"}</span>
    </p>
  );
}

/** Why a NodePool's replicas are held, read with its stepper; and, for an admin, a restore to its flavor's value. */
function Held({ tab, pool }: { tab: ScaleTabValue; pool: ScaleNodePool }) {
  const block = nodepoolBlock(pool);
  if (!block) return null;
  const restore = tab.isAdmin && needsRestore(pool) && pool.name !== null && pool.locked_replicas !== null;
  return (
    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
      <span id={whyIdOf(pool)} className="inline-flex items-start gap-1 break-words" data-testid={pool.locked_by ? "scale-pool-locked" : "scale-blocked"}>
        {pool.locked_by && <Lock className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />}
        {block}
      </span>
      {restore && (
        <RestoreReplicas
          name={tab.cluster.name}
          where={tab.cluster.where}
          nodepool={pool.name as string}
          current={pool.replicas}
          target={pool.locked_replicas as number}
          runShows="under NodePool sizes"
          busyId={tab.busy ? BUSY_ID : undefined}
        />
      )}
    </div>
  );
}

/** Whether a NodePool's replicas can change now: an admin's, named, not locked, a number, and no run of the cluster going. */
const scalable = (tab: ScaleTabValue, pool: ScaleNodePool): pool is ScaleNodePool & { name: string } =>
  tab.isAdmin && tab.busy === null && nodepoolBlock(pool) === null;

/**
 * One NodePool's size: a stepper when it can change now, else the number as
 * text, so a held size never looks editable (the reason is said beside it,
 * or once at the panel's top while a run is going).
 */
function PoolSize({ tab, pool }: { tab: ScaleTabValue; pool: ScaleNodePool }) {
  if (!scalable(tab, pool)) {
    return <Count replicas={pool.replicas} className={cn(needsRestore(pool) && "font-medium text-status-warning-fg")} />;
  }
  const { change } = tab.state;
  return (
    <div className="ml-auto">
      <ReplicasStepper
        name={pool.name}
        value={tab.state.valueOf("nodepool", pool.name)}
        onValue={(n) => tab.state.edit("nodepool", pool.name, n)}
        disabled={false}
        changed={change?.mode === "nodepool" && change.target === pool.name}
        inputId={stepperInputId({ mode: "nodepool", target: pool.name })}
        quiet
      />
    </div>
  );
}

const day1Of = (tab: ScaleTabValue, nodepool: string) => tab.options.nodepools.find((p) => p.name === nodepool) ?? null;

/**
 * In a NodePool card's header, beside its ready count: the replicas the
 * day1 file sets, a stepper while they can change. The card is the MCE's
 * NodePool and is matched to the file's by name. For an admin only.
 */
export function CardScaleControl({ nodepool }: { nodepool: string }) {
  const tab = useScaleTab();
  if (!tab?.isAdmin) return null;
  const pool = day1Of(tab, nodepool);
  if (!pool) {
    return (
      <p
        className="max-w-36 text-right text-xs text-muted-foreground"
        title="No nodepool entry of the day1 file renders this NodePool's name, so it is not scaled here."
        data-testid="scale-card-unmatched"
      >
        Not named in the day1 file
      </p>
    );
  }
  if (!scalable(tab, pool)) {
    return (
      <div data-testid="scale-card-control">
        <PoolSize tab={tab} pool={pool} />
      </div>
    );
  }
  return (
    // Centred on the ready count's first line
    <div className="-mt-1.5 flex items-center gap-2" data-testid="scale-card-control">
      <span className="text-xs text-muted-foreground" aria-hidden>
        Replicas
      </span>
      <PoolSize tab={tab} pool={pool} />
    </div>
  );
}

/** Under a NodePool card's header: why its replicas are held (with a restore), and its change waiting to be sent. */
export function CardScaleBelow({ nodepool }: { nodepool: string }) {
  const tab = useScaleTab();
  const pool = tab ? day1Of(tab, nodepool) : null;
  if (!tab || !pool) return null;
  const { change } = tab.state;
  const mine = tab.isAdmin && change?.mode === "nodepool" && change.target === nodepool;
  if (!nodepoolBlock(pool) && !mine) return null;
  return (
    <div className="mx-4 mb-3 space-y-2" data-testid="scale-card-below">
      <Held tab={tab} pool={pool} />
      {mine && <PendingChange tab={tab} nodepool={nodepool} />}
    </div>
  );
}

/**
 * A NodePool sizes row: a NodePool of the day1 file that no card shows
 * (all of them while live status is off). An admin's is a stepper while it
 * can change, else the number; a held one says why.
 */
export function SizeRow({ tab, pool }: { tab: ScaleTabValue; pool: ScaleNodePool }) {
  return (
    <li data-testid={`scale-pool-${pool.index}`} className="group/pool space-y-2 px-4 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-56 space-y-0.5">
          <p className="font-mono text-sm font-medium break-all">{pool.name ?? `nodepool[${pool.index}]`}</p>
          {pool.infra_env && <p className="font-mono text-xs text-muted-foreground break-all">{pool.infra_env}</p>}
          <Held tab={tab} pool={pool} />
        </div>
        <PoolSize tab={tab} pool={pool} />
      </div>
      {tab.isAdmin && pool.name && <PendingChange tab={tab} nodepool={pool.name} />}
    </li>
  );
}
