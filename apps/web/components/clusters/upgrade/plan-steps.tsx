"use client";

import { Circle, CircleCheck, Loader2, TriangleAlert } from "lucide-react";
import { humanize } from "@/lib/nodes";
import { poolStates, stepStates, type PoolState, type StepState } from "@/lib/upgrade";
import { cn } from "@/lib/utils";
import type { UpgradeRun } from "@/types";

const POOL_STYLE: Record<PoolState, string> = {
  done: "border-status-ready/30 bg-status-ready/10 text-status-ready-fg",
  current: "border-status-provisioning/40 bg-status-provisioning/10 text-status-provisioning-fg",
  alert: "border-status-error/40 bg-status-error/10 text-status-error-fg",
  next: "border-primary/40 bg-primary/5 text-primary",
  waiting: "border-border text-muted-foreground",
};

const POOL_TITLE: Record<PoolState, string> = {
  done: "Rolled",
  current: "Rolling now: its nodes are on the Nodes tab",
  alert: "Stopped here: its nodes are on the Nodes tab",
  next: "Next, after the customer's Continue",
  waiting: "Waiting",
};

function StepIcon({ state }: { state: StepState }) {
  if (state === "done") return <CircleCheck className="h-4 w-4 text-status-ready-fg" aria-hidden />;
  if (state === "current") {
    return <Loader2 className="h-4 w-4 animate-spin text-status-provisioning-fg motion-reduce:animate-none" aria-hidden />;
  }
  if (state === "alert") return <TriangleAlert className="h-4 w-4 text-status-error-fg" aria-hidden />;
  return <Circle className="h-4 w-4 text-muted-foreground/50" aria-hidden />;
}

/**
 * The run's plan as a list of steps, from "now runs" to the target. Each step
 * is done, under way or pending from the run's own fields; a workers step
 * lists its NodePools, and one rolling now opens the Nodes tab.
 */
export function PlanSteps({ run, onOpenNodesTab }: { run: UpgradeRun; onOpenNodesTab: () => void }) {
  const plan = run.plan;
  if (!plan) return null;
  const states = stepStates(run);
  return (
    <ol className="space-y-1.5 text-sm" data-testid="upgrade-plan" aria-label="The plan">
      <li className="flex items-center gap-2 text-muted-foreground">
        <CircleCheck className="h-4 w-4 text-muted-foreground/60" aria-hidden />
        Runs <span className="font-mono">{plan.control_plane}</span>
      </li>
      {plan.steps.map((step, i) => {
        const state = states[i];
        const pools = step.nodepools.length > 0 ? poolStates(run, step, state) : {};
        return (
          <li key={i} data-testid="upgrade-step" data-state={state} className="flex items-start gap-2">
            <span className="mt-0.5"><StepIcon state={state} /></span>
            <div className="min-w-0 space-y-1">
              <p>
                <span className={cn(state === "pending" && "text-muted-foreground")}>{humanize(step.kind)}</span>{" "}
                <span className="font-mono">{step.version}</span>{" "}
                <span className="text-xs text-muted-foreground" title="Why the plan has this step">{humanize(step.reason).toLowerCase()}</span>
              </p>
              {step.nodepools.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {step.nodepools.map((pool) => {
                    const poolState = pools[pool];
                    const limit = run.max_unavailable[pool];
                    const chip = cn("rounded-md border px-1.5 py-0.5 font-mono text-xs break-all", POOL_STYLE[poolState]);
                    const label = limit ? `${pool} · max ${limit}` : pool;
                    return poolState === "current" || poolState === "alert" ? (
                      <button
                        key={pool}
                        type="button"
                        onClick={onOpenNodesTab}
                        title={POOL_TITLE[poolState]}
                        data-testid="upgrade-current-nodepool"
                        className={cn(chip, "underline-offset-2 hover:underline")}
                      >
                        {label}
                      </button>
                    ) : (
                      <span key={pool} title={POOL_TITLE[poolState]} className={chip}>{label}</span>
                    );
                  })}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
