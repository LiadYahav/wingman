"use client";

import { CircleCheck, CircleX, Loader2 } from "lucide-react";
import { ProblemList } from "@/components/common/problem-list";
import { AgentProposals } from "@/components/clusters/upgrade/agent-proposals";
import { DecisionBar } from "@/components/clusters/upgrade/decision-bar";
import { PlanSteps } from "@/components/clusters/upgrade/plan-steps";
import { useUpgradeRun } from "@/lib/api/upgrades";
import { humanize } from "@/lib/nodes";
import { isOpen } from "@/lib/upgrade";
import { cn, formatDateTime } from "@/lib/utils";
import type { UpgradeRun } from "@/types";

/** The run's state in a word: its phase while open (paused said so), its outcome once done, else its status. */
function stateWord(run: UpgradeRun): string {
  if (isOpen(run)) {
    const phase = run.phase ? humanize(run.phase) : "Starting";
    return run.paused && run.phase !== "paused" ? `Paused · ${phase}` : phase;
  }
  return humanize(run.outcome ?? run.status);
}

function Facts({ run }: { run: UpgradeRun }) {
  const rows: [string, string | null][] = [
    ["MCE", run.mce],
    ["Control plane", run.control_plane_version],
    ["Profile", run.profile],
    ["Ladder checked", run.verified_against_graph],
  ];
  return (
    <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-[7rem_1fr]">
      {rows.filter(([, value]) => value).map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="font-mono break-all">{value}</dd>
        </div>
      ))}
      <dt className="text-muted-foreground">Run</dt>
      <dd className="font-mono break-all text-muted-foreground">{run.workflow_id}</dd>
    </dl>
  );
}

/** A closed run's outcome and final versions, in one line. */
function Outcome({ run }: { run: UpgradeRun }) {
  if (isOpen(run) || run.outcome === null) return null;
  const pools = Object.entries(run.nodepool_versions).map(([pool, version]) => `${pool} ${version}`).join(", ");
  const steps = run.plan?.steps.length;
  return (
    <p data-testid="upgrade-outcome" className="text-sm text-muted-foreground break-words">
      Control plane <span className="font-mono text-foreground">{run.control_plane_version ?? "—"}</span>
      {pools && <>; NodePools <span className="font-mono">{pools}</span></>}.
      {run.steps_completed !== null && steps !== undefined && ` ${run.steps_completed} of ${steps} steps ran.`}
    </p>
  );
}

/** The run's log, newest first, folded away. */
function Log({ run }: { run: UpgradeRun }) {
  if (run.log.length === 0) return null;
  return (
    <details className="text-xs" data-testid="upgrade-log">
      <summary className="cursor-pointer text-muted-foreground">Log ({run.log.length})</summary>
      <ol className="mt-2 space-y-1">
        {[...run.log].reverse().map((line, i) => (
          <li key={`${line.at}-${i}`} className="break-words">
            <span className="text-muted-foreground">{formatDateTime(line.at)}</span>{" "}
            <span className="font-medium">{line.event}</span>
            {line.by && <span className="text-muted-foreground"> · {line.by}</span>}
            {line.detail && <span className="text-muted-foreground">: {line.detail}</span>}
          </li>
        ))}
      </ol>
    </details>
  );
}

function Heading({ run }: { run: UpgradeRun }) {
  const open = isOpen(run);
  const done = run.outcome === "done";
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {open ? (
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-status-provisioning-fg motion-reduce:animate-none" aria-hidden />
      ) : done ? (
        <CircleCheck className="h-4 w-4 shrink-0 text-status-ready-fg" aria-hidden />
      ) : (
        <CircleX className="h-4 w-4 shrink-0 text-status-error-fg" aria-hidden />
      )}
      <h2 id="upgrade-run-title" className="text-sm font-semibold">
        Upgrade
        {run.plan && (
          <span className="ml-1.5 font-mono font-normal">
            {run.plan.control_plane} → {run.plan.target}
          </span>
        )}
      </h2>
      <span data-testid="upgrade-phase" title={run.phase ?? undefined} className="text-sm font-medium text-muted-foreground">
        {stateWord(run)}
      </span>
    </div>
  );
}

/**
 * The cluster's newest upgrade-cluster run (ADR-0055), on the Overview: what
 * it is doing in the workflow's own words, what it waits for, its decisions
 * for admins, its plan, the agent's proposals and its log. Read again every
 * 10 s while it is open; nothing at all while upgrades are off or there is
 * no run.
 */
export function UpgradePanel({
  name,
  where,
  isAdmin,
  onOpenNodesTab,
}: {
  name: string;
  where: string;
  isAdmin: boolean;
  onOpenNodesTab: () => void;
}) {
  const { data, error } = useUpgradeRun(name, where);
  if (!data || data.state !== "run") {
    return error ? (
      <div data-testid="upgrade-run-read-error">
        <ProblemList error={error} title="The cluster's upgrade run could not be read" />
      </div>
    ) : null;
  }
  const run = data.run;
  const open = isOpen(run);
  return (
    <section
      data-testid="upgrade-panel"
      aria-labelledby="upgrade-run-title"
      className={cn(
        "rounded-xl border p-4 space-y-3",
        open && "border-status-provisioning/30 bg-status-provisioning/5",
        !open && run.outcome === "done" && "border-status-ready/30 bg-status-ready/5",
        !open && run.outcome !== "done" && "border-status-error/30 bg-status-error/5"
      )}
    >
      <Heading run={run} />
      {run.waiting_for && (
        <p data-testid="upgrade-waiting-for" className="rounded-md bg-background/60 px-3 py-2 text-sm break-words">
          {run.waiting_for}
        </p>
      )}
      {isAdmin && <DecisionBar name={name} where={where} run={run} />}
      <Outcome run={run} />
      {run.error && (
        <p data-testid="upgrade-run-error" className="rounded-md bg-status-error/10 px-3 py-2 text-sm text-status-error-fg break-words">
          {run.error}
        </p>
      )}
      <PlanSteps run={run} onOpenNodesTab={onOpenNodesTab} />
      <AgentProposals name={name} where={where} run={run} isAdmin={isAdmin} />
      <Facts run={run} />
      <Log run={run} />
      {error && <ProblemList error={error} title="The run could not be read again" />}
    </section>
  );
}
