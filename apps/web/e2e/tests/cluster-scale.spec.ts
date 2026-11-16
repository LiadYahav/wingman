/**
 * Scaling a cluster's NodePools through the platform's update-nodepool
 * workflow (ADR-0062 and its 2026-11-16 amendment), on the cluster page's
 * Nodes tab: a stepper on each NodePool's card from the MCE (its exact
 * replicas, matched by name), or on its NodePool sizes row when there are no
 * cards (live status off); a hardware type's total in a small dialog; one
 * change at a time, Scale up at once and Scale down after a question in
 * place; the run in place (the workflow's phases, its child's, the plan and
 * the servers a scale-down chose), refusals and failures in words, a
 * NodePool whose replicas a flavor locks, and a flavor sync's replicas
 * restored by their own run. Scaling off, or a viewer: no steppers. Every
 * API is mocked.
 */
import { test, expect, type Page, type Route } from "@playwright/test";
import {
  fulfillProblem, go, injectAdminAuth, injectViewerAuth, json, mockClusterNodes, mockDashboardApis, mockNodePool, mockNodes,
} from "../fixtures/api-handlers";
import type { ClusterDetail, ClusterDrift, ClusterNodes, ScaleOptions, ScaleRun, SyncPreview, UpgradeRun } from "../../types";

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

/**
 * Two zones of one kind (zone-b removes its nodes by fewest-pods, zone-a has no policy), a locked NodePool whose
 * file holds 3 (the flavor locks 2), and one that cannot be named.
 */
