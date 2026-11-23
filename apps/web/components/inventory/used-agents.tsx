"use client";

import Link from "next/link";
import { Info, TriangleAlert } from "lucide-react";
import { Hint } from "@/components/common/hint";
import { clusterHref } from "@/lib/clusters";
import { byCluster, showUnguarded, unguardedHint, unguardedSummary, usedHint } from "@/lib/inventory/used";
import type { MceInventory, UsedLabels } from "@/types/inventory";

/**
 * A used count, `2 used`, with which servers and why in its tooltip: herzi's
 * used Agents are free again but never available (ADR-0057's 3.55.0 amendment).
 */
export function UsedCount({
  labels,
  count,
  servers = [],
  paused = false,
  testId,
  big = false,
}: {
  labels: UsedLabels;
  count: number;
  servers?: string[];
  /** herzi paused the pool: it removes none of them until resumed. */
  paused?: boolean;
  testId: string;
  big?: boolean;
}) {
  if (count <= 0) return null;
  return (
    <Hint hint={usedHint(labels, servers, paused)} label={`${count} used, waiting for herzi to remove: why`} testId={testId}>
      <span className="text-status-warning-fg">
        {big ? <span className="font-semibold tabular-nums">{count}</span> : count} used
      </span>
    </Hint>
  );
}

/** Why the MCE's used Agents are unknown, when their read failed. */
export function UsedUnread({ mce }: { mce: MceInventory }) {
  if (mce.used !== null || !mce.used_error) return null;
  return (
    <p className="mt-1 text-xs text-muted-foreground" data-testid="mce-used-unread">
      Used Agents not read: {mce.used_error}
    </p>
  );
}

/**
 * The MCE's agent NodePools, from its cluster files, that do not exclude the
 * used-Agent label: herzi holds every removal until they do, and they may
 * bind a used Agent meanwhile. Shown once it matters (the deployment excludes
 * the label, or herzi has used Agents here), each cluster linked to its page.
 */
export function UnguardedNotice({ mce, labels }: { mce: MceInventory; labels: UsedLabels }) {
  if (!showUnguarded(mce, labels)) return null;
  return (
    <details className="mt-2 rounded-lg border border-status-warning/30 bg-status-warning/5 px-3 py-2 text-xs" data-testid="mce-unguarded">
      <summary className="flex cursor-pointer items-center gap-1.5 text-status-warning-fg">
        <TriangleAlert aria-hidden className="h-3.5 w-3.5 shrink-0" />
        <span>{unguardedSummary(mce, labels)}</span>
        <Hint hint={unguardedHint(labels)} label="Why the exclusion matters">
          <Info aria-hidden className="h-3 w-3" />
        </Hint>
      </summary>
      <ul className="mt-1.5 space-y-0.5 pl-5">
        {byCluster(mce.unguarded).map(({ cluster, nodepools }) => (
          <li key={cluster} data-testid="unguarded-cluster">
            <Link
              href={clusterHref({ name: cluster, site: mce.site, mce: mce.mce })}
              className="font-mono underline decoration-dotted underline-offset-4 hover:decoration-solid"
            >
              {cluster}
            </Link>
            <span className="text-muted-foreground">
              {": "}
              {nodepools.map((pool) => (pool.replace ? `${pool.nodepool} (Replace: change it to InPlace first)` : pool.nodepool)).join(", ")}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}
