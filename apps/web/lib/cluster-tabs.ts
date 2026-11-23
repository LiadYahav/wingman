/**
 * The cluster page's tabs, and who gets the Nodes tab. A cluster's nodes,
 * the servers it runs on, are for admins (ADR-0038, amended 2026-11-23): day1
 * refuses a viewer's nodes read, and the page offers a viewer no Nodes tab.
 */

export const CLUSTER_TABS = ["overview", "nodes", "yaml", "drift", "history"] as const;
export type ClusterTab = (typeof CLUSTER_TABS)[number];

/** The tab `?tab=` asks for (a flavor's rollout links a cluster to its drift), else Overview. */
export function requestedTab(param: string | null): ClusterTab {
  return CLUSTER_TABS.find((tab) => tab === param) ?? "overview";
}

/**
 * Whether the page offers the Nodes tab. The role is only known in the
 * browser (the persisted auth store), once mounted: until then the tab is
 * drawn as the server drew it, so an admin's never flickers away; a viewer's
 * goes once the role is known.
 */
export function offersNodesTab({ mounted, isAdmin }: { mounted: boolean; isAdmin: boolean }): boolean {
  return !mounted || isAdmin;
}

/** The tab shown: Overview in place of a Nodes tab the page does not offer (a viewer's `?tab=nodes`). */
export function shownTab(tab: ClusterTab, nodesTab: boolean): ClusterTab {
  return tab === "nodes" && !nodesTab ? "overview" : tab;
}
