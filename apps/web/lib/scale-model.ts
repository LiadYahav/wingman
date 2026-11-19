/**
 * What the Nodes tab's Scale draws from update-nodepool's data (ADR-0062), as
 * pure functions. Wingman starts the run and shows it: the plan, the balance
 * rule and the phases are the workflow's, so nothing here spreads a total or
 * lists a phase. A phase or a status the workflow adds is shown humanized.
 */

import { isApiError } from "@/lib/api-client";
import { humanize } from "@/lib/nodes";
import type { ErrorCode, ScaleNodePool, ScaleRun, StartScaleRequest } from "@/types";

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

/** Why a NodePool cannot be scaled by name; `null` when it can. */
export function nodepoolBlock(pool: ScaleNodePool): string | null {
  if (pool.name === null) return pool.unnamed ?? "Its NodePool cannot be named from the day1 file.";
  if (pool.locked_by !== null) return `Locked by flavor ${pool.locked_by} at ${pool.locked_replicas ?? "its value"}.`;
  if (pool.replicas === null) return "Its replicas in the day1 file are not a number.";
  return null;
}

/** The one change waiting to be sent: one NodePool's new replicas (update-nodepool sets one NodePool a run). */
export interface ScaleChange {
  nodepool: string;
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

/**
 * The start's body: one NodePool and its replicas, and the servers that leave when a scale-down names them (the
 * caller sends none on a scale-up); `null` until the number is a whole one.
 */
export function startBody(nodepool: string | null, replicas: number, servers: string[] = []): StartScaleRequest | null {
  const count = replicasOf(replicas);
  if (!nodepool || count === null) return null;
  return servers.length > 0 ? { nodepool, replicas: count, server_names: servers } : { nodepool, replicas: count };
}

/** The replicas a NodePool's change starts from: the day1 file's. */
export function currentOf(nodepool: string | null, nodepools: ScaleNodePool[]): number | null {
  if (!nodepool) return null;
  return nodepools.find((p) => p.name === nodepool)?.replicas ?? null;
}

/** `3 → 5`, with an unknown side as a dash. */
export const fromTo = (before: number | null, after: number | null) => `${before ?? "—"} → ${after ?? "—"}`;

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

/** What a run scaled, from its result: its NodePool, or the InfraEnv kind of a run recorded so before 2026-11-18. */
export function runTarget(result: { infra_env_kind: string | null; nodepool: string | null } | null): string | null {
  if (!result) return null;
  if (result.nodepool) return `NodePool ${result.nodepool}`;
  return result.infra_env_kind ? `kind ${result.infra_env_kind}` : null;
}

const NOTHING_DONE = "Nothing was marked or written.";

/** Why named servers were refused, by the workflow's words (its own stay shown above); the first that matches. */
const NAMED_REFUSALS: [RegExp, string][] = [
  [/predates/i, "The MCE's server-lifecycle worker is older than named servers and cannot tell which server a machine is: upgrade it, then run again."],
  [/unhealthy for CAPI/i, "This OpenShift's CAPI would take an unhealthy machine you did not pick in place of one you did: pick its server instead, or bring it back to health first."],
  [/more than one Machine/i, "Two machines of the NodePool are the same server, so which one leaves cannot be told."],
  [/no Machine of NodePool/i, "A picked server is not a machine of the NodePool now (the workflow lists its servers): read the nodes again and pick again."],
  [/more than once/i, "A server was picked twice."],
  [/Name exactly the servers that leave/i, "The servers picked are not as many as the scale-down removes."],
];

/** A plain line under a failed run's own words, for a failure that needs one; `null` for the rest. */
export function failureHint(errorType: string | null, error: string | null = null): string | null {
  if (errorType !== "ScaleDownServersInvalidError") return null;
  const known = NAMED_REFUSALS.find(([words]) => words.test(error ?? ""));
  if (known) return `${known[1]} ${NOTHING_DONE}`;
  return (
    "The servers named to leave cannot be the ones this scale-down removes: a wrong count, a server that is no machine " +
    `of the NodePool (or is two), an unhealthy machine CAPI would take instead, or an MCE worker too old to tell. ${NOTHING_DONE}`
  );
}

/**
 * The heading of a refused start, by its `code`; the problem's own words are listed under it. A 502 is neutral: its
 * words say whether the orchestrator could not be reached, failed, or has no update-nodepool deployed yet.
 */
export function refusalTitle(error: unknown): string {
  if (isApiError(error, "SCALE_ALREADY_RUNNING")) return "update-nodepool refused to start: a run of this cluster is going.";
  if (isApiError(error, "AMBIGUOUS_WRITE")) {
    return "The start was sent but not confirmed, so it may have started: the run is read again. Look at it before trying again.";
  }
  if (isApiError(error, "VALIDATION_ERROR")) return "Wingman refused the request.";
  if (isApiError(error, "DEPENDENCY_UNAVAILABLE")) return "Nothing started: the workflows orchestrator could not start update-nodepool.";
  if (isApiError(error, "FEATURE_DISABLED")) return "Scaling is not turned on in this deployment.";
  if (isApiError(error, "FORBIDDEN")) return "Only an admin can scale a cluster.";
  return "The scale did not start.";
}
