/**
 * Upgrades in the clusters list (mocked; ADR-0055's amendments,
 * docs/notes/2026-11-13-upgrade-cluster-workflow-api.md §3-4): each row's
 * state under its mastertag, "Upgrading · <phase>" with `waiting_for` in a
 * tooltip, or "Upgrade available → <version>" from day1's
 * `upgrade_available`; an admin's Upgrade on the row opens the cluster page's
 * dialog, without leaving the list; the Upgrades filter, kept in the URL.
 * No separate Upgrades view any more. Upgrades off: nothing of them.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import type { ClusterStatus, FleetUpgrade, UpgradeRun, UpgradeTargets } from "../../types";

const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const LARK = "ocp4-prod-lark-site1";
const OWL = "ocp4-prod-owl-site1";
const HAWK = "ocp4-prod-hawk-site1";
const HERON = "ocp4-prod-heron-site1";
const LONG_WAIT =
  "continue, once the customer's readiness checks after the last step pass: prod-lark-site1-dell-r760-site1-64c-512gb-20tb rolls next";

const cluster = (name: string, upgrade_available: string | null): ClusterStatus => ({
  name, site: SITE, mce: MCE, phase: "Unknown", spec_name: null, spec_version: null, created_by: "alice",
  created_at: "2026-11-07T10:00:00+00:00", mastertag: "4.18.22-x86_64",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${name}.yaml`,
  hosted_cluster: { cluster_name: name.replace(/^ocp4-/, ""), name: name, namespace: `hcp-${name}` },
  naming: { follows_convention: true, env: "prod", short_name: "x", sequence: null, problems: [] },
  owner: { merkaz: "1", anaf: "2", mador: "3" }, problems: [], upgrade_available,
});

/** LARK is upgrading (its MCE offers newer too), OWL and HAWK could be, HERON is up to date. */
const CLUSTERS = [cluster(LARK, "4.18.56"), cluster(OWL, "4.18.56"), cluster(HAWK, "4.18.56"), cluster(HERON, null)];
const OFF = CLUSTERS.map((c) => ({ ...c, upgrade_available: null }));

const fleetRun = (name: string, overrides: Partial<FleetUpgrade> = {}): FleetUpgrade => ({
  workflow_id: `upgrade-cluster-${name}`, cluster: name, site: SITE, mce: MCE, status: "running",
  started_at: new Date(Date.now() - 12 * 60_000).toISOString(), closed_at: null,
  phase: "awaiting-continue", waiting_for: LONG_WAIT, paused: false, outcome: null, ...overrides,
});

/** LARK's upgrade is open; HAWK's was cancelled, so HAWK may be upgraded again. */
const RUNS: FleetUpgrade[] = [
  fleetRun(LARK),
  fleetRun(HAWK, { status: "completed", phase: null, waiting_for: null, outcome: "cancelled", closed_at: new Date().toISOString() }),
];

const TARGETS = (name: string, versions: string[]): UpgradeTargets => ({
  cluster: name, mce: MCE, mce_version: "2.8.2", control_plane_version: "4.18.22",
  supported_minors: ["4.18", "4.17", "4.16"], ladder_revision: "3f2a9c1", verified_against_graph: "2026-10-31",
  targets: versions.map((version) => ({ version, minor: "4.18", steps: 1, control_plane_steps: 1, newest_in_minor: true, must: true })),
  nodepools: [], nodepool_order: [],
});

/**
 * The clusters list with upgrades on: `runs` (or `fleet`, any route handler)
 * from `GET /upgrades`, the workflow's targets per cluster, and a start that
 * adds its run to the list. Returns the starts sent.
 */
