"use client";

import { Network, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Rebooting } from "@/types";

/** One part of the sync preview: a titled box, quiet or a warning. */
export function SyncSection({
  title,
  icon: Icon,
  tone = "neutral",
  children,
  testId,
}: {
  title: string;
  icon?: typeof Network;
  tone?: "neutral" | "warning";
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <section
      data-testid={testId}
      aria-label={title}
      className={cn(
        "rounded-lg border p-3.5 space-y-2",
        tone === "warning" ? "border-status-warning/30 bg-status-warning/5" : "bg-muted/20"
      )}
    >
      <h3
        className={cn(
          "flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide",
          tone === "warning" ? "text-status-warning-fg" : "text-muted-foreground"
        )}
      >
        {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
        {title}
      </h3>
      {children}
    </section>
  );
}

/** `2 nodes`, `25% of the nodes`: an `inPlace.maxUnavailable` as a count. */
function atATime(maxUnavailable: number | string): string {
  const n = typeof maxUnavailable === "number" ? maxUnavailable : /^\d+$/.test(maxUnavailable) ? Number(maxUnavailable) : null;
  if (n !== null) return `${n} node${n === 1 ? "" : "s"}`;
  return `${maxUnavailable} of the nodes`;
}

/**
 * How merging a sync rolls a nodepool's nodes (ADR-0037): drained and
 * rebooted in place, one at a time or `inPlace.maxUnavailable` at a time
 * (the chart's default `upgradeType` is `InPlace`), or replaced.
 */
export function rollText(r: Pick<Rebooting, "replicas" | "max_unavailable" | "replaces_nodes">): string {
  const nodes = r.replicas === null ? "Its nodes" : `Its ${r.replicas} node${r.replicas === 1 ? "" : "s"}`;
  const are = r.replicas === 1 ? "is" : "are";
  if (r.replaces_nodes) {
    return `${nodes} ${are} replaced with new nodes (upgradeType: Replace): new nodes come up with the new configs, then the old ones are removed.`;
  }
  if (r.max_unavailable === null || r.max_unavailable === "") {
    return `${nodes} ${are} drained and rebooted in place, one node at a time.`;
  }
  return `${nodes} ${are} drained and rebooted in place, ${atATime(r.max_unavailable)} at a time (inPlace.maxUnavailable).`;
}

/** Configs changed, or a day1 that predates the flags (every rolling nodepool was a configs change then). */
const configsChange = (r: Rebooting) => r.configs !== false && (r.configs === true || !r.tuning);

/**
 * The nodepools a sync's merge rolls or may reboot: changed machine configs
 * roll the nodes (ADR-0037); changed tuning profiles may reboot them, since a
 * PerformanceProfile or kernel arguments need one (ADR-0061).
 */
export function SyncRolling({ rebooting }: { rebooting: Rebooting[] }) {
  if (rebooting.length === 0) return null;
  const tuning = rebooting.some((r) => r.tuning);
  return (
    <SyncSection title="Merging rolls these nodes" icon={RotateCw} tone="warning" testId="sync-rolling">
      <p className="text-xs text-muted-foreground">
        OpenShift applies changed machine configs by rolling a nodepool&apos;s nodes.
        {tuning && " Changed tuning profiles can reboot them too (a PerformanceProfile, kernel arguments)."}
      </p>
      <ul className="space-y-1.5 text-sm">
        {rebooting.map((r) => (
          <li key={r.nodepool.index} data-testid={`sync-roll-${r.nodepool.index}`}>
            <span className="font-medium break-all">{r.nodepool.name}</span>
            <span className="text-muted-foreground"> (nodepool[{r.nodepool.index}])</span>
            {configsChange(r) && <p>{rollText(r)}</p>}
            {r.tuning && (
              <p data-testid={`sync-tuning-${r.nodepool.index}`}>Its tuning profiles change: its nodes may reboot.</p>
            )}
          </li>
        ))}
      </ul>
      <p className="text-sm font-medium">
        Nothing rolls until the MR is merged: merging is what starts it. Merge it in a window the
        cluster&apos;s owners accept.
      </p>
    </SyncSection>
  );
}

/** Beside the sync button: the nodepools whose tuning profiles change, named once more before the MR opens. */
export function TuningRebootNote({ rebooting }: { rebooting: Rebooting[] }) {
  const pools = rebooting.filter((r) => r.tuning).map((r) => r.nodepool.name);
  if (pools.length === 0) return null;
  return (
    <p className="text-xs text-status-warning-fg sm:mr-auto break-words" data-testid="sync-tuning-confirm">
      Tuning profiles change on {pools.join(", ")}: their nodes may reboot when the MR merges.
    </p>
  );
}
