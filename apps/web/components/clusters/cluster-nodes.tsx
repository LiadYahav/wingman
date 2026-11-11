"use client";

import { useState } from "react";
import { Info, Layers, RefreshCw, RotateCcw, TriangleAlert } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { NodePoolCard, UnassignedServers, type NodeActions } from "@/components/clusters/node-pools";
import { UninstallNodeDialog, type UninstallTarget } from "@/components/clusters/uninstall-node-dialog";
import { useClusterNodes } from "@/lib/nodes";
import { cn } from "@/lib/utils";
import type { ClusterNodes as Nodes, ServerRecord, WorkflowRun } from "@/types";

/** A run started here and the run the server showed then: until a read shows something else, the start is shown. */
interface Started {
  run: WorkflowRun;
  before: WorkflowRun | null;
}

const sameRun = (a: WorkflowRun | null, b: WorkflowRun | null) =>
  a === b ||
  (a !== null && b !== null && a.workflow_id === b.workflow_id && a.status === b.status && a.phase === b.phase && a.error === b.error);

/**
 * How long a start is shown over a read that does not list it yet: the
 * orchestrator's list may lag a workflow it just started, and a re-run has
 * the same workflow id as the run before it.
 */
const STARTED_GRACE_MS = 60_000;

/** The server's newest run as the page read it, wherever the server is. */
function fetchedRunOf(data: Nodes, serverId: string): WorkflowRun | null {
  for (const pool of data.node_pools) {
    for (const node of pool.nodes) if (node.server?.id === serverId) return node.uninstall;
  }
  return data.unassigned.find((s) => s.id === serverId)?.uninstall ?? null;
}

