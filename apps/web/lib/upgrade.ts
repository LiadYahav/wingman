/**
 * What the cluster page draws from an upgrade-cluster run (ADR-0055), as pure
 * functions. The run's validators judge every decision; this only chooses
 * which buttons to offer. The workflow's phases are never listed here: the
 * one map below is phase → decisions, the same one the orchestrator's own
 * page keeps, until the run reports `decisions` itself
 * (docs/notes/2026-11-13-upgrade-cluster-workflow-api.md §4).
 */

import type { UpgradeDecision, UpgradePlanStep, UpgradeRun } from "@/types";

/** The decisions a person makes in each phase that waits for one. */
const DECISIONS_BY_PHASE: Readonly<Record<string, readonly UpgradeDecision[]>> = {
  "awaiting-approval": ["approve"],
  "awaiting-day2-confirm": ["confirm-day2"],
  "awaiting-admin-ack": ["approve-admin-ack", "retry"],
  "awaiting-continue": ["continue"],
  "needs-human": ["retry"],
};

/** The phase where the agent's proposals wait for a person. */
const PROPOSALS_PHASE = "needs-human";

const KNOWN: ReadonlySet<string> = new Set<UpgradeDecision>([
  "approve", "approve-admin-ack", "continue", "confirm-day2", "pause", "resume", "abort", "retry",
]);

export const isOpen = (run: UpgradeRun | null | undefined): boolean => run?.status === "running";

/**
 * The buttons for a run: what it says it accepts, when it does; otherwise the
 * phase's from the map, then Pause (Resume once paused) and Abort while it is
 * open. A phase the map doesn't know gets only Pause and Abort.
 */
export function decisionsFor(run: UpgradeRun): UpgradeDecision[] {
  if (!isOpen(run)) return [];
  if (run.decisions !== null) return run.decisions.filter((d): d is UpgradeDecision => KNOWN.has(d));
  const own = (run.phase && DECISIONS_BY_PHASE[run.phase]) || [];
  return [...own, run.paused ? "resume" : "pause", "abort"];
}

/** Whether the agent's pending proposals can be decided now. */
export function proposalsOpen(run: UpgradeRun): boolean {
  if (!isOpen(run)) return false;
  return run.decisions !== null ? run.decisions.includes("retry") : run.phase === PROPOSALS_PHASE;
}

/** Each decision's button, its confirm dialog's title, and a one-line explanation (a tooltip). */
export const DECISION_TEXT: Readonly<Record<UpgradeDecision, { label: string; explain: string }>> = {
  approve: { label: "Approve", explain: "Nothing is committed yet. Approving lets the run commit its first step to day1 and sync it." },
  "approve-admin-ack": {
    label: "Approve admin ack",
    explain: "A client still calls an API this ack removes. Approving gives the ack anyway; say why.",
  },
  continue: {
    label: "Continue",
    explain: "The customer's sign-off: their readiness checks passed, so the next NodePool may roll.",
  },
  "confirm-day2": { label: "Day2 is ready", explain: "The day2 layers for this version are applied, so the run may go on." },
  pause: { label: "Pause", explain: "Hold the run before its next commit. What is already rolling finishes." },
  resume: { label: "Resume", explain: "Carry on from where the pause held the run." },
  abort: {
    label: "Abort",
    explain: "Before approval nothing was committed. After it, the run commits pausedUntil and stops. Nothing is rolled back.",
  },
  retry: { label: "Retry", explain: "Try again what stopped the run (after an approved proposal ran, or the cause was fixed)." },
};

/** Decisions the workflow refuses without a reason. */
export const needsReason = (decision: UpgradeDecision): boolean => decision === "abort" || decision === "approve-admin-ack";

/** Decisions that take no reason at all (the workflow's body refuses one). */
export const takesReason = (decision: UpgradeDecision): boolean => decision !== "continue";

/** Decisions that name a NodePool. */
export const takesNodePool = (decision: UpgradeDecision): boolean => decision === "continue";

export type StepState = "done" | "current" | "alert" | "pending";

/**
 * Each plan step's state, from the run's own fields: a closed run's first
 * `steps_completed` are done; an open one's steps before `current_step` are
 * done and that one is under way. Nothing is under way before the run has a
 * current step or while it waits for approval.
 */
export function stepStates(run: UpgradeRun): StepState[] {
  const steps = run.plan?.steps ?? [];
  if (run.steps_completed !== null) return steps.map((_, i) => (i < run.steps_completed! ? "done" : "pending"));
  const at = run.current_step;
  if (at === null || run.phase === "awaiting-approval") return steps.map(() => "pending");
  const here: StepState = !isOpen(run) || run.phase === PROPOSALS_PHASE ? "alert" : "current";
  return steps.map((_, i) => (i < at ? "done" : i > at ? "pending" : here));
}

export type PoolState = "done" | "current" | "alert" | "next" | "waiting";

/** The NodePools of a workers step, each done, rolling, next (it waits for continue) or waiting. */
export function poolStates(run: UpgradeRun, step: UpgradePlanStep, state: StepState): Record<string, PoolState> {
  const states: Record<string, PoolState> = {};
  const remaining = step.nodepools.filter((n) => !run.nodepools_done.includes(n));
  const next = (run.decisions ?? DECISIONS_BY_PHASE[run.phase ?? ""] ?? []).includes("continue") ? remaining[0] : undefined;
  for (const name of step.nodepools) {
    if (state === "done") states[name] = "done";
    else if (state === "pending") states[name] = "waiting";
    else if (run.nodepools_done.includes(name)) states[name] = "done";
    else if (run.current_nodepool === name) states[name] = state === "alert" ? "alert" : "current";
    else states[name] = name === next ? "next" : "waiting";
  }
  return states;
}

/** The NodePools a `continue` may name: the current workers step's, not done yet, in its order. */
export function nodePoolsLeft(run: UpgradeRun): string[] {
  const step = run.current_step !== null ? run.plan?.steps[run.current_step] : undefined;
  return step ? step.nodepools.filter((n) => !run.nodepools_done.includes(n)) : [];
}

/**
 * The start request's `max_unavailable`: only the NodePools whose value was
 * changed from the file's, as a whole number when it is one. `undefined`
 * when nothing changed (the workflow keeps every NodePool's own).
 */
export function changedMaxUnavailable(
  edited: Record<string, string>,
  file: Record<string, string | null>
): Record<string, number | string> | undefined {
  const changed: Record<string, number | string> = {};
  for (const [name, raw] of Object.entries(edited)) {
    const value = raw.trim();
    if (!value || value === (file[name] ?? "")) continue;
    changed[name] = /^\d+$/.test(value) ? Number(value) : value;
  }
  return Object.keys(changed).length > 0 ? changed : undefined;
}
