"use client";

import { CircleCheck, CircleX, Loader2 } from "lucide-react";
import { humanize } from "@/lib/nodes";
import { fromTo, isRunning, stateWord } from "@/lib/scale-model";
import { cn } from "@/lib/utils";
import type { ScaleResult, ScaleRun } from "@/types";

const DIRECTION: Record<string, string> = { up: "Scaling up", down: "Scaling down", none: "Nothing to change" };

/** What the run was asked, as its result says it: a kind's total, or one NodePool. */
function targetOf(result: ScaleResult | null): string | null {
  if (!result) return null;
  return result.infra_env_kind ? `kind ${result.infra_env_kind}` : result.nodepool ? `NodePool ${result.nodepool}` : null;
}

/** Each NodePool the run planned, before → after, with the policy a scale-down picks its servers by. */
function Plan({ result }: { result: ScaleResult }) {
  if (result.nodepools.length === 0) return null;
  const down = result.direction === "down";
  return (
    <div className="space-y-1.5">
      <table className="w-full text-xs" data-testid="scale-run-plan">
        <caption className="sr-only">Replicas before and after, per NodePool</caption>
        <thead className="text-left text-muted-foreground">
          <tr>
            <th scope="col" className="py-1 pr-3 font-medium">NodePool</th>
            <th scope="col" className="hidden py-1 pr-3 font-medium sm:table-cell">InfraEnv</th>
            <th scope="col" className="py-1 pr-3 font-medium">Replicas</th>
            {down && <th scope="col" className="py-1 font-medium">Scale-down policy</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {result.nodepools.map((np) => (
            <tr key={np.name} data-testid={`scale-run-pool-${np.name}`}>
              <td className="py-1.5 pr-3 font-mono break-all">{np.name}</td>
              <td className="hidden py-1.5 pr-3 font-mono text-muted-foreground break-all sm:table-cell">{np.infra_env ?? "—"}</td>
              <td className={cn("py-1.5 pr-3 tabular-nums whitespace-nowrap", np.before !== np.after && "font-medium")}>
                {fromTo(np.before, np.after)}
              </td>
              {down && <td className="py-1.5 text-muted-foreground">{np.scale_down_policy ?? "none: CAPI picks at random"}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      {result.total_before !== null && result.nodepools.length > 1 && (
        <p className="text-xs text-muted-foreground" data-testid="scale-run-total">
          Total <span className="tabular-nums font-medium text-foreground">{fromTo(result.total_before, result.total_after)}</span>
        </p>
      )}
    </div>
  );
}

/** The servers a scale-down chose to leave, and what put each first. */
function Chosen({ result }: { result: ScaleResult }) {
  if (result.chosen.length === 0) return null;
  return (
    <section aria-label="Servers chosen to leave" className="space-y-1" data-testid="scale-run-chosen">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Servers chosen to leave</h3>
      <ul className="space-y-0.5 text-xs">
        {result.chosen.map((c) => (
          <li key={c.machine} className="break-words">
            <span className="font-mono font-medium">{c.node ?? c.machine}</span>
            {c.node && <span className="font-mono text-muted-foreground"> ({c.machine})</span>}
            <span className="text-muted-foreground"> · {c.nodepool} · {c.policy}: {c.reason}</span>
          </li>
        ))}
      </ul>
      {result.deleting.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Seen deleting: <span className="font-mono break-all">{result.deleting.join(", ")}</span>. They return to the MCE&apos;s inventory as free Agents.
        </p>
      )}
    </section>
  );
}

/** Where the change went: the day1 commit, or that day1 already held it. */
function Commit({ result }: { result: ScaleResult }) {
  if (result.direction === "none") {
    return <p className="text-xs text-muted-foreground">The replicas already were the request: nothing was written.</p>;
  }
  if (!result.revision) return null;
  const short = result.revision.slice(0, 10);
  return (
    <p className="text-xs text-muted-foreground" data-testid="scale-run-commit">
      {result.committed === false ? (
        <>day1 already held these replicas (main at <span className="font-mono">{short}</span>); the run synced and checked them.</>
      ) : (
        <>Committed <span className="font-mono text-foreground">{short}</span> to day1 main; Argo CD applied it and the NodePools show it.</>
      )}
    </p>
  );
}

/**
 * The cluster's newest update-nodepool run (ADR-0062), in place on the Nodes
 * tab: what it is doing in the workflow's own words (its child's step too),
 * then, once done, each NodePool before → after, the servers a scale-down
 * chose and the commit; a failure in the workflow's words. While it runs the
 * plan is not known yet: the workflow reports it when it completes.
 */
export function ScaleRunCard({ run }: { run: ScaleRun }) {
  const running = isRunning(run);
  const done = run.status === "completed";
  const result = run.result;
  const target = targetOf(result);
  const direction = result?.direction ?? run.direction;
  return (
    <section
      id="scale-run"
      tabIndex={-1}
      data-testid="scale-run"
      data-status={run.status}
      aria-labelledby="scale-run-title"
      className={cn(
        "rounded-xl border p-4 space-y-3 outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        running && "border-status-provisioning/30 bg-status-provisioning/5",
        done && "border-status-ready/30 bg-status-ready/5",
        !running && !done && "border-status-error/30 bg-status-error/5"
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {running ? (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-status-provisioning-fg motion-reduce:animate-none" aria-hidden />
        ) : done ? (
          <CircleCheck className="h-4 w-4 shrink-0 text-status-ready-fg" aria-hidden />
        ) : (
          <CircleX className="h-4 w-4 shrink-0 text-status-error-fg" aria-hidden />
        )}
        <h3 id="scale-run-title" className="text-sm font-semibold">
          Scale{target && <> <span className="font-mono font-normal break-all">{target}</span></>}
        </h3>
        <span role="status" data-testid="scale-run-phase" title={run.phase ?? undefined} className="text-sm font-medium text-muted-foreground">
          {stateWord(run)}
        </span>
        {direction && direction !== "none" && running && !stateWord(run).startsWith(DIRECTION[direction] ?? "\0") && (
          <span className="text-xs text-muted-foreground" data-testid="scale-run-direction">{DIRECTION[direction] ?? humanize(direction)}</span>
        )}
      </div>
      {running && !result && (
        <p className="text-xs text-muted-foreground">
          The workflow reports each NodePool before and after once it completes. It never waits for new nodes to be Ready.
        </p>
      )}
      {run.error && (
        <div data-testid="scale-run-error" className="rounded-md bg-status-error/10 px-3 py-2 text-sm text-status-error-fg space-y-0.5">
          {run.error_type && <p className="font-mono text-xs font-medium">{run.error_type}</p>}
          <p className="break-words">{run.error}</p>
        </div>
      )}
      {result && <Plan result={result} />}
      {result && <Chosen result={result} />}
      {result && <Commit result={result} />}
      <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-[7rem_1fr]">
        <dt className="text-muted-foreground">Run</dt>
        <dd className="font-mono break-all text-muted-foreground">{run.workflow_id}</dd>
        {run.child && (
          <>
            <dt className="text-muted-foreground">Child</dt>
            <dd className="font-mono break-all text-muted-foreground">
              {run.child.workflow_id}
              {run.child.status && <span className="font-sans"> · {humanize(run.child.status)}</span>}
            </dd>
          </>
        )}
      </dl>
    </section>
  );
}
