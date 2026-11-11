"use client";

import { ArrowRight, CircleDashed, ExternalLink, Loader2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { HealthBadge, NodeStateChip } from "@/components/clusters/node-badges";
import type { NodesRead } from "@/lib/nodes";
import { cn } from "@/lib/utils";
import type { NodePoolNodes, PoolNode } from "@/types";

/**
 * A NodePool of the cluster file, opened on the Overview: its nodes as the MCE
 * reports them, each one linking to its server in server-scan. The Nodes tab
 * has the full board (activity, problems, uninstall); this is the quick look.
 */

/** The MCE's NodePool for a file's nodepool: by its name, which the chart derives as `<clusterName>-<infraEnv>`. */
export function matchPool(
  pools: NodePoolNodes[],
  { name, infraEnv, clusterName }: { name: string | null; infraEnv: string | null; clusterName: string }
): NodePoolNodes | null {
  const expected = name ?? (infraEnv ? `${clusterName}-${infraEnv}` : null);
  const byName = expected ? pools.find((p) => p.name === expected) : undefined;
  if (byName) return byName;
  // An explicit name the MCE renamed is rare; the InfraEnv in the selector still finds the pool
  if (!infraEnv) return null;
  const bySelector = pools.filter((p) => p.agent_selector?.endsWith(`=${infraEnv}`));
  return bySelector.length === 1 ? bySelector[0] : null;
}

function NodeRow({ node }: { node: PoolNode }) {
  const server = node.server;
  const label = server?.name ?? node.server_name ?? node.machine ?? "A node";
  const gap = node.state === "waiting" || node.state === "missing";
  const body = (
    <>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          {gap && <CircleDashed className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />}
          <span className={cn("truncate font-mono text-xs", gap ? "text-muted-foreground" : "font-medium text-foreground")}>
            {gap ? (node.state === "missing" ? "A node is missing" : "Waiting for a server") : label}
          </span>
          {server && (
            <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" aria-hidden />
          )}
        </span>
        {gap && node.waiting_for ? (
          <span className="mt-0.5 block text-xs text-muted-foreground">{node.waiting_for}</span>
        ) : server ? (
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
            {[server.serial, [server.vendor, server.model].filter(Boolean).join(" ")].filter(Boolean).join(" · ")}
          </span>
        ) : null}
        {node.current && node.activity && (
          <span className="mt-0.5 block text-xs text-status-provisioning-fg">{node.activity}</span>
        )}
      </span>
      <span className="flex shrink-0 items-center gap-3">
        <NodeStateChip state={node.state} />
        {server && <HealthBadge health={server.health} />}
      </span>
    </>
  );
  const row = cn(
    "flex items-center gap-3 px-3 py-2",
    node.current && "border-l-2 border-l-status-provisioning bg-status-provisioning/5",
    gap && "border border-dashed border-border/80 rounded-md my-1"
  );
  if (!server) {
    return (
      <li data-testid="pool-node" className={row}>
        {body}
      </li>
    );
  }
  return (
    <li data-testid="pool-node">
      <a
        href={server.url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`${server.name}: open in server-scan (new tab)`}
        className={cn(row, "group outline-none transition-colors hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50")}
      >
        {body}
      </a>
    </li>
  );
}

export function PoolNodesInline({
  read,
  isPending,
  error,
  onRetry,
  pool,
  poolName,
  onOpenNodesTab,
}: {
  read: NodesRead | undefined;
  isPending: boolean;
  error: unknown;
  onRetry: () => void;
  pool: NodePoolNodes | null;
  /** The name the file's nodepool should have on the MCE, for the "not reported" note. */
  poolName: string | null;
  onOpenNodesTab?: () => void;
}) {
  let content: React.ReactNode;
  if (isPending) {
    content = (
      <div className="space-y-2 px-3 py-2" aria-busy>
        <Skeleton className="h-4 w-72" />
        <Skeleton className="h-4 w-60" />
      </div>
    );
  } else if (error) {
    content = (
      <div className="px-3 py-2">
        <ProblemList error={error} title="The nodes could not be read" />
        <button type="button" onClick={onRetry} className="mt-1 text-xs text-primary hover:underline">
          Try again
        </button>
      </div>
    );
  } else if (read?.off) {
    content = <p className="px-3 py-2 text-xs text-muted-foreground">Nodes need live status from the MCE (CLUSTER_STATUS_ENABLED).</p>;
  } else if (!pool) {
    content = (
      <p className="px-3 py-2 text-xs text-muted-foreground">
        The MCE reports no NodePool {poolName ? <span className="font-mono">{poolName}</span> : "for this nodepool"} yet.
      </p>
    );
  } else {
    content = (
      <>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 pt-2 text-xs text-muted-foreground">
          <span>
            <span className="font-medium text-foreground tabular-nums">{pool.ready}</span>
            {pool.wanted !== null ? ` / ${pool.wanted}` : ""} ready
          </span>
          {pool.update && (
            <span className={pool.update.failed ? "text-status-error-fg" : "text-status-provisioning-fg"}>
              {pool.update.failed ? "Update failed" : `Updating ${pool.update.kind === "machine_template" ? "machines" : pool.update.kind}`}
              {pool.update.progress && ` · ${pool.update.progress.updated} of ${pool.update.progress.total} updated`}
            </span>
          )}
        </p>
        {pool.nodes.length === 0 ? (
          <p className="px-3 py-2 text-xs text-muted-foreground">No Machines in this NodePool.</p>
        ) : (
          <ul className="divide-y divide-border/60 py-1" aria-label={`Nodes of ${pool.name}`}>
            {pool.nodes.map((node, i) => (
              <NodeRow key={node.machine ?? `missing-${i}`} node={node} />
            ))}
          </ul>
        )}
      </>
    );
  }
  return (
    <div data-testid="pool-nodes-inline" className="rounded-md border bg-background/60">
      {content}
      {onOpenNodesTab && (
        <div className="border-t px-3 py-1.5 text-right">
          <button
            type="button"
            onClick={onOpenNodesTab}
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            Details and uninstall in the Nodes tab <ArrowRight className="h-3 w-3" aria-hidden />
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * A NodePool's live state in a row of the Nodepools card: ready of wanted,
 * then an update rolling through it (in progress, not a problem), a failed
 * update, or what is not well.
 */
export function PoolLiveState({ pool, loading, known }: { pool: NodePoolNodes | null; loading: boolean; known: boolean }) {
  if (loading) return <Skeleton className="h-3.5 w-24" />;
  if (!known) return <span className="text-muted-foreground">—</span>;
  if (!pool) return <span className="text-muted-foreground">Not on the MCE</span>;
  const short = pool.wanted !== null && pool.ready < pool.wanted;
  const update = pool.update;
  return (
    <span data-testid="nodepool-live" className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 whitespace-nowrap">
      <span className="tabular-nums">
        <span className={cn("font-medium", short ? "text-status-warning-fg" : "text-foreground")}>{pool.ready}</span>
        <span className="text-muted-foreground">{pool.wanted !== null ? ` / ${pool.wanted}` : ""} ready</span>
      </span>
      {update ? (
        update.failed ? (
          <span className="inline-flex items-center gap-1 text-status-error-fg">Update failed</span>
        ) : (
          <span className="inline-flex items-center gap-1 text-status-provisioning-fg">
            <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-hidden />
            Updating {update.kind === "machine_template" ? "machines" : update.kind}
            {update.progress ? ` · ${update.progress.updated} of ${update.progress.total}` : ""}
          </span>
        )
      ) : pool.problems.length > 0 ? (
        <span className="text-status-warning-fg" title={pool.problems.join("\n")}>
          {pool.problems.length} problem{pool.problems.length === 1 ? "" : "s"}
        </span>
      ) : null}
    </span>
  );
}
