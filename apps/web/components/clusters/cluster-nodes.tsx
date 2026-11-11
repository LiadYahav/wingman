"use client";

import { useState } from "react";
import {
  CircleCheck, CircleX, ClockAlert, ExternalLink, Info, Loader2, RefreshCw, RotateCcw, Server, Split, TriangleAlert,
  WifiOff, Wrench, type LucideIcon,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { UninstallNodeDialog } from "@/components/clusters/uninstall-node-dialog";
import { humanize, isRunning, useClusterNodes } from "@/lib/nodes";
import { cn, formatDateTime } from "@/lib/utils";
import type { ClusterNode, ClusterNodes as Nodes, NodeHealth, WorkflowRun } from "@/types";

// ── Health and flags ─────────────────────────────────────────────────────────

const HEALTH: Record<NodeHealth, { label: string; dot: string; chip: string }> = {
  HEALTHY: { label: "Healthy", dot: "bg-status-ready", chip: "bg-status-ready/12 text-status-ready-fg ring-status-ready/25" },
  WARNING: { label: "Warning", dot: "bg-status-warning", chip: "bg-status-warning/12 text-status-warning-fg ring-status-warning/25" },
  MAJOR: { label: "Major", dot: "bg-status-error", chip: "bg-status-error/12 text-status-error-fg ring-status-error/25" },
  CRITICAL: {
    label: "Critical",
    dot: "bg-status-error",
    chip: "bg-status-error/20 text-status-error-fg ring-status-error/40 font-semibold",
  },
  // Not a verdict: never shown as healthy
  UNKNOWN: { label: "Unknown", dot: "bg-status-deleting", chip: "bg-status-deleting/12 text-status-deleting-fg ring-status-deleting/25" },
};

/** server-scan's overall verdict; anything it adds later reads as unknown, not healthy. */
function HealthBadge({ health }: { health: NodeHealth }) {
  const tone = HEALTH[health] ?? HEALTH.UNKNOWN;
  return (
    <span
      data-testid="node-health"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
        tone.chip
      )}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", tone.dot)} aria-hidden />
      {HEALTH[health] ? tone.label : humanize(String(health))}
    </span>
  );
}

interface Flag {
  key: "maintenance" | "stale" | "unreachable" | "contested";
  label: string;
  icon: LucideIcon;
  tone: "warning" | "error";
  hint: string;
}

/** What server-scan says about a node beyond its health. Shown only: none of them changes what Wingman offers. */
function flagsOf(node: ClusterNode): Flag[] {
  const flags: Flag[] = [];
  if (node.maintenance) {
    flags.push({ key: "maintenance", label: "Maintenance", icon: Wrench, tone: "warning", hint: "server-scan has this server in maintenance." });
  }
  if (node.stale) {
    flags.push({
      key: "stale",
      label: "Stale",
      icon: ClockAlert,
      tone: "warning",
      hint: `server-scan's facts about this server are out of date${node.last_seen_at ? `; last seen ${formatDateTime(node.last_seen_at)}` : ""}.`,
    });
  }
  if (!node.reachable) {
    flags.push({ key: "unreachable", label: "Unreachable", icon: WifiOff, tone: "error", hint: "server-scan could not reach this server." });
  }
  if (node.contested) {
    flags.push({ key: "contested", label: "Contested", icon: Split, tone: "warning", hint: "Two clusters' jobs claim this server in server-scan." });
  }
  return flags;
}

function NodeFlags({ node }: { node: ClusterNode }) {
  const flags = flagsOf(node);
  if (flags.length === 0) return null;
  return (
    <TooltipProvider>
      {flags.map(({ key, label, icon: Icon, tone, hint }) => (
        <Tooltip key={key}>
          <TooltipTrigger
            data-testid={`node-flag-${key}`}
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium cursor-default outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
              tone === "error" ? "bg-status-error/10 text-status-error-fg" : "bg-status-warning/10 text-status-warning-fg"
            )}
          >
            <Icon className="h-3 w-3" aria-hidden />
            {label}
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">{hint}</TooltipContent>
        </Tooltip>
      ))}
    </TooltipProvider>
  );
}

// ── A node's uninstall run ───────────────────────────────────────────────────

/**
 * The node's newest uninstall run, in the orchestrator's words: a running
 * run names its phase (the workflow's own string, humanized), a failed one
 * its error. Wingman keeps no list of phases.
 */