async function openClusters(
  page: Page,
  { runs = RUNS, fleet, viewer = false, path = "/clusters", clusters = CLUSTERS }:
    { runs?: FleetUpgrade[]; fleet?: (route: Route) => Promise<void>; viewer?: boolean; path?: string; clusters?: ClusterStatus[] } = {}
) {
  const listed = [...runs];
  const starts: { cluster: string; body: unknown }[] = [];
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters", (r) => json(r, clusters));
  await page.route("**/api/day1/upgrades", (route) => (fleet ? fleet(route) : json(route, { runs: listed })));
  await page.route(/\/api\/day1\/clusters\/[^/]+\/upgrade-targets(\?.*)?$/, (route) => {
    const name = new URL(route.request().url()).pathname.split("/")[4];
    return json(route, TARGETS(name, name === OWL ? [] : ["4.18.56", "4.18.40"]));
  });
  await page.route(/\/api\/day1\/clusters\/[^/]+\/upgrade(\?.*)?$/, (route) => {
    const name = new URL(route.request().url()).pathname.split("/")[4];
    starts.push({ cluster: name, body: route.request().postDataJSON() });
    const started = { workflow_id: `upgrade-cluster-${name}`, cluster: name, status: "running", phase: null, waiting_for: null,
      mce: null, paused: false, outcome: null } as UpgradeRun;
    listed.unshift(fleetRun(name, { phase: "planning", waiting_for: null }));
    return json(route, started, 202);
  });
  await go(page, path);
  return starts;
}

const row = (page: Page, name: string) => page.getByTestId(`cluster-row-${name}`);
const tooltip = (page: Page) => page.locator("[data-slot=tooltip-content][data-open]");