const OPTIONS: ScaleOptions = {
  cluster: LARK, mce: MCE, flavor: FLAVOR,
  nodepools: [
    {
      index: 0, name: ZONE_A, infra_env: "dell-r660-site1-zone-a", replicas: 3, locked_by: null, locked_replicas: null, unnamed: null,
      scale_down_policy: null,
    },
    {
      index: 1, name: ZONE_B, infra_env: "dell-r660-site1-zone-b", replicas: 3, locked_by: null, locked_replicas: null, unnamed: null,
      scale_down_policy: "fewest-pods",
    },
    {
      index: 2, name: R760, infra_env: "dell-r760-site1", replicas: 3, locked_by: FLAVOR, locked_replicas: 2, unnamed: null,
      scale_down_policy: null,
    },
    {
      index: 3, name: null, infra_env: null, replicas: 1, locked_by: null, locked_replicas: null,
      unnamed: "nodepool[3] has neither name nor infraEnvName: its NodePool cannot be named", scale_down_policy: null,
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

/**
 * The cluster page with scaling on (unless `scale` is `null`: day1's 501, the
 * dashboard mocks' default), on its Nodes tab. Live status is off unless
 * `nodes` gives the MCE's NodePools, shown as cards.
 */
async function openNodes(
  page: Page,
  scale: Scale | null,
  { viewer = false, upgrade, drift = notDrifted, tab = "nodes", nodes }: {
    viewer?: boolean; upgrade?: UpgradeRun; drift?: ClusterDrift; tab?: string; nodes?: ClusterNodes;
  } = {}
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
  if (nodes) await mockClusterNodes(page, LARK, nodes);
  await go(page, `/clusters/${LARK}?site=${SITE}&mce=${MCE}&tab=${tab}`);
}

/** A NodePool's or a hardware type's stepper, by the name its group says. */
const stepper = (page: Page, name: string) => page.getByRole("group", { name: `${name} replicas`, exact: true });
const field = (page: Page, name: string) => stepper(page, name).getByRole("spinbutton");
const more = (page: Page, name: string) => page.getByRole("button", { name: `One replica more for ${name}`, exact: true });
const fewer = (page: Page, name: string) => page.getByRole("button", { name: `One replica fewer for ${name}`, exact: true });
const ZONES = "dell-r660-site1-zone";
const card = (page: Page, name: string) => page.getByTestId(`node-pool-${name}`);

/** The MCE's NodePools as cards: the two zones, the locked r760, and one the day1 file does not name. */
const CARDS = mockNodes({
  hosted_cluster: "prod-lark-site1",
  node_pools: [ZONE_A, ZONE_B, R760, "prod-lark-site1-extra"].map((name) => mockNodePool({ name, ready: 3, wanted: 3 })),
});

test.describe("Scale a cluster's NodePools through update-nodepool", () => {
  test("scaling off: no sizes and no steppers, and the Nodes tab is as before", async ({ page }) => {
    await openNodes(page, null);
    await expect(page.getByTestId("cluster-nodes-off")).toHaveText("Nodes need live status from the MCE (CLUSTER_STATUS_ENABLED).");
    await expect(page.getByTestId("scale-panel")).toHaveCount(0);
    await expect(page.getByTestId("scale-stepper")).toHaveCount(0);
  });

  test("a viewer sees the sizes and the run, with no steppers, no Restore and no hardware type", async ({ page }) => {
    await openNodes(page, scaleOf({ run: DONE }), { viewer: true });
    await expect(page.getByTestId("scale-pool-0")).toContainText("3 replicas");
    await expect(page.getByTestId("scale-pool-2")).toContainText(`Locked by flavor ${FLAVOR} at 2`);
    await expect(page.getByTestId("scale-pool-3")).toContainText(/1 replica(?!s)/);
    await expect(page.getByTestId("scale-run")).toBeVisible();
    await expect(page.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(page.getByTestId("scale-kind-action")).toHaveCount(0);
    await expect(page.getByTestId("restore-replicas")).toHaveCount(0);
  });

  test("live status off: each NodePool scales on its sizes row; Scale up sends its exact replicas, once", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    await expect(page.getByTestId("cluster-nodes-off")).toBeVisible();
    await expect(field(page, ZONE_A)).toHaveValue("3");
    await more(page, ZONE_A).click();
    await expect(field(page, ZONE_A)).toHaveValue("4");
    await expect(stepper(page, ZONE_A)).toHaveAttribute("data-changed", "true");
    const pending = page.getByTestId("scale-pool-0").getByTestId("scale-pending");
    await expect(pending.getByTestId("scale-change")).toHaveText("Replicas 3 → 4 (+1)");
    await expect(pending).toContainText("One commit to day1 main; the workflow syncs Argo CD itself.");
    await expect(page.getByTestId("scale-announce")).toHaveText(`${ZONE_A}: 3 → 4 (+1)`);
    await expect(page.getByTestId("scale-announce")).toHaveAttribute("role", "status");
    await expect(pending.getByTestId("scale-start")).toHaveText("Scale up");

    // A scale-up starts at once; the second click of a double-click sends nothing
    await pending.getByTestId("scale-start").dblclick();
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    expect(scale.starts).toEqual([{ nodepool: ZONE_A, replicas: 4 }]);
    await expect(page.getByTestId("scale-run")).toBeFocused();
    // The run holds every stepper, and says why once
    const why = "An update-nodepool run of this cluster is running";
    await expect(page.getByTestId("scale-busy-reason")).toContainText(why);
    await expect(page.getByText(why)).toHaveCount(1);
    // Nothing looks editable while it runs: each size is text
    await expect(page.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(page.getByTestId("scale-pool-0")).toContainText("3 replicas");
    await expect(page.getByTestId("scale-pending")).toHaveCount(0);
    await expect(page.getByTestId("scale-kind-action")).toBeDisabled();
  });

  test("a number can be typed, and the arrow keys step it by one", async ({ page }) => {
    await openNodes(page, scaleOf());
    const b = field(page, ZONE_B);
    const change = page.getByTestId("scale-change");
    await b.fill("5");
    await expect(change).toHaveText("Replicas 3 → 5 (+2)");
    await b.press("ArrowDown");
    await expect(b).toHaveValue("4");
    await b.press("ArrowUp");
    await b.press("ArrowUp");
    await expect(b).toHaveValue("6");
    await expect(change).toHaveText("Replicas 3 → 6 (+3)");
    await b.fill("");
    await expect(change).toHaveText("Replicas are a whole number from 0 to 500.");
    await expect(b).toHaveAttribute("aria-invalid", "true");
    await expect(page.getByTestId("scale-start")).toBeDisabled();
    // Back at its value now: nothing to send
    await b.fill("3");
    await expect(page.getByTestId("scale-pending")).toHaveCount(0);
  });

  test("one change at a time: changing a stepper, or a hardware type's total, puts every other back", async ({ page }) => {
    await openNodes(page, scaleOf());
    await more(page, ZONE_A).click();
    await fewer(page, ZONE_B).click();
    await expect(field(page, ZONE_A)).toHaveValue("3");
    await expect(field(page, ZONE_B)).toHaveValue("2");
    await expect(page.getByTestId("scale-pending")).toHaveCount(1);
    await expect(page.getByTestId("scale-pool-1").getByTestId("scale-change")).toHaveText("Replicas 3 → 2 (−1)");

    // The hardware type's total is the change now
    await page.getByTestId("scale-kind-action").click();
    const dialog = page.getByTestId("scale-kind-dialog");
    await more(page, ZONES).click();
    await expect(dialog.getByTestId("scale-change")).toHaveText("6 → 7 (+1)");
    await expect(page.getByTestId("scale-announce")).toHaveText(`${ZONES} total: 6 → 7 (+1)`);
    await expect(page.locator('[data-testid="scale-stepper"][data-changed="true"]')).toHaveCount(1);
    await expect(page.getByTestId("scale-pending")).toHaveCount(0);
    // Cancel drops it, and returns to the button that opened it
    await dialog.getByTestId("scale-kind-cancel").click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByTestId("scale-kind-action")).toBeFocused();
    await expect(field(page, ZONE_B)).toHaveValue("3");
    await expect(page.locator('[data-testid="scale-stepper"][data-changed="true"]')).toHaveCount(0);

    // A NodePool's Cancel returns to its field
    await more(page, ZONE_A).click();
    await page.getByTestId("scale-cancel").click();
    await expect(field(page, ZONE_A)).toHaveValue("3");
    await expect(field(page, ZONE_A)).toBeFocused();
  });

  test("a scale-down asks first, in place, and is sent only from there", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    await fewer(page, ZONE_B).click();
    const pending = page.getByTestId("scale-pending");
    await expect(pending.getByTestId("scale-start")).toHaveText("Scale down");
    await pending.getByTestId("scale-start").click();
    const confirm = pending.getByTestId("scale-confirm");
    await expect(confirm).toBeFocused();
    await expect(confirm).toContainText("Scale down by 1 replica?");
    const truths = confirm.getByTestId("scale-truths");
    await expect(truths).toContainText("chosen by each NodePool's redbull.io/scale-down-policy; without one, CAPI picks them at random.");
    await expect(truths).toContainText("The freed servers stay in the MCE's inventory, as free Agents.");
    expect(scale.starts).toEqual([]);

    // Back, or Escape, returns with nothing sent
    await confirm.getByTestId("scale-back").click();
    await expect(confirm).toHaveCount(0);
    await expect(pending.getByTestId("scale-start")).toBeFocused();
    await pending.getByTestId("scale-start").click();
    await expect(confirm).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(confirm).toHaveCount(0);
    expect(scale.starts).toEqual([]);

    await pending.getByTestId("scale-start").click();
    await confirm.getByTestId("scale-confirm-start").click();
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 2 }]);
  });

  test("a locked NodePool has no stepper: its size as text, why and a restore; an unnamed one has none either", async ({ page }) => {
    await openNodes(page, scaleOf());
    const row = page.getByTestId("scale-pool-2");
    await expect(row.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(row).toContainText("3 replicas");
    await expect(row.getByTestId("scale-pool-locked")).toHaveText(`Locked by flavor ${FLAVOR} at 2.`);
    await expect(row.getByRole("button", { name: `Restore ${R760} to 2 replicas with update-nodepool` })).toBeVisible();
    const unnamed = page.getByTestId("scale-pool-3");
    await expect(unnamed.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(unnamed).toContainText("its NodePool cannot be named");
  });

  test("a hardware type's total, in its dialog: spread by the workflow, sent as the kind's", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    await page.getByTestId("scale-kind-action").click();
    const dialog = page.getByTestId("scale-kind-dialog");
    await expect(dialog.getByRole("heading", { name: "Scale a hardware type" })).toBeVisible();
    // Only the types over two or more NodePools: the r760's has one
    await expect(dialog.getByTestId("scale-kind")).toHaveCount(1);
    await expect(dialog.getByRole("radio", { name: new RegExp(`^${ZONES}`) })).toBeChecked();
    await expect(dialog.getByTestId("scale-kind")).toContainText("2 NodePools · 6 replicas");
    await expect(field(page, ZONES)).toHaveValue("6");
    await more(page, ZONES).click();
    await more(page, ZONES).click();
    await expect(dialog.getByTestId("scale-change")).toHaveText("6 → 8 (+2)");
    await dialog.getByTestId("scale-start").click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    expect(scale.starts).toEqual([{ infra_env_kind: ZONES, replicas: 8 }]);
    await expect(page.getByTestId("scale-run")).toBeFocused();
  });

  test("a hardware type's scale-down asks in the same dialog", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    await page.getByTestId("scale-kind-action").click();
    const dialog = page.getByTestId("scale-kind-dialog");
    await field(page, ZONES).fill("5");
    await expect(dialog.getByTestId("scale-change")).toHaveText("6 → 5 (−1)");
    await dialog.getByTestId("scale-start").click();
    const confirm = dialog.getByTestId("scale-confirm");
    await expect(confirm).toContainText(`Scale down ${ZONES} by 1 replica?`);
    await expect(confirm.getByTestId("scale-truths")).toContainText("scale-down-policy");
    expect(scale.starts).toEqual([]);
    await confirm.getByTestId("scale-confirm-start").click();
    await expect(dialog).toHaveCount(0);
    expect(scale.starts).toEqual([{ infra_env_kind: ZONES, replicas: 5 }]);
  });

  test("a hardware type that selects a locked NodePool cannot be scaled; with none over two NodePools, no button", async ({ page }) => {
    const lockedB: ScaleOptions = {
      ...OPTIONS,
      nodepools: OPTIONS.nodepools.map((p) => (p.name === ZONE_B ? { ...p, locked_by: FLAVOR, locked_replicas: 3 } : p)),
      kinds: OPTIONS.kinds.map((k) => (k.kind === ZONES ? { ...k, locked: [ZONE_B] } : k)),
    };
    const scale = scaleOf({ options: lockedB });
    await openNodes(page, scale);
    await page.getByTestId("scale-kind-action").click();
    const dialog = page.getByTestId("scale-kind-dialog");
    const radio = dialog.getByRole("radio", { name: new RegExp(`^${ZONES}`) });
    await expect(radio).toBeDisabled();
    await expect(radio).toHaveAccessibleDescription(`Locked by flavor ${FLAVOR}: it selects ${ZONE_B}, whose replicas the flavor fixes.`);
    // Listed, not offered: its total as text, no stepper
    await expect(dialog.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(dialog.getByTestId("scale-kind-total")).toHaveText("Total 6 replicas");
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);

    scale.options = { ...OPTIONS, kinds: OPTIONS.kinds.filter((k) => k.nodepools.length < 2) };
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await expect(stepper(page, ZONE_A)).toBeVisible();
    await expect(page.getByTestId("scale-kind-action")).toHaveCount(0);
  });

  test("live status on: each NodePool scales on its card, and the sizes fold to a line", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    await expect(page.getByTestId("scale-summary")).toContainText("4 NodePools, 10 replicas, as the day1 file sets them; each card below scales its own.");
    // Only the entry no card shows stays a row
    await expect(page.getByTestId("scale-pool-0")).toHaveCount(0);
    await expect(page.getByTestId("scale-pool-3")).toContainText("its NodePool cannot be named");
    await expect(stepper(page, ZONE_A)).toHaveCount(1);

    const a = card(page, ZONE_A);
    await expect(a.getByTestId("scale-card-control")).toContainText("Replicas");
    await expect(a.getByTestId("node-pool-ready")).toContainText("3 / 3 ready");
    await a.getByRole("button", { name: `One replica more for ${ZONE_A}` }).click();
    await expect(a.getByTestId("scale-change")).toHaveText("Replicas 3 → 4 (+1)");
    // One change at a time, across the cards
    await card(page, ZONE_B).getByRole("button", { name: `One replica more for ${ZONE_B}` }).click();
    await expect(a.getByTestId("scale-pending")).toHaveCount(0);
    await expect(field(page, ZONE_A)).toHaveValue("3");
    await card(page, ZONE_B).getByTestId("scale-start").click();
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 4 }]);
  });

  test("on the cards: a locked NodePool says why and restores there; one the file does not name has no stepper", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    const r760 = card(page, R760);
    await expect(r760.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(r760.getByTestId("scale-card-control")).toHaveText("3 replicas");
    await expect(r760.getByTestId("scale-pool-locked")).toHaveText(`Locked by flavor ${FLAVOR} at 2.`);
    await r760.getByRole("button", { name: `Restore ${R760} to 2 replicas with update-nodepool` }).click();
    await r760.getByTestId("restore-start").click();
    await expect(r760.getByTestId("restore-started")).toContainText(`update-nodepool started (${RUN_ID}): its run shows under NodePool sizes.`);
    expect(scale.starts).toEqual([{ nodepool: R760, replicas: 2 }]);

    const extra = card(page, "prod-lark-site1-extra");
    await expect(extra.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(extra.getByTestId("scale-card-unmatched")).toHaveText("Not named in the day1 file");
  });

  test("on the cards, a viewer sees the lock and the ready count, with no stepper", async ({ page }) => {
    await openNodes(page, scaleOf(), { viewer: true, nodes: CARDS });
    await expect(card(page, R760).getByTestId("scale-pool-locked")).toHaveText(`Locked by flavor ${FLAVOR} at 2.`);
    await expect(card(page, ZONE_A).getByTestId("node-pool-ready")).toContainText("3 / 3 ready");
    await expect(page.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(page.getByTestId("restore-replicas")).toHaveCount(0);
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
    const runCard = page.getByTestId("scale-run");
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Completed");
    await expect(runCard.getByRole("heading", { level: 3, name: "Scale kind dell-r660-site1-zone" })).toBeVisible();
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
    await more(page, ZONE_A).click();
    const reads = scale.runReads;
    await page.getByTestId("scale-start").click();
    const error = page.getByTestId("scale-error");
    await expect(error).toContainText("update-nodepool refused to start: a run of this cluster is going.");
    await expect(error).toContainText(words);
    await expect(page.getByTestId("scale-start")).toBeDisabled();
    await expect(page.getByTestId("scale-cancel")).toBeEnabled();
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
    // A closed run does not hold the steppers back
    await expect(field(page, ZONE_A)).toBeEnabled();
    await expect(page.getByTestId("scale-busy-reason")).toHaveCount(0);
  });

  test("an open upgrade of the cluster leaves no stepper, holds the hardware type, and says why once", async ({ page }) => {
    const upgrade = { workflow_id: `upgrade-cluster-${LARK}`, status: "running", phase: "awaiting-approval" } as UpgradeRun;
    await openNodes(page, scaleOf(), { upgrade, nodes: CARDS });
    const why = "An upgrade-cluster run of this cluster is open";
    await expect(page.getByTestId("scale-busy-reason")).toContainText(why);
    await expect(page.getByText(why)).toHaveCount(1);
    // Nothing looks editable: every size is text
    await expect(page.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(card(page, ZONE_A).getByTestId("scale-card-control")).toHaveText("3 replicas");
    await expect(page.getByTestId("scale-kind-action")).toBeDisabled();
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
    await expect(row.getByTestId("restore-started")).toContainText(`update-nodepool started (${RUN_ID}): its run shows under NodePool sizes.`);
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

// Screenshots for the review (SCALE_SCREENSHOTS=<dir>): a card's change, the hardware type dialog, the rows' scale-down
// question and a done run, light and dark.
const SHOTS = process.env.SCALE_SCREENSHOTS;
test.describe("Scale screenshots", () => {
  test.skip(!SHOTS, "only with SCALE_SCREENSHOTS");
  for (const scheme of ["light", "dark"] as const) {
    test(`a card's change and the hardware type dialog, ${scheme}`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 1000 });
      // The app starts dark (next-themes' defaultTheme); the person's choice is kept under `theme`
      await page.addInitScript((theme) => localStorage.setItem("theme", theme), scheme);
      await openNodes(page, scaleOf(), { nodes: CARDS });
      const a = card(page, ZONE_A);
      await more(page, ZONE_A).click();
      await expect(a.getByTestId("scale-change")).toHaveText("Replicas 3 → 4 (+1)");
      await page.mouse.move(0, 0);
      await page.getByTestId("scale-panel").scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${SHOTS}/scale-card-change-${scheme}.png` });
      await a.screenshot({ path: `${SHOTS}/scale-card-${scheme}.png` });
      await page.getByTestId("scale-kind-action").click();
      const dialog = page.getByTestId("scale-kind-dialog");
      await dialog.evaluate((el) => Promise.all(el.getAnimations({ subtree: true }).map((x) => x.finished)));
      await more(page, ZONES).click();
      await more(page, ZONES).click();
      await expect(dialog.getByTestId("scale-change")).toHaveText("6 → 8 (+2)");
      await page.screenshot({ path: `${SHOTS}/scale-dialog-${scheme}.png` });
    });

    test(`the rows without live status, a scale-down's question and a done run, ${scheme}`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 1000 });
      await page.addInitScript((theme) => localStorage.setItem("theme", theme), scheme);
      await openNodes(page, scaleOf({ run: DONE }));
      await fewer(page, ZONE_B).click();
      await page.getByTestId("scale-start").click();
      await expect(page.getByTestId("scale-confirm-start")).toBeEnabled();
      await page.mouse.move(0, 0);
      await page.getByTestId("scale-panel").screenshot({ path: `${SHOTS}/scale-rows-down-${scheme}.png` });
      await page.getByTestId("scale-run").screenshot({ path: `${SHOTS}/scale-run-${scheme}.png` });
    });
  }
});
