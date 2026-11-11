"use client";

import { useState } from "react";
import { CircleDashed, CircleX, ExternalLink, Layers, Loader2, ServerOff, TriangleAlert } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { HealthBadge, NodeFlags, NodeStateChip, RunStatus, ServerStateText } from "@/components/clusters/node-badges";
import type { UninstallTarget } from "@/components/clusters/uninstall-node-dialog";
import { humanize, isRunning } from "@/lib/nodes";
import { cn } from "@/lib/utils";
import type { NodePoolNodes, NodePoolUpdate, PoolNode, ServerRecord, UnassignedServer, WorkflowRun } from "@/types";

/** What a row needs from the tab: the run to show, and whether and how to start an uninstall. */
export interface NodeActions {
  /** The run to show for a server: a start made here wins until a read lists something else. */
  runOf: (serverId: string | null, fetched: WorkflowRun | null) => WorkflowRun | null;
  /** An admin, in a deployment that can start an uninstall. */
  canUninstall: boolean;
  onUninstall: (target: UninstallTarget, trigger: HTMLElement) => void;
}

// ── A row ────────────────────────────────────────────────────────────────────

/** The state, health and action slots have fixed widths, so they line up down a pool and across pools. */
const SLOTS = "sm:grid-cols-[0.5rem_minmax(0,1fr)_6.5rem_6rem_5.5rem]";