function RunStatus({ run }: { run: WorkflowRun }) {
  const running = isRunning(run);
  const completed = run.status === "completed";
  return (
    <div
      data-testid="node-uninstall-run"
      role={running ? "status" : undefined}
      className={cn(
        "flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-xs",
        running && "border-status-provisioning/25 bg-status-provisioning/5",
        completed && "border-status-ready/25 bg-status-ready/5",
        !running && !completed && "border-status-error/25 bg-status-error/5"
      )}
    >
      {running ? (
        <Loader2 className="h-3.5 w-3.5 shrink-0 mt-px animate-spin text-status-provisioning-fg" aria-hidden />
      ) : completed ? (
        <CircleCheck className="h-3.5 w-3.5 shrink-0 mt-px text-status-ready-fg" aria-hidden />
      ) : (
        <CircleX className="h-3.5 w-3.5 shrink-0 mt-px text-status-error-fg" aria-hidden />
      )}
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="flex flex-wrap items-baseline gap-x-1.5">
          <span
            className={cn(
              "font-medium",
              running ? "text-status-provisioning-fg" : completed ? "text-status-ready-fg" : "text-status-error-fg"
            )}
          >
            {running ? "Uninstalling" : completed ? "Uninstall completed" : `Uninstall ${humanize(run.status).toLowerCase()}`}
          </span>
          {running && (
            <span className="text-foreground" data-testid="node-uninstall-phase">
              {run.phase ? humanize(run.phase) : "Starting"}
            </span>
          )}
          <span className="font-mono text-[11px] text-muted-foreground break-all">{run.workflow_id}</span>
        </p>
        {run.error && <p className="text-status-error-fg break-words">{run.error}</p>}
      </div>
    </div>
  );
}

// ── The list ─────────────────────────────────────────────────────────────────

/** A run started here and the run the node showed then: until a read shows something else, the start is shown. */
interface Started {
  run: WorkflowRun;
  before: WorkflowRun | null;
}

const sameRun = (a: WorkflowRun | null, b: WorkflowRun | null) =>
  a === b ||
  (a !== null && b !== null && a.workflow_id === b.workflow_id && a.status === b.status && a.phase === b.phase && a.error === b.error);

/**
 * How long a start is shown over a read that does not list it yet: the
 * orchestrator's list may lag a workflow it just started.
 */
const STARTED_GRACE_MS = 60_000;

function NodesSkeleton({ compact }: { compact: boolean }) {
  return (
    <div role="status" aria-label="Reading the nodes" className={cn("space-y-2.5", compact ? "py-1" : "p-4")}>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Skeleton className="h-4 w-72 max-w-[45%]" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 w-28 hidden sm:block" />
          <Skeleton className="h-5 w-16 rounded-full ml-auto" />
        </div>
      ))}
    </div>
  );
}

function Notes({ data, isAdmin }: { data: Nodes; isAdmin: boolean }) {
  const unavailable = isAdmin && !data.uninstall.available;
  if (!data.runs_error && !unavailable) return null;
  return (
    <div className="space-y-1.5">
      {data.runs_error && (
        <p data-testid="nodes-runs-error" className="flex items-start gap-1.5 text-xs text-status-warning-fg">
          <TriangleAlert className="h-3.5 w-3.5 shrink-0 mt-px" aria-hidden />
          <span className="break-words">
            Uninstall runs could not be read, so whether any is running is unknown ({data.runs_error}).
          </span>
        </p>
      )}
      {unavailable && (
        <p data-testid="nodes-uninstall-unavailable" className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <Info className="h-3.5 w-3.5 shrink-0 mt-px" aria-hidden />
          <span className="break-words">
            Uninstall is not available here{data.uninstall.detail ? `: ${data.uninstall.detail}` : "."}
          </span>
        </p>
      )}
    </div>
  );
}

const th = "px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground whitespace-nowrap";

/**
 * The servers server-scan places in a cluster (the API note's §1), each
 * linked to its page in server-scan, with its newest uninstall run. An admin
 * starts the platform's `uninstall-server-from-hc` workflow on one from here
 * (§2); Wingman starts it and shows its run, and the workflow does its own
 * checks, so a contested node keeps its button.
 *
 * Mount it where it is shown: it reads the nodes when mounted. `compact` is
 * the clusters list's expanded row.
 */
