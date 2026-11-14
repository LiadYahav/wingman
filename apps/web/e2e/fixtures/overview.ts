/**
 * The Overview's mocks: a made-up fleet of clusters at two sites, on three
 * OpenShift versions, typed so a shape change fails `tsc`. The capacity and
 * fleet-health cards reuse the Inventory, Segments and Server Scan fixtures.
 */

import type { Page, Route } from "@playwright/test";
import { go, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "./api-handlers";
import type { ClusterStatus, FleetUpgrade } from "../../types";

export const SITE1_A = "ocp4-prod-mce-site1-a";
export const SITE1_B = "ocp4-prod-mce-site1-b";
const SITE2_A = "ocp4-prod-mce-site2-a";

function overviewCluster(
  name: string,
  site: string,
  mce: string,
  { mastertag = "4.18.22-x86_64", upgrade_available = null }: { mastertag?: string | null; upgrade_available?: string | null } = {}
): ClusterStatus {
  return {
    name, site, mce, phase: "Unknown", spec_name: null, spec_version: null, created_by: "alice",
    created_at: "2026-11-07T10:00:00+00:00", mastertag,
    path: `sites/${site}/mces/${mce}/hostedClusters/${name}.yaml`,
    hosted_cluster: { cluster_name: name.replace(/^ocp4-/, ""), name: name.replace(/^ocp4-/, ""), namespace: `hcp-${name.replace(/^ocp4-/, "")}` },
    naming: { follows_convention: true, env: "prod", short_name: "x", sequence: null, problems: [] },
    owner: {}, problems: [], upgrade_available,
  };
}

/** site1 holds four (three on MCE a), site2 one; two MCEs offer 4.18.56, one cluster sets no mastertag. */
const CLUSTERS: ClusterStatus[] = [
  overviewCluster("ocp4-prod-lark-site1", "site1", SITE1_A, { upgrade_available: "4.18.56" }),
  overviewCluster("ocp4-prod-owl-site1", "site1", SITE1_A, { upgrade_available: "4.18.56" }),
  overviewCluster("ocp4-prod-hawk-site1", "site1", SITE1_A, { mastertag: "4.17.9-x86_64" }),
  overviewCluster("ocp4-prod-wren-site1", "site1", SITE1_B, { mastertag: "4.18.40-x86_64" }),
  overviewCluster("ocp4-prod-kite-site2", "site2", SITE2_A, { mastertag: null }),
];

/** As day1 lists them while upgrades are off: no release is offered. */
export const UPGRADES_OFF = CLUSTERS.map((c) => ({ ...c, upgrade_available: null }));

/** LARK's upgrade is open. */
export const RUNS: FleetUpgrade[] = [{
  workflow_id: "upgrade-cluster-ocp4-prod-lark-site1", cluster: "ocp4-prod-lark-site1", site: "site1", mce: SITE1_A,
  status: "running", started_at: "2026-11-14T09:00:00+00:00", closed_at: null, phase: "planning",
  waiting_for: null, paused: false, outcome: null,
}];

type Handler = (route: Route) => Promise<void> | void;

/**
 * Sign in (as a viewer if asked), mock the dashboard's reads, then the
 * clusters and, when given, the fleet's upgrade runs (`GET /upgrades`; off
 * otherwise), and open the Overview. `before` registers a test's own routes
 * before the page opens: mocks match LIFO, so they win.
 */
export async function openOverview(
  page: Page,
  {
    clusters = CLUSTERS,
    upgrades,
    viewer = false,
    before,
  }: { clusters?: ClusterStatus[]; upgrades?: FleetUpgrade[] | Handler; viewer?: boolean; before?: (page: Page) => Promise<void> } = {}
) {
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters", (route) => json(route, clusters));
  if (upgrades) {
    await page.route("**/api/day1/upgrades", (route) => (typeof upgrades === "function" ? upgrades(route) : json(route, { runs: upgrades })));
  }
  await before?.(page);
  await go(page, "/");
}
