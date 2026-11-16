/**
 * Scaling a cluster's NodePools through the platform's update-nodepool
 * workflow (ADR-0062), on the cluster page's Nodes tab: the NodePool sizes
 * from the day1 file, an admin's Scale by hardware kind (a total) or one
 * NodePool (its replicas), a review that says what the run does, the run in
 * place (the workflow's phases, its child's, the plan and the servers a
 * scale-down chose), refusals and failures in words, a NodePool whose
 * replicas a flavor locks, and a flavor sync's replicas restored by their own
 * run. Scaling off, or a viewer: no Scale. Every API is mocked.
 */
import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import type { ClusterDetail, ClusterDrift, ScaleOptions, ScaleRun, SyncPreview, UpgradeRun } from "../../types";

const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const LARK = "ocp4-prod-lark-site1";
const FLAVOR = "agent-dell";
const ZONE_A = "prod-lark-site1-dell-r660-site1-zone-a";
const ZONE_B = "prod-lark-site1-dell-r660-site1-zone-b";
const R760 = "prod-lark-site1-dell-r760-site1";
const RUN_ID = `update-nodepool-${LARK}`;

const DETAIL: ClusterDetail = {
  name: LARK, site: SITE, mce: MCE,
  yaml: `# specName: ${FLAVOR}\n# specVersion: 1.0.0\nmastertag: 4.18.22-x86_64\nnodepool: []\n`,
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${LARK}.yaml`,
  last_commit_id: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
  metadata: {
    spec_name: FLAVOR, spec_version: "1.0.0", created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { merkaz: "1" }, mastertag: "4.18.22-x86_64", platform: "agent", nodepools: [],
    network: { vlan_id: null, dhcp_network: null, segment: null }, cluster_name: null, automation_keys: [],
  },
  hosted_cluster: { cluster_name: "prod-lark-site1", name: "openshift-prod-lark-site1", namespace: "hcp-prod-lark-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "lark", sequence: null, problems: [] },
  mce_default_mastertag: "4.18.22-x86_64",
  problems: [],
  segments_manager: null,
};

/** Two zones of one kind, a locked NodePool whose file holds 3 (the flavor locks 2), and one that cannot be named. */
const OPTIONS: ScaleOptions = {
  cluster: LARK, mce: MCE, flavor: FLAVOR,
  nodepools: [
    { index: 0, name: ZONE_A, infra_env: "dell-r660-site1-zone-a", replicas: 3, locked_by: null, locked_replicas: null, unnamed: null },
    { index: 1, name: ZONE_B, infra_env: "dell-r660-site1-zone-b", replicas: 3, locked_by: null, locked_replicas: null, unnamed: null },
    { index: 2, name: R760, infra_env: "dell-r760-site1", replicas: 3, locked_by: FLAVOR, locked_replicas: 2, unnamed: null },
    {
      index: 3, name: null, infra_env: null, replicas: 1, locked_by: null, locked_replicas: null,
      unnamed: "nodepool[3] has neither name nor infraEnvName: its NodePool cannot be named",
    },
  ],
  kinds: [
    { kind: "dell-r660-site1-zone", nodepools: [ZONE_A, ZONE_B], total: 6, locked: [] },
    { kind: "dell-r660-site1-zone-a", nodepools: [ZONE_A], total: 3, locked: [] },
    { kind: "dell-r660-site1-zone-b", nodepools: [ZONE_B], total: 3, locked: [] },
    { kind: "dell-r760-site1", nodepools: [R760], total: 3, locked: [R760] },
  ],
};

const run = (overrides: Partial<ScaleRun> = {}): ScaleRun => ({
  workflow_id: RUN_ID, status: "running", phase: "pending", direction: null, child: null, result: null, error: null, error_type: null,
  ...overrides,
});

/** A scale-down of zone-b by fewest-pods, done: the plan, the server chosen and the commit. */
const DONE: ScaleRun = run({
  status: "completed", phase: "completed", direction: "down",
  result: {
    infra_env_kind: "dell-r660-site1-zone", nodepool: null, day1_path: DETAIL.path, direction: "down", total_before: 6, total_after: 5,
    nodepools: [
      { name: ZONE_A, infra_env: "dell-r660-site1-zone-a", before: 3, after: 3, scale_down_policy: null },
      { name: ZONE_B, infra_env: "dell-r660-site1-zone-b", before: 3, after: 2, scale_down_policy: "fewest-pods" },
    ],
    child_workflow_id: `scale-down-nodepool-${LARK}`, revision: "9f2c1ab77d0e5c3f", committed: true,
    live: [{ name: ZONE_B, replicas: 2, ready_replicas: 3 }],
    chosen: [{ nodepool: ZONE_B, machine: `${ZONE_B}-7xk2p`, node: "worker-7", policy: "fewest-pods", reason: "1 workload pods" }],
    deleting: [`${ZONE_B}-7xk2p`],
  },
});

const notDrifted: ClusterDrift = {
  cluster: LARK, site: SITE, mce: MCE, state: "in_sync", is_drifted: false, spec_name: FLAVOR, spec_version: "1.0.0",
  current_spec_version: "1.0.0", value_drift: [], addon_drift: [], version_differences: [], error: null, update: null,
};

/** What day1 answers on the scale routes, and what the page sent. */
interface Scale {
  options: ScaleOptions;
  run: ScaleRun | null;
  starts: unknown[];
  runReads: number;
  /** The start's answer (default: 202 with a running run). */
  start?: (route: Route) => Promise<void>;
}

const scaleOf = (overrides: Partial<Scale> = {}): Scale => ({ options: OPTIONS, run: null, starts: [], runReads: 0, ...overrides });

async function mockScale(page: Page, scale: Scale) {
  await page.route(`**/api/day1/clusters/${LARK}/scale?**`, async (route) => {
    if (route.request().method() === "GET") return json(route, scale.options);
    scale.starts.push(route.request().postDataJSON());
    if (scale.start) return scale.start(route);
    scale.run = run();
    return json(route, scale.run, 202);
  });
  await page.route(`**/api/day1/clusters/${LARK}/scale-run?**`, (route) => {
    scale.runReads += 1;
    return scale.run ? json(route, scale.run) : fulfillProblem(route, 404, "NOT_FOUND", `cluster '${LARK}' has no update-nodepool run`);
  });
}

/** The cluster page with scaling on (unless `scale` is `null`: day1's 501, the dashboard mocks' default), on its Nodes tab. */
async function openNodes(
  page: Page,
  scale: Scale | null,
  { viewer = false, upgrade, drift = notDrifted, tab = "nodes" }: { viewer?: boolean; upgrade?: UpgradeRun; drift?: ClusterDrift; tab?: string } = {}
) {
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
  await page.route(`**/api/day1/clusters/${LARK}?**`, (r) => json(r, DETAIL));
  await page.route(`**/api/day1/clusters/${LARK}/drift?**`, (r) => json(r, drift));
  await page.route(`**/api/day2/clusters/${LARK}/history?**`, (r) => json(r, []));
  await page.route(`**/api/day2/clusters/${LARK}/addons?**`, (r) =>
    json(r, { cluster: LARK, mce: MCE, id: `hosted:${SITE}:prod:${MCE}:${LARK}`, kind: "hosted", site: SITE, env: "prod",
      ocp_version: "4.18.22", installed: [], excluded: [], warnings: [], argocd_note: "" })
  );
  await page.route("**/api/day2/addons", (r) => json(r, []));
  if (upgrade) await page.route(/\/api\/day1\/clusters\/[^/]+\/upgrade-run(\?.*)?$/, (r) => json(r, upgrade));
  if (scale) await mockScale(page, scale);
  await go(page, `/clusters/${LARK}?site=${SITE}&mce=${MCE}&tab=${tab}`);
}

test.describe("Scale a cluster's NodePools through update-nodepool", () => {
  test("scaling off: no sizes and no Scale, and the Nodes tab is as before", async ({ page }) => {
    await openNodes(page, null);
    await expect(page.getByTestId("cluster-nodes-off")).toHaveText("Nodes need live status from the MCE (CLUSTER_STATUS_ENABLED).");
    await expect(page.getByTestId("scale-panel")).toHaveCount(0);
    await expect(page.getByTestId("scale-action")).toHaveCount(0);
  });

  test("a viewer sees the sizes and the run, with no Scale and no Restore", async ({ page }) => {
    await openNodes(page, scaleOf({ run: DONE }), { viewer: true });
    await expect(page.getByTestId("scale-panel")).toBeVisible();
    await expect(page.getByTestId("scale-pool-2")).toContainText(`Locked by flavor ${FLAVOR} at 2`);
    await expect(page.getByTestId("scale-run")).toBeVisible();
    await expect(page.getByTestId("scale-action")).toHaveCount(0);
    await expect(page.getByTestId("restore-replicas")).toHaveCount(0);
  });

  test("by hardware kind: a total over the NodePools it selects, sent as the kind's", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    // Live status is off: the sizes and Scale stay, from the day1 file
    await expect(page.getByTestId("cluster-nodes-off")).toBeVisible();
    await page.getByTestId("scale-action").click();
    const dialog = page.getByTestId("scale-dialog");
    // The first kind that can be scaled is chosen: the two zones together
    const zones = dialog.locator('[data-testid="scale-kind"][data-kind="dell-r660-site1-zone"]');
    await expect(zones.getByRole("radio")).toBeChecked();
    await expect(zones.getByRole("radio")).toHaveAccessibleName(/^dell-r660-site1-zone\s/);
    await expect(zones).toContainText("2 NodePools · 6 replicas");
    await expect(zones).toContainText(`${ZONE_A}, ${ZONE_B}`);
    // A kind that selects a locked NodePool is shown, not offered
    const locked = dialog.locator('[data-testid="scale-kind"][data-kind="dell-r760-site1"]');
    await expect(locked.getByRole("radio")).toBeDisabled();
    await expect(locked).toContainText(`Locked by flavor ${FLAVOR}: it selects ${R760}, whose replicas the flavor fixes.`);

    await dialog.getByTestId("scale-replicas").fill("8");
    await expect(dialog.getByText("now 6")).toBeVisible();
    await dialog.getByTestId("scale-review").click();
    await expect(dialog.getByRole("heading", { name: "Scale up?" })).toBeVisible();
    await expect(dialog.getByTestId("scale-change")).toContainText("6 → 8 replicas in total over 2 NodePools");
    const truths = dialog.getByTestId("scale-truths");
    await expect(truths).toContainText("One commit to day1 main that changes only the replicas lines, with no merge request.");
    await expect(truths).toContainText("syncs the cluster's Argo CD Application itself");
    await expect(truths).not.toContainText("scale-down-policy");
    await dialog.getByTestId("scale-start").click();

    await expect(dialog).toHaveCount(0);
    expect(scale.starts).toEqual([{ infra_env_kind: "dell-r660-site1-zone", replicas: 8 }]);
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    await expect(page.getByTestId("scale-action")).toBeDisabled();
    await expect(page.getByTestId("scale-busy-reason")).toContainText("An update-nodepool run of this cluster is running");
  });

  test("one NodePool: its exact replicas; a locked or unnamed one cannot be chosen", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    await page.getByTestId("scale-action").click();
    const dialog = page.getByTestId("scale-dialog");
    await dialog.getByTestId("scale-mode-nodepool").click();
    const r760 = dialog.locator(`[data-testid="scale-nodepool"][data-nodepool="${R760}"]`);
    await expect(r760.getByRole("radio")).toBeDisabled();
    await expect(r760).toContainText(`Locked by flavor ${FLAVOR} at 2.`);
    const unnamed = dialog.locator('[data-testid="scale-nodepool"][data-nodepool=""]');
    await expect(unnamed.getByRole("radio")).toBeDisabled();
    await expect(unnamed).toContainText("its NodePool cannot be named");

    await dialog.getByRole("radio", { name: new RegExp(ZONE_B) }).check();
    await dialog.getByTestId("scale-replicas").fill("3");
    await expect(dialog.getByTestId("scale-unchanged")).toHaveText("It already has 3 replicas: nothing to change.");
    await expect(dialog.getByTestId("scale-review")).toBeDisabled();
    await dialog.getByTestId("scale-replicas").fill("2");
    await dialog.getByTestId("scale-review").click();
    await expect(dialog.getByRole("heading", { name: "Scale down?" })).toBeVisible();
    await expect(dialog.getByTestId("scale-change")).toContainText(ZONE_B);
    await expect(dialog.getByTestId("scale-change")).toContainText("3 → 2 replicas");
    const truths = dialog.getByTestId("scale-truths");
    await expect(truths).toContainText("chosen by each NodePool's redbull.io/scale-down-policy; without one, CAPI picks them at random.");
    await expect(truths).toContainText("The freed servers stay in the MCE's inventory, as free Agents.");
    await dialog.getByTestId("scale-start").click();
    await expect(dialog).toHaveCount(0);
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 2 }]);
  });

  test("the run in place: the workflow's phase and its child's, then the plan and the servers chosen", async ({ page }) => {
    const scale = scaleOf({
      run: run({
        phase: "scaling-down", direction: "down",
        child: { workflow_id: `scale-down-nodepool-${LARK}`, status: "running", phase: "marking-machines", error: null },
      }),
    });
    await openNodes(page, scale);
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Scaling down · Marking machines");
    await expect(page.getByTestId("scale-run")).toContainText(`scale-down-nodepool-${LARK}`);
    await expect(page.getByTestId("scale-run")).toContainText("The workflow reports each NodePool before and after once it completes.");

    scale.run = DONE;
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    const card = page.getByTestId("scale-run");
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Completed");
    await expect(card.getByRole("heading", { level: 3, name: "Scale kind dell-r660-site1-zone" })).toBeVisible();
    await expect(page.getByTestId(`scale-run-pool-${ZONE_B}`)).toContainText("3 → 2");
    await expect(page.getByTestId(`scale-run-pool-${ZONE_B}`)).toContainText("fewest-pods");
    await expect(page.getByTestId(`scale-run-pool-${ZONE_A}`)).toContainText("none: CAPI picks at random");
    await expect(page.getByTestId("scale-run-total")).toContainText("6 → 5");
    await expect(page.getByTestId("scale-run-chosen")).toContainText(`worker-7 (${ZONE_B}-7xk2p) · ${ZONE_B} · fewest-pods: 1 workload pods`);
    await expect(page.getByTestId("scale-run-commit")).toContainText("Committed 9f2c1ab77d to day1 main");
  });

  test("a 409 is shown in the orchestrator's words, nothing is sent again, and the run is read again", async ({ page }) => {
    const words = `An update-nodepool run is already in flight for cluster ${LARK}`;
    const scale = scaleOf({ start: (route) => fulfillProblem(route, 409, "SCALE_ALREADY_RUNNING", words) });
    await openNodes(page, scale);
    await page.getByTestId("scale-action").click();
    const dialog = page.getByTestId("scale-dialog");
    await dialog.getByTestId("scale-replicas").fill("4");
    await dialog.getByTestId("scale-review").click();
    const reads = scale.runReads;
    await dialog.getByTestId("scale-start").click();
    const error = dialog.getByTestId("scale-error");
    await expect(error).toContainText("update-nodepool refused to start: a run of this cluster is going.");
    await expect(error).toContainText(words);
    await expect(dialog.getByTestId("scale-start")).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Close" })).toBeVisible();
    await expect.poll(() => scale.runReads).toBeGreaterThan(reads);
    expect(scale.starts).toHaveLength(1);
  });

  test("a failed run says why in the workflow's words, with its type", async ({ page }) => {
    const words = `scale-down-nodepool-${LARK} failed — ArgoSyncRefusedError: the Application ${LARK} has other changes pending. Its history has the detail`;
    await openNodes(page, scaleOf({ run: run({ status: "failed", phase: "scaling-down", direction: "down", error: words, error_type: "ArgoSyncRefusedError" }) }));
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Failed");
    const error = page.getByTestId("scale-run-error");
    await expect(error).toContainText("ArgoSyncRefusedError");
    await expect(error).toContainText(words);
    // A closed run does not hold Scale back
    await expect(page.getByTestId("scale-action")).toBeEnabled();
  });

  test("an open upgrade of the cluster holds Scale back, with why", async ({ page }) => {
    const upgrade = { workflow_id: `upgrade-cluster-${LARK}`, status: "running", phase: "awaiting-approval" } as UpgradeRun;
    await openNodes(page, scaleOf(), { upgrade });
    await expect(page.getByTestId("scale-action")).toBeDisabled();
    await expect(page.getByTestId("scale-busy-reason")).toContainText("An upgrade-cluster run of this cluster is open");
  });

  test("a locked NodePool that drifted is restored to its flavor's value by its own run", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    const row = page.getByTestId("scale-pool-2");
    await expect(row).toContainText(`Locked by flavor ${FLAVOR} at 2`);
    await row.getByRole("button", { name: `Restore ${R760} to 2 replicas with update-nodepool` }).click();
    const confirm = row.getByTestId("restore-confirm");
    await expect(confirm).toContainText(`Set NodePool ${R760} from 3 → 2 replicas, the value its flavor locks?`);
    await expect(confirm.getByTestId("scale-truths")).toContainText("scale-down-policy");
    await confirm.getByTestId("restore-start").click();
    await expect(row.getByTestId("restore-started")).toContainText(`update-nodepool started (${RUN_ID}): its run shows below.`);
    expect(scale.starts).toEqual([{ nodepool: R760, replicas: 2 }]);
  });
});

test.describe("A flavor sync leaves locked replicas to update-nodepool", () => {
  const drifted: ClusterDrift = {
    ...notDrifted, state: "drifted", is_drifted: true,
    value_drift: [{
      path: "nodepools[2].replicas", file_key: "nodepool[2].replicas", nodepool: { index: 2, name: R760 }, flavor_value: 2,
      cluster_value: 3, in_file: true, added: [], removed: [], needs_decision: null, needs_hardware: false, reboots: false,
    }],
  };
  const held: SyncPreview = {
    cluster: LARK, site: SITE, mce: MCE, path: DETAIL.path, last_commit_id: DETAIL.last_commit_id, spec_name: FLAVOR,
    spec_version: "1.0.0", file_spec_version: "1.0.0", changes: [], diff: "", removals: [], rebooting: [], problems: [],
    warnings: [], can_sync: false, addons_to_install: [], version_differences: [], addons_error: null,
    held_replicas: [{ index: 2, name: R760, replicas: 3, flavor_replicas: 2 }],
  };

  test("the preview lists the replicas the MR leaves out, each with a restore that sends the flavor's value", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { drift: drifted, tab: "drift" });
    await page.route(`**/api/day1/clusters/${LARK}/sync/preview?**`, (r) => json(r, held));
    await page.getByRole("button", { name: "Sync to flavor" }).click();

    const section = page.getByTestId("sync-held-replicas");
    await expect(section).toContainText("Not in this merge request: NodePool replicas");
    await expect(section.getByTestId("sync-held-2")).toContainText(`${R760} 3 → 2`);
    await expect(page.getByTestId("sync-blocked")).toHaveText("Nothing else to sync: the replicas above change through update-nodepool.");
    await section.getByRole("button", { name: `Restore ${R760} to 2 replicas with update-nodepool` }).click();
    await section.getByTestId("restore-start").click();
    await expect(section.getByTestId("restore-started")).toContainText(`update-nodepool started (${RUN_ID})`);
    expect(scale.starts).toEqual([{ nodepool: R760, replicas: 2 }]);
  });
});

// Screenshots for the review (SCALE_SCREENSHOTS=<dir>): the Scale dialog's review and a done run, light and dark.
const SHOTS = process.env.SCALE_SCREENSHOTS;
test.describe("Scale screenshots", () => {
  test.skip(!SHOTS, "only with SCALE_SCREENSHOTS");
  for (const scheme of ["light", "dark"] as const) {
    test(`dialog and run, ${scheme}`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      // The app starts dark (next-themes' defaultTheme); the person's choice is kept under `theme`
      await page.addInitScript((theme) => localStorage.setItem("theme", theme), scheme);
      await openNodes(page, scaleOf({ run: DONE }));
      await expect(page.getByTestId("scale-run")).toBeVisible();
      await page.getByTestId("scale-run").scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${SHOTS}/scale-run-${scheme}.png` });
      await page.getByTestId("scale-action").click();
      const dialog = page.getByTestId("scale-dialog");
      // After its enter animation, so the shot shows the dialog as a person reads it
      await dialog.evaluate((el) => Promise.all(el.getAnimations({ subtree: true }).map((a) => a.finished)));
      await page.screenshot({ path: `${SHOTS}/scale-dialog-choose-${scheme}.png` });
      await dialog.getByTestId("scale-replicas").fill("5");
      await dialog.getByTestId("scale-review").click();
      await expect(dialog.getByTestId("scale-start")).toBeEnabled();
      await page.screenshot({ path: `${SHOTS}/scale-dialog-review-${scheme}.png` });
    });
  }
});
