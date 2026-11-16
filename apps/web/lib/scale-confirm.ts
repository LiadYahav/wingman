/**
 * What the scale confirmation says before update-nodepool starts (ADR-0062's
 * amendments), as pure functions. The workflow's design page is the
 * authority: these only put it in plain words. Which nodes a scale-down
 * removes is each NodePool's scale-down policy, as the day1 file sets it.
 */

import { fromTo, type ScaleChange } from "@/lib/scale-model";
import { plural } from "@/lib/utils";
import type { ScaleOptions } from "@/types";

/** The policies update-nodepool knows, and which nodes each removes first; any other value it refuses. */
const PICKS: Record<string, string> = {
  "fewest-pods": "running the fewest pods",
  "least-requested": "with the lowest requested CPU or memory",
  "least-utilized": "with the lowest live CPU or memory use",
};

const UNHEALTHY_FIRST = "Unhealthy machines always go first.";

/** A NodePool the change may move, with its scale-down policy (`null`: the day1 file sets none). */
export interface PoolPolicy {
  nodepool: string;
  policy: string | null;
}

/** Which nodes a scale-down removes, in words: one line, and each NodePool's own when a hardware type's differ. */
export interface Leaving {
  text: string;
  /** Each NodePool and its policy in words, when they differ; else empty. */
  pools: { nodepool: string; words: string; refused: boolean }[];
  /** The workflow will refuse the run: a NodePool that loses nodes names a policy it does not know. */
  refused: boolean;
}

const known = (policy: string | null): policy is string => policy !== null && Object.hasOwn(PICKS, policy);

/** The NodePools a change may move: the one, or those a hardware type selects, with their policies. */
export function poolsOf(change: Pick<ScaleChange, "mode" | "target">, options: Pick<ScaleOptions, "nodepools" | "kinds">): PoolPolicy[] {
  const policyOf = (name: string) => options.nodepools.find((p) => p.name === name)?.scale_down_policy ?? null;
  const names = change.mode === "nodepool" ? [change.target] : (options.kinds.find((k) => k.kind === change.target)?.nodepools ?? []);
  return names.map((nodepool) => ({ nodepool, policy: policyOf(nodepool) }));
}

/** Under the title: `3 → 4 replicas (+1)`, or a hardware type's `5 → 7 in total over 2 NodePools; the workflow spreads it`. */
export function changeLine(mode: ScaleChange["mode"], current: number, asked: number, pools: number): string {
  if (mode === "kind") return `${fromTo(current, asked)} in total over ${plural(pools, "NodePool")}; the workflow spreads it`;
  const delta = asked - current;
  return `${fromTo(current, asked)} replicas (${delta > 0 ? "+" : "−"}${Math.abs(delta)})`;
}

/** What a scale-up adds: each new node takes a free server of the hardware, or waits for one. */
export function addsLine(count: number, mode: ScaleChange["mode"]): string {
  const hardware = mode === "kind" ? "this hardware type" : "the NodePool's hardware";
  return `Adds ${plural(count, "node")}: ${count === 1 ? "it takes" : "each takes"} a free server of ${hardware}; with none free, it waits until one is added.`;
}

/** When the run is done, as the workflow decides it. */
export const doneLine = (mode: ScaleChange["mode"]): string =>
  mode === "kind"
    ? "Done when the NodePools show the new sizes; new nodes join after they install."
    : "Done when the NodePool shows the new size; new nodes join after they install.";

/** One NodePool's policy in words, for a hardware type whose NodePools differ. */
function poolWords(policy: string | null): { words: string; refused: boolean } {
  if (policy === null) return { words: "picked at random by CAPI (the day1 file sets no policy)", refused: false };
  if (known(policy)) return { words: `the nodes ${PICKS[policy]} (${policy})`, refused: false };
  return { words: `“${policy}”, a policy the workflow does not know: it will refuse the run if this NodePool loses a node`, refused: true };
}

/**
 * Which nodes a scale-down of `count` removes, by the NodePools' scale-down
 * policies: one sentence when they agree, else one line per NodePool (the
 * workflow decides which of a hardware type's NodePools lose nodes).
 */
export function leaving(count: number, pools: PoolPolicy[]): Leaving {
  const policies = [...new Set(pools.map((p) => p.policy))];
  const nodes = plural(count, "node");
  if (policies.length > 1) {
    const each = pools.map((p) => ({ nodepool: p.nodepool, ...poolWords(p.policy) }));
    return {
      text: `Removes ${nodes}; in each NodePool that loses one, its own scale-down policy picks which. ${UNHEALTHY_FIRST}`,
      pools: each,
      refused: false,
    };
  }
  const policy = policies[0] ?? null;
  if (policy === null) {
    const these = pools.length > 1 ? " for these NodePools" : "";
    return { text: `Removes ${nodes}, picked at random by CAPI: the day1 file sets no scale-down policy${these}. ${UNHEALTHY_FIRST}`, pools: [], refused: false };
  }
  if (!known(policy)) {
    return {
      text: `Would remove ${nodes} by the scale-down policy “${policy}”, which the workflow does not know: the workflow will refuse it.`,
      pools: [],
      refused: true,
    };
  }
  const which = pools.length > 1 ? `${nodes}; in each NodePool, the nodes ${PICKS[policy]}` : count === 1 ? `the node ${PICKS[policy]}` : `the ${count} nodes ${PICKS[policy]}`;
  return { text: `Removes ${which} (${policy}). ${UNHEALTHY_FIRST}`, pools: [], refused: false };
}
