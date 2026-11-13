/**
 * The Clusters page's Upgrades view and its "Upgrading" badges (mocked;
 * ADR-0055's amendment, docs/notes/2026-11-13-upgrade-cluster-workflow-api.md
 * §3): every cluster's newest upgrade run from one day1 read, its status, the
 * workflow's phase made readable, `waiting_for` short with the whole text in
 * a tooltip, and when it started. Each row opens its cluster's page, where the
 * decisions are. Upgrades off: neither the view nor a badge.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import type { ClusterStatus, FleetUpgrade } from "../../types";

const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const LARK = "ocp4-prod-lark-site1";
const OWL = "ocp4-prod-owl-site1";
const HAWK = "ocp4-prod-hawk-site1";
const LONG_WAIT =
  "continue, once the customer's readiness checks after the last step pass: prod-lark-site1-dell-r760-site1-64c-512gb-20tb rolls next";

const cluster = (name: string): ClusterStatus => ({
  name, site: SITE, mce: MCE, phase: "Unknown", spec_name: null, spec_version: null, created_by: "alice",
  created_at: "2026-11-07T10:00:00+00:00", mastertag: "4.18.22-x86_64",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${name}.yaml`,
  hosted_cluster: { cluster_name: name.replace(/^ocp4-/, ""), name: name, namespace: `hcp-${name}` },
  naming: { follows_convention: true, env: "prod", short_name: "x", sequence: null, problems: [] },
  owner: { merkaz: "1", anaf: "2", mador: "3" }, problems: [],
});

const fleetRun = (name: string, overrides: Partial<FleetUpgrade> = {}): FleetUpgrade => ({
  workflow_id: `upgrade-cluster-${name}`, cluster: name, site: SITE, mce: MCE, status: "running",
  started_at: new Date(Date.now() - 12 * 60_000).toISOString(), closed_at: null,
  phase: "awaiting-continue", waiting_for: LONG_WAIT, paused: false, outcome: null, ...overrides,
});

const RUNS: FleetUpgrade[] = [
  fleetRun(LARK),
  fleetRun(OWL, { phase: "awaiting-approval", waiting_for: "approve: 4.18.22 → 4.18.56 in 2 steps" }),
  fleetRun(HAWK, { status: "completed", phase: null, waiting_for: null, outcome: "cancelled", closed_at: new Date().toISOString() }),
  fleetRun("ocp4-prod-gone-site1", { site: null, mce: null, status: "failed", phase: null, waiting_for: null }),
];

/** The clusters list with upgrades on and `runs` (or `answer`, any route handler); returns how often it was read. */
async function openClusters(
  page: Page,
  { runs = RUNS, answer, viewer = false, path = "/clusters" }: { runs?: FleetUpgrade[]; answer?: (route: Route) => Promise<void>; viewer?: boolean; path?: string } = {}
) {
  const reads = { count: 0 };
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters", (r) => json(r, [LARK, OWL, HAWK].map(cluster)));
  await page.route("**/api/day1/upgrades", (route) => {
    reads.count += 1;
    return answer ? answer(route) : json(route, { runs });
  });
  await go(page, path);
  return reads;
}

const tabs = (page: Page) => page.getByRole("tablist", { name: "Clusters views" });

