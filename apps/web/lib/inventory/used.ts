/**
 * herzi's used Agents (ADR-0057's 3.55.0 amendment): free Agents that carry
 * a used-Agent label (herzi's `redbull.io/ever-installed`, or the
 * deployment's excluded labels). No NodePool that excludes the label takes
 * one, and herzi takes it out of the MCE, so day1 never counts it as
 * available. This is the page's words for them, and for the NodePools that
 * do not exclude the label yet. The numbers are day1's.
 */

import type { MceInventory, UnguardedNodepool, UsedLabels } from "@/types/inventory";

/** `redbull.io/ever-installed`, or the deployment's keys joined. */
const keysText = (labels: UsedLabels): string => labels.keys.join(", ");

/** The tooltip of a used count: which servers, and why they are not available. */
export function usedHint(labels: UsedLabels, servers: string[], paused = false): string {
  const named = servers.length > 0 ? `: ${servers.join(", ")}` : "";
  const held = paused ? " herzi is paused on this pool, so it removes none of them until it is resumed." : "";
  return `Used, waiting for herzi to remove${named}. Each was installed in a cluster and is free again, labelled ${keysText(labels)}: no NodePool that excludes the label takes it, and herzi takes it out of the MCE (remove-server-from-mce). Not counted as available or in the total.${held}`;
}

/**
 * Whether the MCE's NodePools that lack the exclusion are worth a notice:
 * the deployment excludes the label (its rollout is under way), or herzi has
 * used Agents here that it removes only once every NodePool excludes it.
 */
export function showUnguarded(mce: MceInventory, labels: UsedLabels): boolean {
  return mce.unguarded.length > 0 && (labels.source === "setting" || (mce.used ?? 0) > 0);
}

export interface UnguardedCluster {
  cluster: string;
  nodepools: UnguardedNodepool[];
}

/** The NodePools by cluster, in day1's order. */
export function byCluster(pools: UnguardedNodepool[]): UnguardedCluster[] {
  const groups = new Map<string, UnguardedCluster>();
  for (const pool of pools) {
    const group = groups.get(pool.cluster) ?? { cluster: pool.cluster, nodepools: [] };
    group.nodepools.push(pool);
    groups.set(pool.cluster, group);
  }
  return [...groups.values()];
}

const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

/** `3 NodePools in 2 clusters do not exclude redbull.io/ever-installed`. */
export function unguardedSummary(mce: MceInventory, labels: UsedLabels): string {
  const clusters = byCluster(mce.unguarded).length;
  const pools = mce.unguarded.length;
  const verb = pools === 1 ? "does" : "do";
  return `${plural(pools, "NodePool", "NodePools")} in ${plural(clusters, "cluster", "clusters")} ${verb} not exclude ${keysText(labels)}`;
}

/** Why it matters, and how a cluster takes the exclusion. */
export function unguardedHint(labels: UsedLabels): string {
  return `herzi removes a used Agent only once every NodePool that could take it excludes ${keysText(labels)}; until then such a NodePool may bind it again. Each cluster takes the exclusion through its own merge request (ADR-0065), never all at once. A Replace NodePool is left out of it, since every node would be replaced: change it to InPlace first.`;
}
