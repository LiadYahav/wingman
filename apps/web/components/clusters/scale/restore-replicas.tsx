"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowRight, Loader2, Scaling, Undo2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { ProblemList } from "@/components/common/problem-list";
import { SyncSection } from "@/components/clusters/sync-rolling";
import { useScaleBusy, useStartScale } from "@/lib/scale";
import { fromTo, refusalTitle } from "@/lib/scale-model";
import { cn } from "@/lib/utils";
import type { HeldReplicas } from "@/types";
import { ScaleTruths } from "./scale-truths";

/**
 * "Restore with update-nodepool": one NodePool set back to the replicas its
 * flavor locks, by name (ADR-0062). The button opens a confirmation in place
 * that says what the run does; Start sends it once, never retried. It waits,
 * with why, while a run of the cluster (update-nodepool's or
 * upgrade-cluster's) is going: one at a time, nothing queued.
 */
export function RestoreReplicas({
  name,
  where,
  nodepool,
  current,
  target,
  runShows = "on the cluster's Nodes tab",
  busyId,
}: {
  name: string;
  where: string;
  nodepool: string;
  current: number | null;
  target: number;
  /** Where its run shows, said once it started. */
  runShows?: string;
  /** Where the page already says why it waits: the button points there and says it no second time. */
  busyId?: string;
}) {
  const [confirming, setConfirming] = useState(false);
  const [started, setStarted] = useState<string | null>(null);
  const busy = useScaleBusy(name, where);
  const start = useStartScale(name, where);
  const label = `Restore ${nodepool} to ${target} replicas with update-nodepool`;

  if (started) {
    return (
      <p role="status" data-testid="restore-started" className="flex flex-wrap items-center gap-x-1.5 text-xs text-status-provisioning-fg">
        <Scaling className="h-3.5 w-3.5 shrink-0" aria-hidden />
        <span className="break-all">
          update-nodepool started ({started}): its run shows {runShows}.
        </span>
      </p>
    );
  }

  if (!confirming) {
    return (
      <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
        <button
          type="button"
          data-testid="restore-replicas"
          onClick={() => setConfirming(true)}
          disabled={busy !== null}
          aria-label={label}
          aria-describedby={busy ? (busyId ?? `restore-busy-${nodepool}`) : undefined}
          className={buttonVariants({ variant: "outline", size: "xs" })}
        >
          <Undo2 aria-hidden />
          Restore to {target}
        </button>
        {busy && !busyId && (
          <span id={`restore-busy-${nodepool}`} className="text-xs text-muted-foreground" data-testid="restore-busy">
            {busy}
          </span>
        )}
      </span>
    );
  }

  const submit = () =>
    start.mutate(
      { nodepool, replicas: target },
      {
        onSuccess: (run) => {
          toast.success("update-nodepool started", { description: `${nodepool}: ${fromTo(current, target)} replicas` });
          setStarted(run.workflow_id);
        },
      }
    );

  return (
    <div
      role="group"
      aria-label={`Restore ${nodepool}`}
      data-testid="restore-confirm"
      className="mt-1 w-full space-y-2.5 rounded-lg border bg-background px-3 py-2.5"
    >
      <p className="text-sm">
        Set NodePool <span className="font-mono font-medium break-all">{nodepool}</span> from{" "}
        <span className="tabular-nums">{fromTo(current, target)}</span> replicas, the value its flavor locks?
      </p>
      <ScaleTruths down={current !== null && target < current} compact />
      {Boolean(start.error) && (
        <div data-testid="restore-error">
          <ProblemList error={start.error} title={refusalTitle(start.error)} />
        </div>
      )}
      <div className="flex flex-wrap items-center justify-end gap-2">
        {busy && <span className="mr-auto text-xs text-muted-foreground">{busy}</span>}
        <button type="button" onClick={() => { start.reset(); setConfirming(false); }} disabled={start.isPending} className={buttonVariants({ variant: "outline", size: "sm" })}>
          Cancel
        </button>
        <button
          type="button"
          data-testid="restore-start"
          onClick={submit}
          disabled={start.isPending || busy !== null || Boolean(start.error)}
          className={buttonVariants({ size: "sm" })}
        >
          {start.isPending && <Loader2 className="animate-spin" aria-hidden />}
          {start.isPending ? "Starting…" : "Start update-nodepool"}
        </button>
      </div>
    </div>
  );
}

/**
 * The sync's NodePools whose locked replicas its MR leaves out (ADR-0062):
 * with scaling on, replicas change only through update-nodepool, so each one
 * is restored by its own run. Nothing when there are none (scaling off).
 */
export function SyncHeldReplicas({ name, where, held }: { name: string; where: string; held: HeldReplicas[] | undefined }) {
  if (!held || held.length === 0) return null;
  return (
    <SyncSection title="Not in this merge request: NodePool replicas" icon={Scaling} testId="sync-held-replicas">
      <p className="text-xs text-muted-foreground">
        NodePool replicas change only through update-nodepool. The flavor locks these, and the file holds other values:
        restore each one with its own run, one at a time.
      </p>
      <ul className="space-y-2">
        {held.map((h) => (
          <li key={h.index} data-testid={`sync-held-${h.index}`} className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5 text-sm">
            <span className="min-w-0 break-words">
              NodePool <span className="font-mono font-medium break-all">{h.name ?? `nodepool[${h.index}]`}</span>{" "}
              <span className="tabular-nums text-muted-foreground">{fromTo(h.replicas, h.flavor_replicas)}</span>
            </span>
            {h.name ? (
              <RestoreReplicas name={name} where={where} nodepool={h.name} current={h.replicas} target={h.flavor_replicas} />
            ) : (
              <span className="text-xs text-muted-foreground">It cannot be named from the day1 file, so it cannot be restored by name.</span>
            )}
          </li>
        ))}
      </ul>
    </SyncSection>
  );
}

/**
 * A rollout's cluster whose MR leaves locked replicas out: what is left, and
 * where it is restored (the cluster's Nodes tab, an admin's: `nodesHref` only
 * for them, ADR-0038). No run is read here.
 */
export function HeldReplicasLinks({ held, nodesHref, className }: { held: HeldReplicas[] | undefined; nodesHref?: string; className?: string }) {
  if (!held || held.length === 0) return null;
  return (
    <div className={cn("space-y-0.5 text-xs", className)} data-testid="held-replicas">
      <p className="text-muted-foreground">
        Not in its merge request, restored with update-nodepool:{" "}
        {held.map((h, i) => (
          <span key={h.index}>
            {i > 0 && ", "}
            <span className="font-mono break-all text-foreground">{h.name ?? `nodepool[${h.index}]`}</span>{" "}
            <span className="tabular-nums">{fromTo(h.replicas, h.flavor_replicas)}</span>
          </span>
        ))}
        .
      </p>
      {nodesHref && (
        <Link href={nodesHref} className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline">
          Restore on its Nodes tab
          <ArrowRight className="h-3 w-3" aria-hidden />
        </Link>
      )}
    </div>
  );
}
