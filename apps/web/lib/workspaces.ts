/**
 * Wingman's two workspaces (ADR-0067). **Customers** is the tenants' side:
 * their hosted clusters, flavors, add-ons, approvals, audit and lints.
 * **Infrastructure**, for admins only, is what serves them: the Customer
 * MCEs and sites, the seeds and their KV clusters, Inventory Management
 * (herzi fills the customers' demand), Quick Links, and the systems the team
 * keeps apart from Wingman. A viewer is always in Customers and never sees
 * the switch; day1 refuses what Infrastructure reads to anyone else.
 */

import type { ClusterStatus, Mce } from "@/types";

export type WorkspaceId = "customers" | "infrastructure";

export interface Workspace {
  id: WorkspaceId;
  label: string;
  /** The workspace's home: where the top bar's switch goes. */
  href: string;
  /** What it holds, for the switch's tooltip and the docs. */
  description: string;
}

export const WORKSPACES: readonly Workspace[] = [
  {
    id: "customers",
    label: "Customers",
    href: "/",
    description: "The tenants' hosted clusters, flavors, add-ons and their changes",
  },
  {
    id: "infrastructure",
    label: "Infrastructure",
    href: "/infrastructure",
    description: "The MCEs, seeds, KV clusters and servers behind them",
  },
];

/** Pages only Infrastructure has; each is an admin's (day1 refuses a viewer). */
const INFRASTRUCTURE_PATHS = ["/infrastructure", "/mces", "/seeds", "/inventory", "/quick-links"] as const;
/** Pages both workspaces show, under Help: they keep the workspace you came from. */
const SHARED_PATHS = ["/docs", "/settings"] as const;

const under = (pathname: string, base: string) => pathname === base || pathname.startsWith(`${base}/`);

/** `/clusters/<name>` and below: one cluster's pages, whose workspace is the cluster's kind. */
export function clusterOfPath(pathname: string): string | null {
  const match = /^\/clusters\/([^/]+)/.exec(pathname);
  if (!match || match[1] === "new") return null;
  return decodeURIComponent(match[1]);
}

/**
 * The workspace a page is in. One cluster's pages follow its kind once it
 * is known (`kvCluster`): a KV cluster's are Infrastructure's, a tenant's
 * Customers'; until then, and on a shared page, `previous` stands. A viewer
 * is always in Customers.
 */
export function workspaceOf(
  pathname: string,
  { admin, kvCluster, previous = "customers" }: { admin: boolean; kvCluster?: boolean; previous?: WorkspaceId },
): WorkspaceId {
  if (!admin) return "customers";
  if (INFRASTRUCTURE_PATHS.some((base) => under(pathname, base))) return "infrastructure";
  if (clusterOfPath(pathname) !== null) {
    if (kvCluster === undefined) return previous;
    return kvCluster ? "infrastructure" : "customers";
  }
  if (SHARED_PATHS.some((base) => under(pathname, base))) return previous;
  return "customers";
}

/** A KV cluster, on a seed: day1's `kind` (a row without one is a tenant's). */
export const isKvCluster = (cluster: Pick<ClusterStatus, "kind">): boolean => cluster.kind === "kv";

/** The tenants' clusters: what the Customers workspace lists and counts. */
export const tenantClusters = <T extends Pick<ClusterStatus, "kind">>(clusters: readonly T[]): T[] =>
  clusters.filter((cluster) => !isKvCluster(cluster));

/** A seed, an MCE-level folder that hosts one zone's KV clusters: day1's `kind`. */
export const isSeed = (mce: Pick<Mce, "kind">): boolean => mce.kind === "seed";