/** A server's name: its page in server-scan, in a new tab. */
function ServerLink({ server }: { server: ServerRecord }) {
  return (
    <a
      href={server.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${server.name}, its server-scan page (opens in a new tab)`}
      className="group inline-flex items-center gap-1 whitespace-nowrap rounded-sm font-mono text-xs font-medium text-foreground underline-offset-4 outline-none hover:text-primary hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {server.name}
      <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" aria-hidden />
    </a>
  );
}

function UninstallButton({ target, actions }: { target: UninstallTarget; actions: NodeActions }) {
  return (
    <button
      type="button"
      onClick={(e) => actions.onUninstall(target, e.currentTarget)}
      aria-label={`Uninstall ${target.server.name}`}
      className={cn(
        buttonVariants({ variant: "outline", size: "xs" }),
        "text-muted-foreground hover:border-destructive/40 hover:bg-destructive/5 hover:text-destructive"
      )}
    >
      Uninstall
    </button>
  );
}

/**
 * "a · b · c". Each part carries its "·" in its left padding, and the line is
 * shifted left inside a clipping box, so a part that wraps to the start of a
 * line loses its dot: no line starts with a separator.
 */
function Meta({ parts }: { parts: React.ReactNode[] }) {
  const shown = parts.filter(Boolean);
  if (shown.length === 0) return null;
  return (
    <div className="mt-0.5 overflow-hidden">
      <p className="-ml-3.5 flex flex-wrap items-baseline gap-y-0.5 text-xs text-muted-foreground">
        {shown.map((part, i) => (
          <span
            key={i}
            className="relative min-w-0 pl-3.5 before:absolute before:left-[0.3rem] before:text-muted-foreground/50 before:content-['·']"
          >
            {part}
          </span>
        ))}
      </p>
    </div>
  );
}

/** A labelled value of the meta line: "Machine prod-…-x7k2p". */
function Labelled({ label, children, mono = false }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <span className="min-w-0 break-words">
      <span className="text-muted-foreground/70">{label} </span>
      <span className={cn(mono && "font-mono")}>{children}</span>
    </span>
  );
}

/**
 * One row of the board. The node being worked on carries an accent bar, a
 * tint and a slow pulse, and says what is happening to it; a failed one is
 * marked in the error tone; every other row stays quiet.
 */
function Row({
  testId,
  title,
  flags,
  meta,
  activity,
  emphasis,
  state,
  health,
  action,
  run,
}: {
  testId: string;
  title: React.ReactNode;
  flags?: React.ReactNode;
  meta: React.ReactNode[];
  activity: string | null;
  emphasis: "current" | "failed" | null;
  state: React.ReactNode;
  health: React.ReactNode;
  action: React.ReactNode;
  run: WorkflowRun | null;
}) {
  const current = emphasis === "current";
  const failed = emphasis === "failed";
  return (
    <li
      data-testid={testId}
      data-current={current || undefined}
      className={cn(
        "relative grid grid-cols-[0.5rem_minmax(0,1fr)] gap-x-3 px-4 py-3",
        SLOTS,
        current && "bg-status-provisioning/[0.06]",
        failed && "bg-status-error/[0.04]"
      )}
    >
      {emphasis && (
        <span
          aria-hidden
          className={cn("absolute inset-y-0 left-0 w-[3px]", current ? "bg-status-provisioning" : "bg-status-error")}
        />
      )}
      {/* The indicator: a slow pulse on the node being worked on */}
      <span className="mt-1.5 flex h-2 w-2" aria-hidden>
        {current && (
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-status-provisioning opacity-50 animate-ping [animation-duration:2s] motion-reduce:animate-none" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-status-provisioning" />
          </span>
        )}
        {failed && <span className="inline-flex h-2 w-2 rounded-full bg-status-error" />}
      </span>

      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
          {title}
          {current && <span className="sr-only">(being worked on now)</span>}
          {flags}
        </div>
        <Meta parts={meta} />
        {activity && (
          <p
            data-testid="node-activity"
            className={cn(
              "mt-1 text-xs break-words",
              current ? "font-medium text-status-provisioning-fg" : failed ? "text-status-error-fg" : "text-muted-foreground"
            )}
          >
            {activity}
          </p>
        )}
      </div>

      {/* State, health and the action: below the name on a phone, in fixed slots beside it otherwise */}
      <div className="col-start-2 mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 sm:contents">
        <div className="sm:col-start-3 sm:row-start-1 sm:pt-0.5">{state}</div>
        <div className="sm:col-start-4 sm:row-start-1 sm:pt-0.5">{health}</div>
        <div className="sm:col-start-5 sm:row-start-1 sm:text-right">{action}</div>
      </div>

      {run && (
        <div className="col-start-2 mt-2 sm:col-end-6">
          <RunStatus run={run} />
        </div>
      )}
    </li>
  );
}

/**
 * The missing piece: a Machine that waits for a server, or a node the pool
 * wants and has no Machine for. A dashed outline and a hollow icon make the
 * gap plain at a glance, with why it waits.
 */
function Placeholder({ node, current }: { node: PoolNode; current: boolean }) {
  const waiting = node.state === "waiting";
  return (
    <li data-testid={`node-placeholder-${node.machine ?? "missing"}`} data-current={current || undefined} className="px-4 py-2.5">
      <div
        className={cn(
          "grid grid-cols-[0.5rem_minmax(0,1fr)] gap-x-3 rounded-lg border border-dashed px-3 py-2.5 sm:grid-cols-[0.5rem_minmax(0,1fr)_auto]",
          current ? "border-status-provisioning/50 bg-status-provisioning/5" : "border-muted-foreground/30 bg-muted/20"
        )}
      >
        <CircleDashed
          className={cn("-ml-1 mt-0.5 h-3.5 w-3.5", current ? "text-status-provisioning-fg" : "text-muted-foreground")}
          aria-hidden
        />
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{waiting ? "Waiting for a server" : "A node is missing"}</p>
          <p className="mt-0.5 text-xs text-muted-foreground break-words" data-testid="node-waiting-for">
            {node.waiting_for ??
              (waiting
                ? "No Agent is reserved for this Machine yet."
                : "The NodePool wants more nodes than it has Machines; one is still to be created.")}
          </p>
          {node.machine && (
            <Meta parts={[<Labelled key="m" label="Machine" mono>{node.machine}</Labelled>]} />
          )}
          {node.activity && <p className="mt-1 text-xs text-muted-foreground break-words">{node.activity}</p>}
        </div>
        <div className="col-start-2 mt-2 sm:col-start-3 sm:row-start-1 sm:mt-0">
          <NodeStateChip state={node.state} />
        </div>
      </div>
    </li>
  );
}

function NodeRow({ node, pool, actions }: { node: PoolNode; pool: string; actions: NodeActions }) {
  const { server } = node;
  const run = actions.runOf(server?.id ?? null, node.uninstall);
  const name = server?.name ?? node.server_name ?? node.machine ?? "—";
  const hardware = server ? [server.vendor, server.model].filter(Boolean).join(" ") : "";
  const agent = node.agent && (node.agent.state || node.agent.stage)
    ? [node.agent.state && humanize(node.agent.state), node.agent.stage].filter(Boolean).join(", ")
    : null;
  return (
    <Row
      testId={`node-${name}`}
      title={
        server ? (
          <ServerLink server={server} />
        ) : (
          <span className="whitespace-nowrap font-mono text-xs font-medium text-foreground" title="No server-scan record">
            {name}
          </span>
        )
      }
      flags={<NodeFlags server={server} outdated={node.outdated} />}
      meta={[
        server?.serial && <span key="serial" className="font-mono">{server.serial}</span>,
        hardware && <span key="hardware">{hardware}</span>,
        node.machine && name !== node.machine && <Labelled key="machine" label="Machine" mono>{node.machine}</Labelled>,
        agent && <Labelled key="agent" label="Agent">{agent}</Labelled>,
      ]}
      activity={node.activity}
      emphasis={node.current ? "current" : node.state === "failed" ? "failed" : null}
      state={<NodeStateChip state={node.state} />}
      health={server ? <HealthBadge health={server.health} /> : null}
      action={
        server && actions.canUninstall && !isRunning(run) ? (
          <UninstallButton target={{ server, pool, machine: node.machine }} actions={actions} />
        ) : null
      }
      run={run}
    />
  );
}

// ── A NodePool ───────────────────────────────────────────────────────────────

const UPDATE_KIND: Record<NodePoolUpdate["kind"], string> = {
  version: "version",
  config: "config",
  machine_template: "machine template",
};

/**
 * An update in progress, as the NodePool's condition says it: what is being
 * updated, how far (when an in-place update counts its nodes), and the
 * condition's own message. A failed one is in the destructive style.
 */
function UpdateBanner({ update }: { update: NodePoolUpdate }) {
  const what = UPDATE_KIND[update.kind] ?? humanize(update.kind).toLowerCase();
  const { progress, failed } = update;
  const percent = progress && progress.total > 0 ? Math.round((Math.min(progress.updated, progress.total) / progress.total) * 100) : 0;
  return (
    <div
      role="status"
      data-testid="node-pool-update"
      className={cn(
        "mx-4 mb-3 rounded-lg border px-3 py-2.5",
        failed ? "border-destructive/30 bg-destructive/5" : "border-status-provisioning/25 bg-status-provisioning/5"
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <p
          className={cn(
            "flex items-center gap-1.5 text-sm font-medium",
            failed ? "text-destructive" : "text-status-provisioning-fg"
          )}
        >
          {failed ? (
            <CircleX className="h-4 w-4" aria-hidden />
          ) : (
            <Loader2 className="h-4 w-4 animate-spin [animation-duration:2s] motion-reduce:animate-none" aria-hidden />
          )}
          {failed ? `${humanize(what)} update failed` : `Updating ${what}`}
        </p>
        {progress && (
          <p className="text-xs tabular-nums text-foreground" data-testid="node-pool-update-progress">
            {progress.updated} of {progress.total} node{progress.total !== 1 ? "s" : ""} updated
          </p>
        )}
      </div>
      {progress && (
        <div
          role="progressbar"
          aria-label="Nodes updated"
          aria-valuemin={0}
          aria-valuemax={progress.total}
          aria-valuenow={progress.updated}
          className={cn("mt-2 h-1 overflow-hidden rounded-full", failed ? "bg-destructive/15" : "bg-status-provisioning/15")}
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500 ease-out motion-reduce:transition-none",
              failed ? "bg-destructive" : "bg-status-provisioning"
            )}
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
      {update.message && (
        <p className={cn("mt-1.5 text-xs break-words", failed ? "text-destructive/80" : "text-muted-foreground")}>
          {update.message}
        </p>
      )}
    </div>
  );
}

/** How many problems show before "Show more". */
const PROBLEMS_SHOWN = 2;

/** "<Type>: <reason>: <message>", with the condition's type set apart. */
function ProblemLine({ text }: { text: string }) {
  const at = text.indexOf(": ");
  return (
    <span className="break-words">
      {at > 0 ? (
        <>
          <span className="font-medium text-foreground/80">{text.slice(0, at)}</span>
          {text.slice(at)}
        </>
      ) : (
        text
      )}
    </span>
  );
}

/** The NodePool's conditions that are not True: a quiet list, folded when long. */
function Problems({ problems, id }: { problems: string[]; id: string }) {
  const [open, setOpen] = useState(false);
  if (problems.length === 0) return null;
  const folded = problems.length > PROBLEMS_SHOWN && !open;
  const shown = folded ? problems.slice(0, PROBLEMS_SHOWN) : problems;
  return (
    <div className="mx-4 mb-3" data-testid="node-pool-problems">
      <ul id={id} className="space-y-1 text-xs text-muted-foreground">
        {shown.map((p, i) => (
          <li key={i} className="flex items-start gap-1.5">
            <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0 text-status-warning-fg" aria-hidden />
            <ProblemLine text={p} />
          </li>
        ))}
      </ul>
      {problems.length > PROBLEMS_SHOWN && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls={id}
          className="mt-1 ml-[1.125rem] rounded-sm text-xs font-medium text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {open ? "Show fewer" : `Show ${problems.length - PROBLEMS_SHOWN} more`}
        </button>
      )}
    </div>
  );
}

/** "2 / 3 ready" with a segment per node it wants, or the autoscaling range. */
function ReadySummary({ pool }: { pool: NodePoolNodes }) {
  const { ready, wanted, autoscaling } = pool;
  const short = wanted !== null && ready < wanted;
  return (
    <div className="shrink-0 text-right" data-testid="node-pool-ready">
      <p className="text-sm">
        <span className={cn("font-semibold tabular-nums", short ? "text-status-warning-fg" : "text-foreground")}>{ready}</span>
        {wanted !== null ? (
          <span className="text-muted-foreground tabular-nums"> / {wanted} ready</span>
        ) : (
          <span className="text-muted-foreground"> ready</span>
        )}
      </p>
      {autoscaling && (
        <p className="text-xs text-muted-foreground tabular-nums">
          autoscales {autoscaling.min}–{autoscaling.max}
        </p>
      )}
      {wanted !== null && wanted > 0 && wanted <= 24 && (
        <div className="mt-1.5 flex justify-end gap-0.5" aria-hidden>
          {Array.from({ length: wanted }).map((_, i) => (
            <span key={i} className={cn("h-1 w-3 rounded-full", i < ready ? "bg-status-ready" : "bg-muted-foreground/20")} />
          ))}
        </div>
      )}
    </div>
  );
}

const UPGRADE_HINT = {
  InPlace: "Updates drain and reboot each node in place.",
  Replace: "Updates replace each node with a new Machine.",
} as const;

/**
 * One NodePool as a card: its summary in the header (ready count, version,
 * how it updates, its Agent selector), an update in progress as a banner, its
 * problems, then its nodes. The node being worked on and any missing piece
 * stand out; ready nodes stay quiet.
 */
export function NodePoolCard({ pool, actions }: { pool: NodePoolNodes; actions: NodeActions }) {
  const short = pool.nodes.some((n) => n.state === "waiting" || n.state === "missing");
  const slug = pool.name.replace(/[^A-Za-z0-9_-]/g, "-");
  return (
    <section
      aria-labelledby={`pool-${slug}`}
      data-testid={`node-pool-${pool.name}`}
      className="overflow-hidden rounded-xl border bg-card shadow-sm"
    >
      <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 px-4 pb-3 pt-3.5">
        <div className="min-w-0 space-y-1">
          <h3 id={`pool-${slug}`} className="flex items-center gap-2 text-sm font-semibold">
            <Layers className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="break-all">{pool.name}</span>
          </h3>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            {pool.version && (
              <span title="The version it last finished updating to">
                <span className="text-muted-foreground/70">Version </span>
                <span className="font-mono text-foreground">{pool.version}</span>
              </span>
            )}
            {pool.upgrade_type && (
              <span
                className="rounded-md border px-1.5 py-px font-mono text-[11px] text-foreground/80"
                title={UPGRADE_HINT[pool.upgrade_type]}
                data-testid="node-pool-upgrade-type"
              >
                {pool.upgrade_type}
              </span>
            )}
            {short && pool.free_agents && (
              <span
                data-testid="node-pool-free-agents"
                className={cn(pool.free_agents.free === 0 && "font-medium text-status-warning-fg")}
              >
                {pool.free_agents.free} free of {pool.free_agents.matching} matching Agent{pool.free_agents.matching !== 1 ? "s" : ""}
              </span>
            )}
          </p>
          {pool.agent_selector && (
            <p className="font-mono text-[11px] text-muted-foreground/80 break-all" title="The Agents this NodePool takes">
              {pool.agent_selector}
            </p>
          )}
        </div>
        <ReadySummary pool={pool} />
      </header>

      {pool.update && <UpdateBanner update={pool.update} />}
      <Problems problems={pool.problems} id={`pool-${slug}-problems`} />

      {pool.nodes.length === 0 ? (
        <p className="border-t px-4 py-3 text-xs text-muted-foreground">This NodePool has no Machines.</p>
      ) : (
        <ul className="divide-y border-t">
          {pool.nodes.map((node, i) =>
            node.state === "waiting" || node.state === "missing" ? (
              <Placeholder key={node.machine ?? `missing-${i}`} node={node} current={node.current} />
            ) : (
              <NodeRow key={node.machine ?? `node-${i}`} node={node} pool={pool.name} actions={actions} />
            )
          )}
        </ul>
      )}
    </section>
  );
}

// ── Servers in no NodePool ───────────────────────────────────────────────────

/**
 * Servers server-scan still places in this cluster that no Machine on the
 * MCE leads to: quieter than the pools, with why they are here.
 */
export function UnassignedServers({ servers, actions }: { servers: UnassignedServer[]; actions: NodeActions }) {
  if (servers.length === 0) return null;
  return (
    <section
      aria-labelledby="unassigned-servers"
      data-testid="nodes-unassigned"
      className="overflow-hidden rounded-xl border border-dashed bg-card/40"
    >
      <header className="px-4 pb-3 pt-3.5">
        <h3 id="unassigned-servers" className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
          <ServerOff className="h-4 w-4 shrink-0" aria-hidden />
          In server-scan, not in any NodePool
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium tabular-nums">{servers.length}</span>
        </h3>
        <p className="mt-1 text-xs text-muted-foreground">
          server-scan still lists these servers in this cluster, but no Machine on the MCE has them: typical for a few
          minutes after an uninstall.
        </p>
      </header>
      <ul className="divide-y border-t border-dashed">
        {servers.map((server) => {
          const run = actions.runOf(server.id, server.uninstall);
          const hardware = [server.vendor, server.model].filter(Boolean).join(" ");
          return (
            <Row
              key={server.id}
              testId={`node-${server.name}`}
              title={<ServerLink server={server} />}
              flags={<NodeFlags server={server} />}
              meta={[
                server.serial && <span key="serial" className="font-mono">{server.serial}</span>,
                hardware && <span key="hardware">{hardware}</span>,
              ]}
              activity={null}
              emphasis={null}
              state={<ServerStateText state={server.state} />}
              health={<HealthBadge health={server.health} />}
              action={
                actions.canUninstall && !isRunning(run) ? (
                  <UninstallButton target={{ server, pool: null, machine: null }} actions={actions} />
                ) : null
              }
              run={run}
            />
          );
        })}
      </ul>
    </section>
  );
}
