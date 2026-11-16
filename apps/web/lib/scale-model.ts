/**
 * What the Nodes tab's Scale draws from update-nodepool's data (ADR-0062), as
 * pure functions. Wingman starts the run and shows it: the plan, the balance
 * rule and the phases are the workflow's, so nothing here spreads a total or
 * lists a phase. A phase or a status the workflow adds is shown humanized.
 */

import { isApiError } from "@/lib/api-client";
import { humanize } from "@/lib/nodes";
import type { ErrorCode, ScaleKind, ScaleNodePool, ScaleRun, StartScaleRequest } from "@/types";

/** Scale by a hardware kind (a total over its NodePools) or one NodePool (its own replicas). */
export type ScaleMode = "kind" | "nodepool";

/** The most replicas the form takes: a guard against a typo, not the workflow's rule. */
export const MAX_REPLICAS = 500;

/** Refusals after which the page's run is out of date (a run started, or may have): it is read again. */
export const STALE_RUN_CODES: readonly ErrorCode[] = ["SCALE_ALREADY_RUNNING", "AMBIGUOUS_WRITE", "NOT_FOUND"];

export const isRunning = (run: ScaleRun | null | undefined): boolean => run?.status === "running";

/** `Scaling down · Marking machines`: the run's phase, and its child's while the child has one. */
export function phaseWords(run: ScaleRun): string {
  const parent = run.phase ? humanize(run.phase) : isRunning(run) ? "Starting" : humanize(run.status);
  const child = run.child?.phase;
  return child && child !== "completed" && run.status !== "completed" ? `${parent} · ${humanize(child)}` : parent;
}

/** The run in a word: its phase while it runs, else its status (Completed, Failed, Canceled...). */
export function stateWord(run: ScaleRun): string {
  return isRunning(run) ? phaseWords(run) : humanize(run.status);
}

/** Why Scale (and every restore) waits: a run of this cluster is open, scale or upgrade. One at a time. */
export function busyReason(scaleRunning: boolean, upgradeOpen: boolean): string | null {
  if (scaleRunning) return "An update-nodepool run of this cluster is running: one at a time. Scale again once it ends.";
  if (upgradeOpen) {
    return "An upgrade-cluster run of this cluster is open: both commit to its day1 file, so update-nodepool refuses to start until it ends.";
  }
  return null;
}

/** Why a kind cannot be scaled; `null` when it can. */
export function kindBlock(kind: ScaleKind, flavor: string | null): string | null {
  if (kind.locked.length > 0) {
    const pools = kind.locked.join(", ");
    return `Locked by flavor ${flavor ?? "its flavor"}: it selects ${pools}, whose replicas the flavor fixes.`;
  }
  if (kind.total === null) return "A NodePool of this kind has replicas that are not a number in the day1 file.";
  return null;
}

/** Why a NodePool cannot be scaled by name; `null` when it can. */
export function nodepoolBlock(pool: ScaleNodePool): string | null {
  if (pool.name === null) return pool.unnamed ?? "Its NodePool cannot be named from the day1 file.";
  if (pool.locked_by !== null) return `Locked by flavor ${pool.locked_by} at ${pool.locked_replicas ?? "its value"}.`;
  if (pool.replicas === null) return "Its replicas in the day1 file are not a number.";
  return null;
}

/** The hardware types whose total can be scaled: over two or more NodePools (with one, the NodePool's own does the same). */
export const totalKinds = (kinds: ScaleKind[]): ScaleKind[] => kinds.filter((k) => k.nodepools.length >= 2);

/** The one change waiting to be sent: a kind's new total, or one NodePool's new replicas. */
export interface ScaleChange {
  mode: ScaleMode;
  target: string;
  /** As typed: `NaN` while the field is empty. */
  replicas: number;
}

/** A locked NodePool whose replicas differ from the flavor's: restored with update-nodepool. */
export function needsRestore(pool: ScaleNodePool): boolean {
  return pool.locked_by !== null && pool.locked_replicas !== null && pool.name !== null && pool.replicas !== pool.locked_replicas;
}

/** What a replicas field holds: its digits as a number, `NaN` when it has none. */
export function typedReplicas(text: string): number {
  const digits = text.replace(/\D/g, "");
  return digits === "" ? NaN : Number(digits);
}

/** One step (or `by`) from the value shown, kept from 0 to MAX_REPLICAS. */
export function stepped(value: number, by: number): number {
  return Math.min(MAX_REPLICAS, Math.max(0, (Number.isNaN(value) ? 0 : value) + by));
}

/** A whole number from 0 to MAX_REPLICAS; `null` for anything else. */
export function replicasOf(value: number): number | null {
  return Number.isInteger(value) && value >= 0 && value <= MAX_REPLICAS ? value : null;
}

/** The start's body: exactly one target, as the API takes it; `null` until the choice is complete. */
export function startBody(mode: ScaleMode, target: string | null, replicas: number): StartScaleRequest | null {
  const count = replicasOf(replicas);
  if (!target || count === null) return null;
  return mode === "kind" ? { infra_env_kind: target, replicas: count } : { nodepool: target, replicas: count };
}

/** What the choice is now: the replicas it starts from (a kind's total, a NodePool's own). */
export function currentOf(
  mode: ScaleMode,
  target: string | null,
  kinds: ScaleKind[],
  nodepools: ScaleNodePool[]
): number | null {
  if (!target) return null;
  if (mode === "kind") return kinds.find((k) => k.kind === target)?.total ?? null;
  return nodepools.find((p) => p.name === target)?.replicas ?? null;
}

/** `3 → 5`, with an unknown side as a dash. */
export const fromTo = (before: number | null, after: number | null) => `${before ?? "—"} → ${after ?? "—"}`;

/** What a change is of, in words: a NodePool, or `<kind> total`. */
export const changeLabel = ({ mode, target }: Pick<ScaleChange, "mode" | "target">) => (mode === "kind" ? `${target} total` : target);

/** `2 → 3 (+1)`, `4 → 1 (−3)`: a change and its difference. */
export function changeWords(current: number | null, asked: number | null): string {
  if (current === null || asked === null || asked === current) return fromTo(current, asked);
  const delta = asked - current;
  return `${fromTo(current, asked)} (${delta > 0 ? "+" : "\u2212"}${Math.abs(delta)})`;
}

/** `up`, `down` or `none` from where it is to what is asked; `null` when where it is is unknown. */
export function directionOf(current: number | null, asked: number | null): "up" | "down" | "none" | null {
  if (current === null || asked === null) return null;
  return asked > current ? "up" : asked < current ? "down" : "none";
}

/** The heading of a refused start, by its `code`; the problem's own words are listed under it. */
export function refusalTitle(error: unknown): string {
  if (isApiError(error, "SCALE_ALREADY_RUNNING")) return "update-nodepool refused to start: a run of this cluster is going.";
  if (isApiError(error, "AMBIGUOUS_WRITE")) {
    return "The start was sent but not confirmed, so it may have started: the run is read again. Look at it before trying again.";
  }
  if (isApiError(error, "VALIDATION_ERROR")) return "Wingman refused the request.";
  if (isApiError(error, "DEPENDENCY_UNAVAILABLE")) return "Nothing started: the workflows orchestrator did not answer.";
  if (isApiError(error, "FEATURE_DISABLED")) return "Scaling is not turned on in this deployment.";
  if (isApiError(error, "FORBIDDEN")) return "Only an admin can scale a cluster.";
  return "The scale did not start.";
}
