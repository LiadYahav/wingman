/**
 * Upgrading a cluster through the platform's upgrade-cluster workflow
 * (docs/notes/2026-11-13-upgrade-cluster-workflow-api.md, ADR-0055): the
 * Mastertag row's Upgrade and its dialog of the workflow's targets, the run's
 * panel on the Overview, and the decisions an admin sends, which the run's
 * validators judge. Upgrades off: nothing is shown. Every API is mocked.
 */
import { test, expect, type Page, type Request, type Route } from "@playwright/test";
import { fulfillProblem, go, held, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import type { ClusterDetail, UpgradeRun, UpgradeTargets } from "../../types";

const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const LARK = "ocp4-prod-lark-site1";
const POOL_A = "prod-lark-site1-dell-r660";
const POOL_B = "prod-lark-site1-dell-r760";

const DETAIL: ClusterDetail = {
  name: LARK, site: SITE, mce: MCE,
  yaml: 'owner:\n  merkaz: "1"\nmastertag: 4.18.22-x86_64\nnodepool: []\n',
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${LARK}.yaml`,
  last_commit_id: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
  metadata: {
    spec_name: null, spec_version: null, created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { merkaz: "1", anaf: "2", mador: "3" }, mastertag: "4.18.22-x86_64", platform: "agent", nodepools: [],
    network: { vlan_id: 1412, dhcp_network: "10.20.46.0", segment: "10.20.46.0/24" },
    cluster_name: null, automation_keys: [],
  },
  hosted_cluster: { cluster_name: "prod-lark-site1", name: "openshift-prod-lark-site1", namespace: "hcp-prod-lark-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "lark", sequence: null, problems: [] },
  mce_default_mastertag: "4.18.22-x86_64",
  problems: [],
  segments_manager: null,
};

const TARGETS: UpgradeTargets = {
  cluster: LARK, mce: MCE, mce_version: "2.8.2", control_plane_version: "4.18.22",
  supported_minors: ["4.18", "4.17", "4.16"], ladder_revision: "3f2a9c1", verified_against_graph: "2026-10-31",
  targets: [
    { version: "4.18.56", minor: "4.18", steps: 2, control_plane_steps: 1, newest_in_minor: true, must: true },
    { version: "4.18.40", minor: "4.18", steps: 2, control_plane_steps: 1, newest_in_minor: false, must: false },
  ],
  nodepools: [
    { name: POOL_A, workertag: null, upgrade_type: "InPlace", zone: null, replicas: 3, max_unavailable: null },
    { name: POOL_B, workertag: null, upgrade_type: "InPlace", zone: null, replicas: 2, max_unavailable: "1" },
  ],
  nodepool_order: [POOL_A, POOL_B],
};

const WAITING = "approve: 4.18.22 → 4.18.56 in 2 steps (control plane, then 2 NodePools)";

const run = (overrides: Partial<UpgradeRun> = {}): UpgradeRun => ({
  workflow_id: `upgrade-cluster-${LARK}`, cluster: LARK, status: "running", phase: "awaiting-approval", waiting_for: WAITING,
  mce: MCE,
  plan: {
    control_plane: "4.18.22", target: "4.18.56", max_worker_skew: 2, nodepools: { [POOL_A]: "4.18.22", [POOL_B]: "4.18.22" },
    steps: [
      { kind: "control-plane", version: "4.18.56", reason: "target", nodepools: [] },
      { kind: "workers", version: "4.18.56", reason: "final", nodepools: [POOL_A, POOL_B] },
    ],
  },
  profile: "generic", current_step: null, current_nodepool: null, nodepools_done: [], control_plane_version: "4.18.22",
  nodepool_versions: { [POOL_A]: "4.18.22", [POOL_B]: "4.18.22" }, max_unavailable: {}, paused: false, pending_actions: [],
  last_verdict: null, verified_against_graph: "2026-10-31",
  log: [{ at: "2026-11-13T10:00:00Z", event: "planned", by: "test-admin", detail: "2 steps" }],
  outcome: null, steps_completed: null, error: null, decisions: null,
  ...overrides,
});

/** The run day1 answers (`null`: 404, no run yet), and every write the page sent. */
interface Upgrades {
  run: UpgradeRun | null;
  writes: { path: string; body: unknown }[];
}

const UPGRADE_RUN = /\/api\/day1\/clusters\/[^/]+\/upgrade-run(\/[^?]*)?(\?.*)?$/;
const path = (request: Request) => new URL(request.url()).pathname;
const body = (request: Request): unknown => (request.postData() ? request.postDataJSON() : null);

/**
 * The cluster page; upgrades on unless `upgrades` is `null` (day1's 501, the
 * dashboard mocks' default). `decide` answers each decision (default: 200
 * with the run as it is).
 */
async function openCluster(
  page: Page,
  upgrades: Upgrades | null,
  { viewer = false, decide }: { viewer?: boolean; decide?: (route: Route, decision: string) => Promise<void> } = {}
) {
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
  await page.route(`**/api/day1/clusters/${LARK}?**`, (r) => json(r, DETAIL));
  await page.route(`**/api/day1/clusters/${LARK}/drift?**`, (r) =>
    json(r, {
      cluster: LARK, site: SITE, mce: MCE, state: "not_linked", is_drifted: false, spec_name: null, spec_version: null,
      current_spec_version: null, value_drift: [], addon_drift: [], version_differences: [], error: null,
    })
  );
  await page.route(`**/api/day2/clusters/${LARK}/history?**`, (r) => json(r, []));
  await page.route(`**/api/day2/clusters/${LARK}/addons?**`, (r) =>
    json(r, { cluster: LARK, mce: MCE, id: `hosted:${SITE}:prod:${MCE}:${LARK}`, kind: "hosted", site: SITE, env: "prod",
      ocp_version: "4.18.22", installed: [], excluded: [], warnings: [], argocd_note: "" })
  );
  await page.route("**/api/day2/addons", (r) => json(r, []));
  if (upgrades) await mockUpgradeRun(page, upgrades, decide);
  await go(page, `/clusters/${LARK}?site=${SITE}&mce=${MCE}`);
}

async function mockUpgradeRun(page: Page, upgrades: Upgrades, decide?: (route: Route, decision: string) => Promise<void>) {
  await page.route(UPGRADE_RUN, async (route) => {
    const request = route.request();
    if (request.method() === "GET") {
      return upgrades.run ? json(route, upgrades.run) : fulfillProblem(route, 404, "NOT_FOUND", `no upgrade run for cluster '${LARK}'`);
    }
    upgrades.writes.push({ path: path(request), body: body(request) });
    const decision = path(request).split("/upgrade-run/")[1];
    if (decide) return decide(route, decision);
    return json(route, { workflow_id: `upgrade-cluster-${LARK}`, decision, run: upgrades.run });
  });
}

test.describe("Upgrade a cluster through the upgrade-cluster workflow", () => {
  test("upgrades off: an admin sees Upgrade greyed out with why, and no panel", async ({ page }) => {
    await openCluster(page, null);
    await expect(page.getByText("4.18.22-x86_64").first()).toBeVisible();
    await expect(page.getByTestId("upgrade-action")).toHaveCount(0);
    const off = page.getByTestId("upgrade-action-off");
    await expect(off).toHaveAccessibleName("Upgrade is off: why");
    await off.hover();
    await expect(page.locator("[data-slot=tooltip-content][data-open]")).toHaveText("Upgrades are off on this Wingman (DAY1_UPGRADES=false).");
    await expect(page.getByTestId("upgrade-panel")).toHaveCount(0);
  });

  test("upgrades off: a viewer sees no Upgrade at all", async ({ page }) => {
    await openCluster(page, null, { viewer: true });
    await expect(page.getByText("4.18.22-x86_64").first()).toBeVisible();
    await expect(page.getByTestId("upgrade-action-off")).toHaveCount(0);
    await expect(page.getByTestId("upgrade-action")).toHaveCount(0);
  });

  test("the dialog lists the workflow's targets, and Start sends only the target", async ({ page }) => {
    const upgrades: Upgrades = { run: null, writes: [] };
    const targets = held();
    await page.route(/\/api\/day1\/clusters\/[^/]+\/upgrade-targets(\?.*)?$/, targets.answer(TARGETS));
    const starts: unknown[] = [];
    await page.route(/\/api\/day1\/clusters\/[^/]+\/upgrade(\?.*)?$/, (route) => {
      starts.push(body(route.request()));
      upgrades.run = run({ phase: null, waiting_for: null, plan: null, log: [] });
      return json(route, upgrades.run, 202);
    });
    await openCluster(page, upgrades);

    await page.getByTestId("upgrade-action").click();
    const dialog = page.getByTestId("upgrade-dialog");
    await expect(dialog.getByTestId("upgrade-targets-loading")).toContainText("up to a minute");
    targets.release();
    await expect(dialog.getByTestId("upgrade-target")).toHaveCount(2);
    await expect(dialog.getByTestId("upgrade-targets-facts")).toContainText("supports 4.18, 4.17, 4.16");
    await expect(dialog).toContainText("Nothing is committed before you approve");
    await expect(dialog.getByTestId("upgrade-nodepools").getByRole("listitem")).toHaveCount(2);
    await expect(dialog.getByTestId("upgrade-start")).toBeDisabled();

    await dialog.getByTestId("upgrade-target").filter({ hasText: "4.18.56" }).click();
    await dialog.getByTestId("upgrade-start").click();
    await expect(dialog).toHaveCount(0);
    await expect.poll(() => starts).toEqual([{ target_version: "4.18.56" }]);
    await expect(page.getByTestId("upgrade-panel")).toBeVisible();
    await expect(page.getByTestId("upgrade-phase")).toHaveText("Starting");
    await expect(page.getByTestId("upgrade-action")).toHaveCount(0);
  });

  test("no target newer: the dialog says so and offers no Start", async ({ page }) => {
    await page.route(/\/api\/day1\/clusters\/[^/]+\/upgrade-targets(\?.*)?$/, (r) => json(r, { ...TARGETS, targets: [] }));
    await openCluster(page, { run: null, writes: [] });
    await page.getByTestId("upgrade-action").click();
    await expect(page.getByTestId("upgrade-targets-empty")).toHaveText("Nothing newer to offer.");
    await expect(page.getByTestId("upgrade-start")).toHaveCount(0);
  });

  test("a run waiting for approval: its phase and words; Approve sends it and shows the run returned", async ({ page }) => {
    const upgrades: Upgrades = { run: run(), writes: [] };
    const after = run({
      phase: "control-plane-step", waiting_for: "the control plane to settle: 4.18.56", current_step: 0,
      log: [...run().log, { at: "2026-11-13T10:05:00Z", event: "approved", by: "test-admin", detail: "" }],
    });
    await openCluster(page, upgrades, {
      decide: (route, decision) => json(route, { workflow_id: `upgrade-cluster-${LARK}`, decision, run: after }),
    });

    const panel = page.getByTestId("upgrade-panel");
    await expect(panel.getByTestId("upgrade-phase")).toHaveText("Awaiting approval");
    await expect(panel.getByTestId("upgrade-waiting-for")).toHaveText(WAITING);
    await expect(panel.getByTestId("upgrade-step")).toHaveCount(2);
    await expect(page.getByTestId("upgrade-action")).toHaveCount(0);
    await expect(panel.getByTestId("upgrade-decisions").getByRole("button")).toHaveText(["Approve", "Pause", "Abort"]);

    await panel.getByTestId("upgrade-decision-approve").click();
    await page.getByTestId("upgrade-decision-submit").click();
    await expect(page.getByTestId("upgrade-decision-dialog")).toHaveCount(0);
    await expect.poll(() => upgrades.writes).toEqual([{ path: `/api/day1/clusters/${LARK}/upgrade-run/approve`, body: {} }]);
    await expect(panel.getByTestId("upgrade-phase")).toHaveText("Control plane step");
    await expect(panel.getByTestId("upgrade-step").first()).toHaveAttribute("data-state", "current");
    await expect(panel.getByTestId("upgrade-decisions").getByRole("button")).toHaveText(["Pause", "Abort"]);
  });

  test("a refused decision shows the run's own words, and is not sent again", async ({ page }) => {
    const words = "the run is not waiting for approve: it waits for confirm-day2: sync the ocp-versions/4.18 layer";
    const upgrades: Upgrades = { run: run(), writes: [] };
    await openCluster(page, upgrades, {
      decide: (route) => fulfillProblem(route, 409, "UPGRADE_DECISION_REFUSED", words),
    });
    await page.getByTestId("upgrade-decision-approve").click();
    await page.getByTestId("upgrade-decision-submit").click();
    const error = page.getByTestId("upgrade-decision-error");
    await expect(error).toContainText("The run refused it");
    await expect(error).toContainText(words);
    await expect(page.getByTestId("upgrade-decision-submit")).toBeDisabled();
    expect(upgrades.writes).toHaveLength(1);
  });

  test("Abort needs a reason, sends it, and the cancelled run frees Upgrade", async ({ page }) => {
    const upgrades: Upgrades = { run: run(), writes: [] };
    const cancelled = run({
      status: "completed", phase: null, waiting_for: null, outcome: "cancelled", steps_completed: 0,
    });
    await openCluster(page, upgrades, {
      decide: (route, decision) => {
        upgrades.run = cancelled;
        return json(route, { workflow_id: `upgrade-cluster-${LARK}`, decision, run: cancelled });
      },
    });
    await page.getByTestId("upgrade-decision-abort").click();
    const submit = page.getByTestId("upgrade-decision-submit");
    await expect(submit).toBeDisabled();
    await page.getByTestId("upgrade-decision-reason").fill("  wrong target  ");
    await expect(submit).toBeEnabled();
    await submit.click();
    // The click does not wait for the request: poll until the route has seen it
    await expect.poll(() => upgrades.writes).toEqual([
      { path: `/api/day1/clusters/${LARK}/upgrade-run/abort`, body: { reason: "wrong target" } },
    ]);
    const panel = page.getByTestId("upgrade-panel");
    await expect(panel.getByTestId("upgrade-phase")).toHaveText("Cancelled");
    await expect(panel.getByTestId("upgrade-outcome")).toContainText("0 of 2 steps ran");
    await expect(panel.getByTestId("upgrade-decisions")).toHaveCount(0);
    await expect(page.getByTestId("upgrade-action")).toBeVisible();
  });

  test("the NodePool rolling now opens the Nodes tab", async ({ page }) => {
    const rolling = run({
      phase: "nodepool-roll", waiting_for: null, current_step: 1, current_nodepool: POOL_A, control_plane_version: "4.18.56",
    });
    await openCluster(page, { run: rolling, writes: [] });
    const panel = page.getByTestId("upgrade-panel");
    await expect(panel.getByTestId("upgrade-step").first()).toHaveAttribute("data-state", "done");
    await panel.getByTestId("upgrade-current-nodepool").click();
    await expect(page.getByRole("tab", { name: "Nodes" })).toHaveAttribute("aria-selected", "true");
  });

  test("a viewer sees the run, with no decisions and no Upgrade", async ({ page }) => {
    await openCluster(page, { run: run(), writes: [] }, { viewer: true });
    await expect(page.getByTestId("upgrade-waiting-for")).toHaveText(WAITING);
    await expect(page.getByTestId("upgrade-decisions")).toHaveCount(0);
    await expect(page.getByTestId("upgrade-action")).toHaveCount(0);
  });

  test("a finished run's panel can be dismissed in this browser; the next run shows again", async ({ page }) => {
    const done = run({
      status: "completed", phase: null, waiting_for: null, outcome: "done", steps_completed: 2, control_plane_version: "4.18.56",
    });
    const upgrades: Upgrades = { run: done, writes: [] };
    await openCluster(page, upgrades);
    const panel = page.getByTestId("upgrade-panel");
    await expect(panel.getByTestId("upgrade-phase")).toHaveText("Done");
    await panel.getByTestId("upgrade-dismiss").click();
    await expect(panel).toHaveCount(0);
    await expect(page.getByTestId("upgrade-action")).toBeVisible();
    await page.reload();
    await expect(page.getByTestId("upgrade-action")).toBeVisible();
    await expect(page.getByTestId("upgrade-panel")).toHaveCount(0);
    expect(upgrades.writes).toEqual([]);

    upgrades.run = run({ log: [{ at: "2026-11-14T09:00:00Z", event: "planned", by: "test-admin", detail: "2 steps" }] });
    // The query cache is kept in the browser too: drop it, so the reload reads the new run
    await page.evaluate(() => window.localStorage.removeItem("wingman-query-cache"));
    await page.reload();
    await expect(page.getByTestId("upgrade-panel")).toBeVisible();
    await expect(page.getByTestId("upgrade-dismiss")).toHaveCount(0);
  });
});