function NodesSkeleton() {
  return (
    <div role="status" aria-label="Reading the nodes" className="overflow-hidden rounded-xl border bg-card shadow-sm">
      <div className="flex items-start justify-between gap-6 px-4 pb-3 pt-3.5">
        <div className="space-y-2">
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-3 w-40" />
        </div>
        <Skeleton className="h-5 w-20" />
      </div>
      <div className="divide-y border-t">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-4 py-3.5">
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-72 max-w-[60%]" />
              <Skeleton className="h-3 w-48 max-w-[40%]" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="hidden h-5 w-16 rounded-full sm:block" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** What is unknown or unavailable on this read: said once, above the pools. */
function Notes({ data, isAdmin }: { data: Nodes; isAdmin: boolean }) {
  const unavailable = isAdmin && !data.uninstall.available;
  if (!data.server_scan_error && !data.runs_error && !unavailable) return null;
  return (
    <div className="space-y-1.5">
      {data.server_scan_error && (
        <p data-testid="nodes-server-scan-error" className="flex items-start gap-1.5 text-xs text-status-warning-fg">
          <TriangleAlert className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="break-words">
            server-scan could not be read, so server links and health are unavailable ({data.server_scan_error}).
          </span>
        </p>
      )}
      {data.runs_error && (
        <p data-testid="nodes-runs-error" className="flex items-start gap-1.5 text-xs text-status-warning-fg">
          <TriangleAlert className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="break-words">
            Uninstall runs could not be read, so whether any is running is unknown ({data.runs_error}).
          </span>
        </p>
      )}
      {unavailable && (
        <p data-testid="nodes-uninstall-unavailable" className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <Info className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="break-words">
            Uninstall is not available here{data.uninstall.detail ? `: ${data.uninstall.detail}` : "."}
          </span>
        </p>
      )}
    </div>
  );
}

/**
 * The cluster page's Nodes tab (the API note's §1): one card per NodePool,
 * as the MCE reports it, with server-scan's link and health for each server,
 * then the servers server-scan places in the cluster that no Machine has.
 * An admin starts the platform's `uninstall-server-from-hc` workflow on a
 * server from here (§2); Wingman starts it and shows its run, and the
 * workflow does its own checks, so a contested server keeps its button.
 *
 * Mount it where it is shown: it reads the nodes when mounted.
 */
export function ClusterNodes({
  name,
  where,
  isAdmin,
  enabled = true,
}: {
  name: string;
  /** `?site=&mce=`, as the cluster's other calls send it. */
  where: string;
  isAdmin: boolean;
  enabled?: boolean;
}) {
  const [started, setStarted] = useState<Record<string, Started>>({});
  const [uninstalling, setUninstalling] = useState<{ target: UninstallTarget; trigger: HTMLElement } | null>(null);
  const { data: read, error, isPending, isFetching, refetch } = useClusterNodes(name, where, {
    enabled,
    watching: Object.keys(started).length > 0,
  });

  const onStarted = (server: ServerRecord, run: WorkflowRun) => {
    const before = read && !read.off ? fetchedRunOf(read.data, server.id) : null;
    const entry: Started = { run, before };
    setStarted((prev) => ({ ...prev, [server.id]: entry }));
    setTimeout(
      () =>
        setStarted((prev) => {
          if (prev[server.id] !== entry) return prev;
          const next = { ...prev };
          delete next[server.id];
          return next;
        }),
      STARTED_GRACE_MS
    );
  };

  const closeDialog = () => {
    const trigger = uninstalling?.trigger;
    setUninstalling(null);
    // Back to the button that opened it; once a run is shown the button is gone
    requestAnimationFrame(() => {
      if (trigger?.isConnected) trigger.focus();
    });
  };

  const failure = error ? (
    <div className="space-y-2" data-testid="cluster-nodes-error">
      <ProblemList error={error} title="The nodes could not be read" />
      <button type="button" onClick={() => refetch()} disabled={isFetching} className={buttonVariants({ variant: "outline", size: "sm" })}>
        <RotateCcw className={cn("h-3.5 w-3.5", isFetching && "animate-spin motion-reduce:animate-none")} aria-hidden />
        Retry
      </button>
    </div>
  ) : null;

  if (read?.off) {
    return (
      <p
        data-testid="cluster-nodes-off"
        title={read.detail}
        className="flex items-center gap-1.5 rounded-xl border border-dashed bg-card/40 px-4 py-3 text-xs text-muted-foreground"
      >
        <Info className="h-3.5 w-3.5 shrink-0" aria-hidden />
        Nodes need live status from the MCE (CLUSTER_STATUS_ENABLED).
      </p>
    );
  }

  const data = read?.data;
  const actions: NodeActions = {
    runOf: (serverId, fetched) => {
      const start = serverId ? started[serverId] : undefined;
      return start && sameRun(fetched, start.before) ? start.run : fetched;
    },
    canUninstall: isAdmin && Boolean(data?.uninstall.available),
    onUninstall: (target, trigger) => setUninstalling({ target, trigger }),
  };
  const pools = data?.node_pools.length ?? 0;
  const nodes = data?.node_pools.reduce((n, p) => n + p.nodes.filter((x) => x.state !== "missing").length, 0) ?? 0;

  return (
    <section aria-label={`Nodes of ${name}`} aria-busy={isPending && !error} data-testid="cluster-nodes" className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">Nodes</h2>
          <p className="mt-0.5 text-xs text-muted-foreground break-words">
            {data ? (
              <>
                {pools} NodePool{pools !== 1 ? "s" : ""} · {nodes} Machine{nodes !== 1 ? "s" : ""}, as the MCE reports them for{" "}
                <span className="font-mono">{data.hosted_cluster}</span>; each server&apos;s name opens it in server-scan.
              </>
            ) : (
              "Each NodePool's Machines, as the MCE reports them, with the server behind each."
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching || !enabled}
          className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "shrink-0 text-muted-foreground")}
          aria-label="Refresh nodes"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin motion-reduce:animate-none")} aria-hidden />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      {failure}

      {!data ? (
        !failure && <NodesSkeleton />
      ) : (
        <>
          <Notes data={data} isAdmin={isAdmin} />
          {data.node_pools.length === 0 && data.unassigned.length === 0 ? (
            <EmptyState
              icon={Layers}
              title="The MCE lists no NodePool for this cluster"
              description="NodePools show here once the MCE has them, with their Machines and servers."
              bordered
              data-testid="cluster-nodes-empty"
            />
          ) : (
            <>
              {data.node_pools.map((pool) => (
                <NodePoolCard key={pool.name} pool={pool} actions={actions} />
              ))}
              <UnassignedServers servers={data.unassigned} actions={actions} />
            </>
          )}
        </>
      )}

      {uninstalling && (
        <UninstallNodeDialog
          cluster={name}
          where={where}
          target={uninstalling.target}
          onClose={closeDialog}
          onStarted={onStarted}
        />
      )}
    </section>
  );
}