export function ClusterNodes({
  name,
  where,
  isAdmin,
  compact = false,
  enabled = true,
}: {
  name: string;
  /** `?site=&mce=`, as the cluster's other calls send it. */
  where: string;
  isAdmin: boolean;
  compact?: boolean;
  enabled?: boolean;
}) {
  const [started, setStarted] = useState<Record<string, Started>>({});
  const [uninstalling, setUninstalling] = useState<{ node: ClusterNode; trigger: HTMLElement } | null>(null);
  const { data: read, error, isPending, isFetching, refetch } = useClusterNodes(name, where, {
    enabled,
    watching: Object.keys(started).length > 0,
  });

  const onStarted = (node: ClusterNode, run: WorkflowRun) => {
    const entry: Started = { run, before: node.uninstall };
    setStarted((prev) => ({ ...prev, [node.id]: entry }));
    setTimeout(
      () =>
        setStarted((prev) => {
          if (prev[node.id] !== entry) return prev;
          const next = { ...prev };
          delete next[node.id];
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

  /** The run to show: a start made here, until a read lists something other than what the node showed before it. */
  const runOf = (node: ClusterNode): WorkflowRun | null => {
    const start = started[node.id];
    return start && sameRun(node.uninstall, start.before) ? start.run : node.uninstall;
  };

  // A failed read is shown above the last list read, if there is one (a poll can fail)
  const failure = error ? (
    <div className="space-y-2" data-testid="cluster-nodes-error">
      <ProblemList error={error} title="The nodes could not be read" />
      <button type="button" onClick={() => refetch()} disabled={isFetching} className={buttonVariants({ variant: "outline", size: "sm" })}>
        <RotateCcw className={cn("h-3.5 w-3.5", isFetching && "animate-spin motion-reduce:animate-none")} aria-hidden />
        Retry
      </button>
    </div>
  ) : null;

  let body: React.ReactNode;
  if (!read) {
    body = failure ? <div className={cn(!compact && "p-4")}>{failure}</div> : <NodesSkeleton compact={compact} />;
  } else if (read.off) {
    return (
      <p
        data-testid="cluster-nodes-off"
        title={read.detail}
        className={cn(
          "flex items-center gap-1.5 text-xs text-muted-foreground",
          !compact && "rounded-xl border border-dashed bg-card/40 px-4 py-3"
        )}
      >
        <Info className="h-3.5 w-3.5 shrink-0" aria-hidden />
        Nodes need server-scan, and this deployment has not configured it.
      </p>
    );
  } else {
    const data = read.data;
    const actions = isAdmin && data.uninstall.available;
    const columns = (compact ? 3 : 4) + (actions ? 1 : 0);
    const notes = Boolean(failure) || Boolean(data.runs_error) || (isAdmin && !data.uninstall.available);
    body = (
      <>
        {notes && (
          <div className={cn("space-y-2", !compact && "border-b px-4 py-3")}>
            {failure}
            <Notes data={data} isAdmin={isAdmin} />
          </div>
        )}
        {data.nodes.length === 0 ? (
          compact ? (
            <p data-testid="cluster-nodes-empty" className="text-xs text-muted-foreground">
              server-scan places no server in this cluster.
            </p>
          ) : (
            <EmptyState
              icon={Server}
              title="server-scan places no server in this cluster"
              description={
                <>
                  A server shows here once server-scan&apos;s jobs place it in{" "}
                  <span className="font-mono">{data.hosted_cluster}</span>.
                </>
              }
              data-testid="cluster-nodes-empty"
            />
          )
        ) : (
          // The list's rows are framed; the tab's card is the frame
          <div className={cn("overflow-x-auto", compact && "rounded-lg border bg-card")}>
            <table className="w-full text-sm [&>tbody+tbody]:border-t">
              <thead>
                <tr className={cn("border-b", compact && "bg-muted/30")}>
                  <th className={cn(th, !compact && "pl-4")}>Node</th>
                  <th className={th}>State</th>
                  <th className={th}>Health</th>
                  {!compact && <th className={th}>Last seen</th>}
                  {actions && (
                    <th className={cn(th, !compact && "pr-4")}>
                      <span className="sr-only">Uninstall</span>
                    </th>
                  )}
                </tr>
              </thead>
              {data.nodes.map((node) => {
                const run = runOf(node);
                const hardware = [node.vendor, node.model].filter(Boolean).join(" ");
                return (
                  <tbody key={node.id} data-testid={`node-${node.name}`} className="transition-colors hover:bg-muted/25">
                    <tr>
                      <td className={cn("px-3 py-2 w-full", !compact && "pl-4")}>
                        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
                          <a
                            href={node.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label={`${node.name}, its server-scan page (opens in a new tab)`}
                            className="group inline-flex items-center gap-1 whitespace-nowrap rounded-sm font-mono text-xs font-medium text-foreground underline-offset-4 outline-none hover:text-primary hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                          >
                            {node.name}
                            <ExternalLink
                              className="h-3 w-3 shrink-0 text-muted-foreground transition-colors group-hover:text-primary"
                              aria-hidden
                            />
                          </a>
                          <NodeFlags node={node} />
                        </div>
                        <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
                          {node.serial && <span className="font-mono" title="Serial number">{node.serial}</span>}
                          {node.serial && hardware && <span aria-hidden>·</span>}
                          {hardware && <span>{hardware}</span>}
                          {!node.serial && !hardware && <span>No serial or hardware reported</span>}
                        </p>
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap text-xs" data-testid="node-state" title={node.state}>
                        {humanize(node.state)}
                      </td>
                      <td className="px-3 py-2">
                        <HealthBadge health={node.health} />
                      </td>
                      {!compact && (
                        <td
                          className={cn(
                            "px-3 py-2 whitespace-nowrap text-xs tabular-nums",
                            node.stale ? "text-status-warning-fg" : "text-muted-foreground"
                          )}
                        >
                          {node.last_seen_at ? formatDateTime(node.last_seen_at) : "—"}
                        </td>
                      )}
                      {actions && (
                        <td className={cn("px-3 py-2 text-right", !compact && "pr-4")}>
                          {!isRunning(run) && (
                            <button
                              type="button"
                              onClick={(e) => setUninstalling({ node, trigger: e.currentTarget })}
                              aria-label={`Uninstall ${node.name}`}
                              className={cn(
                                buttonVariants({ variant: "outline", size: "xs" }),
                                "text-muted-foreground hover:border-destructive/40 hover:bg-destructive/5 hover:text-destructive"
                              )}
                            >
                              Uninstall
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                    {run && (
                      <tr>
                        <td colSpan={columns} className={cn("px-3 pb-2.5 pt-0", !compact && "px-4")}>
                          <RunStatus run={run} />
                        </td>
                      </tr>
                    )}
                  </tbody>
                );
              })}
            </table>
          </div>
        )}
      </>
    );
  }

  const nodes = read && !read.off ? read.data : null;
  const count = nodes ? `${nodes.nodes.length} node${nodes.nodes.length !== 1 ? "s" : ""}` : null;

  return (
    <section
      aria-label={`Nodes of ${name}`}
      aria-busy={isPending && !error}
      data-testid="cluster-nodes"
      className={cn(compact ? "space-y-2" : "rounded-xl border bg-card shadow-sm overflow-hidden")}
    >
      {compact ? (
        <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
          <Server className="h-3.5 w-3.5" aria-hidden />
          <span className="font-medium text-foreground tabular-nums">{count ?? "Nodes"}</span>
          <span>in server-scan</span>
          {nodes && (
            <>
              <span aria-hidden>·</span>
              <span className="font-mono break-all">{nodes.hosted_cluster}</span>
            </>
          )}
        </p>
      ) : (
        <header className="flex items-center justify-between gap-3 border-b bg-muted/30 px-4 py-3">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Server className="h-4 w-4 text-muted-foreground" aria-hidden />
              Nodes
              {nodes && (
                <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground tabular-nums">
                  {nodes.nodes.length}
                  <span className="sr-only"> node{nodes.nodes.length !== 1 ? "s" : ""}</span>
                </span>
              )}
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground break-words">
              The servers server-scan places in this cluster
              {nodes && (
                <>
                  {" "}(<span className="font-mono">{nodes.hosted_cluster}</span>)
                </>
              )}
              . Each name opens the server in server-scan.
            </p>
          </div>
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "shrink-0 text-muted-foreground")}
            aria-label="Refresh nodes"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin motion-reduce:animate-none")} aria-hidden />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </header>
      )}
      {body}
      {uninstalling && (
        <UninstallNodeDialog
          cluster={name}
          where={where}
          node={uninstalling.node}
          onClose={closeDialog}
          onStarted={onStarted}
        />
      )}
    </section>
  );
}