test.describe("The Clusters page's Upgrades view", () => {
  test("upgrades off: no Upgrades tab and no badge", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters", (r) => json(r, [cluster(LARK)]));
    await go(page, "/clusters");
    await expect(page.getByTestId(`cluster-row-${LARK}`)).toBeVisible();
    await expect(tabs(page)).toHaveCount(0);
    await expect(page.getByTestId("cluster-upgrading")).toHaveCount(0);
  });

  test("the list badges each cluster whose upgrade is open, and the badge says where it is", async ({ page }) => {
    await openClusters(page);
    await expect(page.getByTestId(`cluster-row-${LARK}`).getByTestId("cluster-upgrading")).toHaveText("Upgrading");
    await expect(page.getByTestId(`cluster-row-${OWL}`).getByTestId("cluster-upgrading")).toBeVisible();
    await expect(page.getByTestId(`cluster-row-${HAWK}`).getByTestId("cluster-upgrading")).toHaveCount(0);
    await page.getByTestId(`cluster-row-${OWL}`).getByTestId("cluster-upgrading").hover();
    await expect(page.locator("[data-slot=tooltip-content][data-open]")).toContainText("Awaiting approval");
    await expect(page.getByTestId("upgrades-open-count")).toHaveText("2");
  });

  test("lists every cluster's run, open first, in the workflow's words, and links each to its cluster", async ({ page }) => {
    await openClusters(page);
    await tabs(page).getByRole("tab", { name: /Upgrades/ }).click();
    await expect(page).toHaveURL(/\/clusters#upgrades$/);
    const rows = page.getByTestId("fleet-upgrade-row");
    await expect(rows).toHaveCount(4);
    await expect(page.getByTestId("fleet-upgrades-summary")).toHaveText("2 upgrading · 4 clusters with a run");
    const lark = page.locator(`[data-cluster="${LARK}"]`);
    await expect(lark.getByTestId("fleet-upgrade-status")).toHaveText("running");
    await expect(lark.getByTestId("fleet-upgrade-phase")).toHaveText("Awaiting continue");
    const waiting = lark.getByTestId("fleet-upgrade-waiting");
    await expect(waiting).toContainText("…");
    await waiting.hover();
    await expect(page.locator("[data-slot=tooltip-content][data-open]")).toHaveText(LONG_WAIT);
    await expect(lark).toContainText("12 min ago");
    await expect(page.locator(`[data-cluster="${HAWK}"]`).getByTestId("fleet-upgrade-phase")).toHaveText("Cancelled");
    await expect(page.locator('[data-cluster="ocp4-prod-gone-site1"]')).toContainText("not in this day1 repo");
    await expect(page.getByTestId("upgrade-decisions")).toHaveCount(0);
    await expect(lark.getByRole("link", { name: LARK })).toHaveAttribute("href", `/clusters/${LARK}?site=${SITE}&mce=${MCE}`);
  });

  test("Back from the Upgrades view returns to the list, and #upgrades opens it", async ({ page }) => {
    await openClusters(page, { path: "/clusters#upgrades" });
    await expect(page.getByTestId("fleet-upgrade-row")).toHaveCount(4);
    await tabs(page).getByRole("tab", { name: "Clusters" }).click();
    await expect(page.getByTestId(`cluster-row-${LARK}`)).toBeVisible();
    await page.goBack();
    await expect(page.getByTestId("fleet-upgrade-row")).toHaveCount(4);
  });

  test("a viewer reads it too", async ({ page }) => {
    await openClusters(page, { viewer: true, path: "/clusters#upgrades" });
    await expect(page.getByTestId("fleet-upgrade-row")).toHaveCount(4);
  });

  test("no runs: the view says so and how one starts", async ({ page }) => {
    await openClusters(page, { runs: [], path: "/clusters#upgrades" });
    await expect(page.getByTestId("fleet-upgrades-empty")).toContainText("Upgrade on a cluster's Mastertag row");
    await expect(page.getByTestId("upgrades-open-count")).toHaveCount(0);
  });

  test("an orchestrator that does not answer is shown, not an empty list", async ({ page }) => {
    await openClusters(page, {
      path: "/clusters#upgrades",
      answer: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "the orchestrator is unreachable listing upgrade runs"),
    });
    await expect(page.getByText("The upgrade runs could not be read")).toBeVisible();
    await expect(page.getByText("the orchestrator is unreachable listing upgrade runs")).toBeVisible();
    await expect(page.getByTestId("fleet-upgrades-empty")).toHaveCount(0);
  });
});
