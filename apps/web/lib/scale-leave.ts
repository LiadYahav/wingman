/**
 * Which servers leave a scale-down (ADR-0062's last 2026-11-18 amendment), as
 * pure functions: one choice, and exactly one answer sent. The NodePool's own
 * policy sends nothing (the workflow reads it off the NodePool); another
 * policy for this run is `scale_down_policy`, ranked ahead of the NodePool's
 * own; picking the servers is `server_names`, exactly as many as leave. The
 * workflow's design page is the authority: these only put it in words.
 */

import { leaving, POLICIES, type Leaving } from "@/lib/scale-confirm";
import { pickedLeaving } from "@/lib/scale-servers";
import { plural } from "@/lib/utils";
import type { ScaleNodePool, ScaleResult, StartScaleRequest } from "@/types";

/** The three ways a scale-down's servers are chosen. */
export type LeaveChoice = "own" | "policy" | "servers";

/** What each policy removes first, in a few words, for the choice's list. */
export const POLICY_NOTES: Record<string, string> = {
  "fewest-pods": "the nodes running the fewest pods",
  "least-requested": "the nodes whose pods request the least CPU or memory",
  "least-utilized": "the nodes using the least CPU or memory now; needs the hosted cluster's metrics API",
};

/** The NodePool's own policy, as the day1 file sets it: `null` none, `undefined` no such NodePool. */
export function ownPolicy(nodepool: string, nodepools: ScaleNodePool[]): string | null | undefined {
  const pool = nodepools.find((p) => p.name === nodepool);
  return pool === undefined ? undefined : pool.scale_down_policy;
}

/** The policies another choice may be: all three but the NodePool's own. */
export const overrides = (own: string | null | undefined): string[] => POLICIES.filter((p) => p !== own);

/** The policy a run takes when "another policy" is chosen: the one picked, else the first offered. */
export const overrideOf = (picked: string | null, own: string | null | undefined): string =>
  picked !== null && overrides(own).includes(picked) ? picked : overrides(own)[0];

/** What the start adds for the choice: nothing for the NodePool's own, else its one field. Never on a scale-up. */
export function leaveFields(
  choice: LeaveChoice,
  count: number,
  servers: string[],
  policy: string
): Pick<StartScaleRequest, "server_names" | "scale_down_policy"> {
  if (count <= 0 || choice === "own") return {};
  return choice === "servers" ? { server_names: servers } : { scale_down_policy: policy };
}

/** Whether the choice can be sent: picked servers must be exactly as many as leave. */
export const leaveReady = (choice: LeaveChoice, picked: number, count: number): boolean =>
  count <= 0 || choice !== "servers" || picked === count;

/** The confirmation's main line for a scale-down of `count`: which nodes leave, by the choice. */
export function leaveLine(choice: LeaveChoice, count: number, own: string | null, policy: string, servers: string[]): Leaving {
  if (choice === "servers") {
    if (servers.length === count) return { text: pickedLeaving(servers), refused: false };
    return { text: `Removes the ${plural(count, "server")} you tick below.`, refused: false };
  }
  if (choice === "policy") return leaving(count, policy, true);
  return leaving(count, own);
}

/**
 * Which way a completed scale-down's servers were chosen, from its result: by name, by a policy (the NodePool's own
 * when it is the day1 file's, else this run's or one set on the NodePool itself), or at random. `own` is the day1
 * file's policy (`undefined` when it is not known). `null` for a run that did not scale down.
 */
export function runChoice(result: ScaleResult, own: string | null | undefined): string | null {
  if (result.direction !== "down") return null;
  if (result.chosen.some((c) => c.policy === "named")) return "Picked by name.";
  const shrunk = result.nodepools.find((np) => (np.after ?? 0) < (np.before ?? 0));
  const applied = shrunk?.scale_down_policy ?? null;
  if (applied === null) return "At random, by CAPI: no scale-down policy.";
  if (own === undefined) return `By ${applied}.`;
  if (applied === own) return `By ${applied}, the NodePool's own policy.`;
  return `By ${applied}, not the day1 file's policy (${own ?? "none"}): this run's choice, or one set on the NodePool itself.`;
}