test.describe("Upgrades in the clusters list", () => {
  test("upgrades off: no state, no Upgrade, no filter, and no Upgrades view", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters", (r) => json(r, OFF));
    await go(page, "/clusters#upgrades");
    await expect(row(page, LARK)).toBeVisible();
    await expect(page.getByTestId("cluster-upgrading")).toHaveCount(0);
    await expect(page.getByTestId("cluster-upgrade-available")).toHaveCount(0);
    await expect(page.getByTestId("row-upgrade-action")).toHaveCount(0);
    await expect(page.getByRole("group", { name: "Upgrades filters" })).toHaveCount(0);
    await expect(page.getByRole("tablist")).toHaveCount(0);
  });

  test("the separate Upgrades view is gone: #upgrades is the clusters list", async ({ page }) => {
    await openClusters(page, { path: "/clusters#upgrades" });
    await expect(row(page, LARK)).toBeVisible();
    await expect(page.getByRole("tablist", { name: "Clusters views" })).toHaveCount(0);
    await expect(page.getByTestId("fleet-upgrade-row")).toHaveCount(0);
  });

  test("an upgrading row shows the phase, waiting_for in its tooltip, and opens its cluster", async ({ page }) => {
    await openClusters(page);
    const upgrading = row(page, LARK).getByTestId("cluster-upgrading");
    await expect(upgrading).toHaveText("Upgrading · Awaiting continue");
    await expect(row(page, LARK).getByTestId("cluster-upgrade-available")).toHaveCount(0);
    await expect(upgrading).toHaveAttribute("href", `/clusters/${LARK}?site=${SITE}&mce=${MCE}`);
    await upgrading.hover();
    await expect(tooltip(page)).toContainText(LONG_WAIT);
    await expect(tooltip(page)).toContainText("the decisions");
    await expect(page.getByTestId("upgrade-decisions")).toHaveCount(0);
  });

  test("a newer release on the MCE is suggested, and only that; up to date stays quiet", async ({ page }) => {
    await openClusters(page);
    const hint = row(page, OWL).getByTestId("cluster-upgrade-available");
    await expect(hint).toHaveText("Upgrade available → 4.18.56");
    // A finished run frees the cluster: HAWK is suggested again
    await expect(row(page, HAWK).getByTestId("cluster-upgrade-available")).toBeVisible();
    await expect(row(page, HAWK).getByTestId("cluster-upgrading")).toHaveCount(0);
    await expect(row(page, HERON).getByTestId("cluster-upgrade-available")).toHaveCount(0);
    await expect(row(page, HERON).getByTestId("row-upgrade-action")).toHaveCount(0);
    await hint.hover();
    await expect(tooltip(page)).toContainText(`MCE ${MCE} offers OpenShift 4.18.56, newer than this cluster's 4.18.22-x86_64`);
    await expect(tooltip(page)).toContainText("may offer other targets, or none");
  });

  test("Upgrade on a row opens the cluster page's dialog in place; once started the row is Upgrading", async ({ page }) => {
    const starts = await openClusters(page);
    await row(page, HAWK).getByTestId("row-upgrade-action").click();
    const dialog = page.getByTestId("upgrade-dialog");
    await expect(dialog).toContainText(`Upgrade ${HAWK}`);
    await expect(dialog.getByTestId("upgrade-target")).toHaveCount(2);
    await dialog.getByTestId("upgrade-target").filter({ hasText: "4.18.56" }).click();
    await dialog.getByTestId("upgrade-start").click();
    await expect(dialog).toHaveCount(0);
    await expect.poll(() => starts).toEqual([{ cluster: HAWK, body: { target_version: "4.18.56" } }]);
    await expect(page).toHaveURL(/\/clusters$/);
    await expect(row(page, HAWK).getByTestId("cluster-upgrading")).toContainText("Upgrading");
    await expect(row(page, HAWK).getByTestId("row-upgrade-action")).toHaveCount(0);
  });

  test("when the workflow then offers nothing, the dialog says so", async ({ page }) => {
    await openClusters(page);
    await row(page, OWL).getByTestId("row-upgrade-action").click();
    await expect(page.getByTestId("upgrade-targets-empty")).toHaveText("Nothing newer to offer.");
    await expect(page.getByTestId("upgrade-start")).toHaveCount(0);
  });

  test("a viewer sees the suggestion and the state, with no Upgrade", async ({ page }) => {
    await openClusters(page, { viewer: true });
    await expect(row(page, OWL).getByTestId("cluster-upgrade-available")).toBeVisible();
    await expect(row(page, LARK).getByTestId("cluster-upgrading")).toBeVisible();
    await expect(page.getByTestId("row-upgrade-action")).toHaveCount(0);
  });

  test("the Upgrades filter counts and filters each state, and is kept in the URL", async ({ page }) => {
    await openClusters(page);
    await expect(page.getByTestId("upgrade-filter-available")).toHaveText(/^Upgrade available\s*2$/);
    await expect(page.getByTestId("upgrade-filter-upgrading")).toHaveText(/^Upgrading\s*1$/);

    await page.getByTestId("upgrade-filter-upgrading").click();
    await expect(page).toHaveURL(/\/clusters\?upgrade=upgrading$/);
    await expect(page.locator("[data-testid^=cluster-row-]")).toHaveCount(1);
    await expect(row(page, LARK)).toBeVisible();

    await page.getByTestId("upgrade-filter-available").click();
    await expect(page).toHaveURL(/\/clusters\?upgrade=available$/);
    await expect(page.locator("[data-testid^=cluster-row-]")).toHaveCount(2);
    await page.reload();
    await expect(page.getByTestId("upgrade-filter-available")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("[data-testid^=cluster-row-]")).toHaveCount(2);
    await expect(row(page, HERON)).toHaveCount(0);

    await page.getByText("Clear filters").click();
    await expect(page).toHaveURL(/\/clusters$/);
    await expect(page.locator("[data-testid^=cluster-row-]")).toHaveCount(4);
  });

  test("runs the orchestrator can't list: the suggestions stay, and the filter says why", async ({ page }) => {
    await openClusters(page, {
      fleet: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "the orchestrator is unreachable listing upgrade runs"),
    });
    await expect(row(page, LARK).getByTestId("cluster-upgrade-available")).toBeVisible();
    await expect(page.getByTestId("cluster-upgrading")).toHaveCount(0);
    await expect(page.getByTestId("upgrade-runs-unknown")).toHaveAccessibleDescription(
      /could not be read, so no cluster shows Upgrading: the orchestrator is unreachable/
    );
  });
});
