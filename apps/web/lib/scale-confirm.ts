/**
 * What the scale confirmation says before update-nodepool starts (ADR-0062's
 * amendments), as pure functions. The workflow's design page is the
 * authority: these only put it in plain words. A run sets one NodePool;
 * which nodes a scale-down removes is that NodePool's scale-down policy, as
 * the day1 file sets it.
 */

import { fromTo } from "@/lib/scale-model";
import { plural } from "@/lib/utils";
import type { ScaleNodePool } from "@/types";

/** The policies update-nodepool knows, and which nodes each removes first; any other value it refuses. */
const PICKS: Record<string, string> = {
  "fewest-pods": "running the fewest pods",
  "least-requested": "with the lowest requested CPU or memory",
  "least-utilized": "with the lowest live CPU or memory use",
};

const UNHEALTHY_FIRST = "Unhealthy machines always go first.";

/** Which nodes a scale-down removes, in words. */
export interface Leaving {
  text: string;
  /** The workflow will refuse the run: the NodePool names a policy it does not know. */
  refused: boolean;
}

const known = (policy: string | null): policy is string => policy !== null && Object.hasOwn(PICKS, policy);

/** The scale-down policy the day1 file sets for a NodePool (`null`: none, or no such NodePool). */
export function policyOf(nodepool: string, nodepools: ScaleNodePool[]): string | null {
  return nodepools.find((p) => p.name === nodepool)?.scale_down_policy ?? null;
}

/** Under the title: `3 → 4 replicas (+1)`. */
export function changeLine(current: number, asked: number): string {
  const delta = asked - current;
  return `${fromTo(current, asked)} replicas (${delta > 0 ? "+" : "−"}${Math.abs(delta)})`;
}

/** What a scale-up adds: each new node takes a free server of the NodePool's hardware, or waits for one. */
export function addsLine(count: number): string {
  const takes = count === 1 ? "it takes" : "each takes";
  return `Adds ${plural(count, "node")}: ${takes} a free server of the NodePool's hardware; with none free, it waits until one is added.`;
}

/** When the run is done, as the workflow decides it. */
export const DONE_LINE = "Done when the NodePool shows the new size; new nodes join after they install.";

/** Which nodes a scale-down of `count` removes, by the NodePool's scale-down policy. */
export function leaving(count: number, policy: string | null): Leaving {
  const nodes = plural(count, "node");
  if (policy === null) {
    return { text: `Removes ${nodes}, picked at random by CAPI: the day1 file sets no scale-down policy. ${UNHEALTHY_FIRST}`, refused: false };
  }
  if (!known(policy)) {
    return {
      text: `Would remove ${nodes} by the scale-down policy “${policy}”, which the workflow does not know: the workflow will refuse it.`,
      refused: true,
    };
  }
  const which = count === 1 ? `the node ${PICKS[policy]}` : `the ${count} nodes ${PICKS[policy]}`;
  return { text: `Removes ${which} (${policy}). ${UNHEALTHY_FIRST}`, refused: false };
}
