/**
 * Flavors v2 on the cluster pages (mocked; docs/notes/2026-11-08-flavors-v2-api-changes.md
 * §10, §12, §13): drift shows the locked values a cluster file does not hold
 * beside its missing add-ons (ADR-0036); "Sync to flavor" previews one day1 MR,
 * asks for a nodepool's hardware where Wingman can't read it, has every removed
 * config confirmed, says how merging rolls the nodes, and sends exactly what the
 * preview showed (ADR-0037); the missing add-ons are offered through day2 once
 * the MR is open; a stale preview (409) is read again. The cluster list filters
 * and groups by owner numbers.
 */

import { test, expect, type Page, type Route, type Request } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, json, mockDashboardApis, mockMR } from "../fixtures/api-handlers";
import type {
  AddonDrift, ClusterDetail, ClusterDrift, ClusterStatus, DestinationCharts, DriftSummaryItem, Rebooting, SyncPreview,
  ValueDrift,
} from "../../types";

const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const NAME = "ocp4-prod-lark-site1";
const FLAVOR = "agent-dell";
const PATH = `sites/${SITE}/mces/${MCE}/hostedClusters/${NAME}.yaml`;
const POOL0 = "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb";
const POOL1 = "prod-lark-site1-dell-r760-site1-64c-512gb-20tb";
const READ_AT = "8bc410218818998ff47e641db7e97007162c678f";
const HOSTED_ID = `hosted:${SITE}:prod:${MCE}:${NAME}`;

const YAML = `# specName: ${FLAVOR}\n# specVersion: 1.0.0\nowner:\n  merkaz: "1234"\nnodepool:\n  - replicas: 3\n  - replicas: 2\n`;
const DETAIL: ClusterDetail = {
  name: NAME,
  site: SITE,
  mce: MCE,
  yaml: YAML,
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: PATH,
  last_commit_id: READ_AT,
  metadata: {
    spec_name: FLAVOR, spec_version: "1.0.0", created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { merkaz: "1234" },
    mastertag: "4.16.27-x86_64",
    platform: "agent",
    nodepools: [
      { name: POOL0, infra_env_name: "dell", replicas: 3, allow_deletion: false, configs: ["workers-chrony-configuration"], node_labels: {}, tuning_config: null },
      { name: POOL1, infra_env_name: "dell", replicas: 2, allow_deletion: false, configs: ["restored-example-config"], node_labels: {}, tuning_config: null },
    ],
    network: { vlan_id: 120, dhcp_network: "10.0.0.0", segment: "10.0.0.0/24" },
    cluster_name: null,
    automation_keys: [],
  },
  hosted_cluster: { cluster_name: "prod-lark-site1", name: "openshift-prod-lark-site1", namespace: "hcp-prod-lark-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "lark", sequence: null, problems: [] },
  mce_default_mastertag: "4.16.27-x86_64",
  problems: [],
  segments_manager: null,
};

/** nodepool[1] holds a config the flavor doesn't list and lacks one it does. */
const CONFIGS_DRIFT: ValueDrift = {
  path: "nodepools[*].configs",
  file_key: "nodepool[1].configs",
  nodepool: { index: 1, name: POOL1 },
  flavor_value: [{ name: "nm-conf-prod-lark-site1-dell-data" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
  cluster_value: [{ name: "nm-conf-prod-lark-site1-dell-data" }, { name: "workers-chrony-configuration" }, { name: "restored-example-config" }],
  in_file: true,
  added: ["nic-ring-buffer"],
  removed: ["restored-example-config"],
  needs_decision: null,
  needs_hardware: false,
  reboots: true,
};

/** A locked owner the file does not set at all. */
const OWNER_DRIFT: ValueDrift = {
  path: "owner_anaf", file_key: "owner.anaf", nodepool: null, flavor_value: "56", cluster_value: null, in_file: false,
  added: [], removed: [], needs_decision: null, needs_hardware: false, reboots: false,
};

/** nodepool[0] has no network config: its hardware must be chosen. */
const HARDWARE_DRIFT: ValueDrift = {
  path: "nodepools[*].configs",
  file_key: "nodepool[0].configs",
  nodepool: { index: 0, name: POOL0 },
  flavor_value: [{ name: "nm-conf" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
  cluster_value: [{ name: "workers-chrony-configuration" }],
  in_file: true,
  added: ["nic-ring-buffer"],
  removed: [],
  needs_decision: "nodepool[0] has no network config (nm-conf-prod-lark-site1-<hardware>); choose its hardware type",
  needs_hardware: true,
  reboots: true,
};

const CLUSTER_ROLES: AddonDrift = {
  addon_name: "cluster-roles", team: "redbull", reason: "missing", expected_version: "main", override_values: { replicas: 2 },
};

function drift(overrides: Partial<ClusterDrift> = {}): ClusterDrift {
  return {
    cluster: NAME, site: SITE, mce: MCE, state: "drifted", is_drifted: true,
    spec_name: FLAVOR, spec_version: "1.0.0", current_spec_version: "1.0.0",
    value_drift: [CONFIGS_DRIFT], addon_drift: [], version_differences: [], error: null, ...overrides,
  };
}

const DIFF = [
  `--- a/${PATH}`,
  `+++ b/${PATH}`,
  "@@ -1,2 +1,2 @@",
  ` # specName: ${FLAVOR}`,
  "-# specVersion: 1.0.0",
  "+# specVersion: 1.1.0",
  "@@ -16,7 +16,7 @@",
  "       - name: workers-chrony-configuration",
  "-      - name: restored-example-config",
  "+      - name: nic-ring-buffer",
].join("\n");

const roll = (index: number, overrides: Partial<Rebooting> = {}): Rebooting => ({
  nodepool: { index, name: index === 0 ? POOL0 : POOL1 },
  replicas: 3, upgrade_type: null, max_unavailable: null, replaces_nodes: false, ...overrides,
});

function preview(overrides: Partial<SyncPreview> = {}): SyncPreview {
  return {
    cluster: NAME, site: SITE, mce: MCE, path: PATH,
    last_commit_id: READ_AT,
    spec_name: FLAVOR,
    spec_version: "1.1.0",
    file_spec_version: "1.0.0",
    changes: [CONFIGS_DRIFT],
    diff: DIFF,
    removals: [{ nodepool: { index: 1, name: POOL1 }, name: "restored-example-config" }],
    rebooting: [roll(1, { replicas: 2 })],
    problems: [],
    warnings: [],
    can_sync: true,
    addons_to_install: [],
    version_differences: [],
    addons_error: null,
    ...overrides,
  };
}

/** `GET /api/day2/clusters/{name}/addons?mce=`: the id a day2 write addresses. */
const CHARTS: DestinationCharts = {
  cluster: NAME, mce: MCE, id: HOSTED_ID, kind: "hosted", site: SITE, env: "prod", ocp_version: "4.16.27",
  installed: [], excluded: [], warnings: [], argocd_note: "",
};

/** Every read the detail page makes; the sync routes answer `previews` in turn (the last one repeats). */
async function openDetail(
  page: Page,
  clusterDrift: ClusterDrift,
  previews: SyncPreview[] = [preview()],
  { viewer = false }: { viewer?: boolean } = {}
) {
  await injectAdminAuth(page);
  if (viewer) {
    await page.addInitScript(() => {
      const state = { state: { user: { username: "vera", groups: ["wingman-viewers"], uid: "vera", full_name: "Vera Viewer", role: "viewer" }, isAuthenticated: true }, version: 0 };
      localStorage.setItem("wingman-auth", JSON.stringify(state));
    });
  }
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters/bulk-status", (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
  await page.route(`**/api/day1/clusters/${NAME}?**`, (r) => json(r, DETAIL));
  await page.route(`**/api/day1/clusters/${NAME}/drift?**`, (r) => json(r, clusterDrift));
  await page.route(`**/api/day2/clusters/${NAME}/history?**`, (r) => json(r, []));
  await page.route(`**/api/day2/clusters/${NAME}/addons?**`, (r) => json(r, CHARTS));
  await page.route("**/api/day2/addons", (r) => json(r, []));
  const previewBodies: unknown[] = [];
  await page.route(`**/api/day1/clusters/${NAME}/sync/preview?**`, (r) => {
    previewBodies.push(r.request().postDataJSON());
    return json(r, previews[Math.min(previewBodies.length, previews.length) - 1]);
  });
  await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);
  await page.getByRole("tab", { name: "Drift" }).click();
  return { previewBodies };
}

/** Answer `POST /clusters/{name}/sync` with `answer`, keeping each request. */
async function mockSync(page: Page, answer: (route: Route) => Promise<void>) {
  const requests: Request[] = [];
  await page.route(`**/api/day1/clusters/${NAME}/sync?**`, (r) => {
    requests.push(r.request());
    return answer(r);
  });
  return requests;
}

const openedMR = (r: Route) =>
  json(r, mockMR({ iid: 61, title: `[Wingman/Day1] Sync cluster ${NAME} to spec ${FLAVOR} v1.1.0`, labels: ["wingman", "sync"] }), 201);

test.describe("Cluster drift on locked values", () => {
  test("the panel shows each locked value that differs beside the missing add-ons", async ({ page }) => {
    await openDetail(page, drift({
      value_drift: [CONFIGS_DRIFT, OWNER_DRIFT, HARDWARE_DRIFT],
      addon_drift: [CLUSTER_ROLES, { ...CLUSTER_ROLES, addon_name: "kyverno", team: "platform" }],
    }));

    await expect(page.getByText(`The cluster has drifted from ${FLAVOR} v1.0.0: 3 locked values differ, and 2 add-ons are missing.`)).toBeVisible();
    const values = page.getByTestId("value-drift");
    await expect(values.getByText("Locked values that differ")).toBeVisible();

    const configs = page.getByTestId("value-drift-nodepool[1].configs");
    await expect(configs).toContainText(`nodepool ${POOL1}`);
    await expect(configs).toContainText("nodepools[*].configs");
    await expect(configs).toContainText("Changing it rolls the nodes");
    await expect(configs.getByRole("definition").first()).toContainText("nic-ring-buffer");
    await expect(configs.getByRole("definition").last()).toContainText("restored-example-config");
    await expect(configs).toContainText("A sync adds nic-ring-buffer and removes restored-example-config.");

    const owner = page.getByTestId("value-drift-owner.anaf");
    await expect(owner.getByRole("definition").first()).toHaveText("56");
    await expect(owner).toContainText("absent from the file");

    const hardware = page.getByTestId("value-drift-nodepool[0].configs");
    await expect(hardware).toContainText("nm-conf (hardware to choose)");
    await expect(hardware.getByTestId("needs-decision")).toContainText(
      "nodepool[0] has no network config (nm-conf-prod-lark-site1-<hardware>); choose its hardware type. Sync to flavor asks for it."
    );

    // The add-on part is unchanged: day2 installs, one MR each
    await expect(page.getByText("Missing addons")).toBeVisible();
    await expect(page.getByRole("button", { name: "Install" })).toHaveCount(2);
    await expect(page.getByRole("button", { name: "Fix all (2)" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sync to flavor" })).toBeVisible();
  });

  test("a viewer sees the drift but no sync", async ({ page }) => {
    await openDetail(page, drift(), [preview()], { viewer: true });

    await expect(page.getByTestId("value-drift-nodepool[1].configs")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sync to flavor" })).toHaveCount(0);
  });

  test("a cluster in sync whose header names an older version is offered a sync", async ({ page }) => {
    await openDetail(page, drift({ state: "in_sync", is_drifted: false, value_drift: [], current_spec_version: "1.1.0" }));

    await expect(page.getByText(`The cluster holds every value ${FLAVOR} v1.1.0 locks and has every add-on it lists.`)).toBeVisible();
    await expect(page.getByText("A sync moves the header to v1.1.0.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sync to flavor" })).toBeVisible();
  });

  test("a cluster on no flavor can join one from the flavor's page", async ({ page }) => {
    await openDetail(page, drift({
      state: "not_linked", is_drifted: false, spec_name: null, spec_version: null, current_spec_version: null, value_drift: [],
    }));

    await expect(page.getByText("This cluster follows no flavor, so there is nothing to drift from.")).toBeVisible();
    await expect(page.getByText("Add existing clusters")).toBeVisible();
    await expect(page.getByRole("link", { name: "Choose a flavor" })).toHaveAttribute("href", "/specs");
    await expect(page.getByRole("button", { name: "Sync to flavor" })).toHaveCount(0);
  });

  test("a day1 that sends no value_drift still shows the add-on drift", async ({ page }) => {
    const old = drift({ addon_drift: [CLUSTER_ROLES] }) as Partial<ClusterDrift>;
    delete old.value_drift;
    await openDetail(page, old as ClusterDrift);

    await expect(page.getByText(`The cluster has drifted from ${FLAVOR} v1.0.0: 1 add-on is missing.`)).toBeVisible();
    await expect(page.getByTestId("value-drift")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Sync to flavor" })).toHaveCount(0);
  });
});

test.describe("Sync to flavor", () => {
  test("a hardware choice previews again, and the sync sends it", async ({ page }) => {
    const undecided = preview({
      changes: [HARDWARE_DRIFT, CONFIGS_DRIFT],
      problems: [`nodepool[0].configs: ${HARDWARE_DRIFT.needs_decision}`],
      can_sync: false,
    });
    const decided = preview({
      changes: [{ ...HARDWARE_DRIFT, needs_decision: null, needs_hardware: false,
        flavor_value: [{ name: "nm-conf-prod-lark-site1-dell" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }] }, CONFIGS_DRIFT],
      removals: [],
      rebooting: [roll(0), roll(1, { replicas: 2 })],
    });
    const { previewBodies } = await openDetail(page, drift({ value_drift: [HARDWARE_DRIFT, CONFIGS_DRIFT] }), [undecided, decided]);
    const syncs = await mockSync(page, openedMR);

    await page.getByRole("button", { name: "Sync to flavor" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: `Sync ${NAME} to ${FLAVOR} v1.1.0` })).toBeVisible();
    await expect(dialog.getByTestId("sync-problems")).toContainText("choose its hardware type");
    const submit = dialog.getByRole("button", { name: "Open sync MR" });
    await expect(submit).toBeDisabled();
    await expect(dialog.getByTestId("sync-blocked")).toHaveText("Resolve the problems above to sync.");
    expect(previewBodies).toEqual([{ hardware: [] }]);

    await dialog.getByRole("combobox", { name: `Hardware type for ${POOL0}` }).click();
    await page.getByRole("option", { name: /^dell\b/ }).first().click();

    await expect.poll(() => previewBodies.length).toBe(2);
    expect(previewBodies[1]).toEqual({ hardware: [{ nodepool: 0, hardware: "dell" }] });
    await expect(dialog.getByTestId("sync-problems")).toHaveCount(0);
    // The choice stays on screen, so it can be changed
    await expect(dialog.getByRole("combobox", { name: `Hardware type for ${POOL0}` })).toContainText("dell");
    await expect(submit).toBeEnabled();
    await submit.click();

    await expect(page.getByText("Sync MR !61 opened")).toBeVisible();
    expect(syncs).toHaveLength(1);
    expect(syncs[0].postDataJSON()).toEqual({
      last_commit_id: READ_AT, spec_version: "1.1.0", hardware: [{ nodepool: 0, hardware: "dell" }], confirm_removals: [],
    });
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("Sync stays disabled until every removal is confirmed, and sends exactly them", async ({ page }) => {
    const two = preview({
      removals: [
        { nodepool: { index: 0, name: POOL0 }, name: "worker-kubeletconfig-reserved" },
        { nodepool: { index: 1, name: POOL1 }, name: "restored-example-config" },
      ],
      rebooting: [roll(0), roll(1, { replicas: 2 })],
    });
    await openDetail(page, drift(), [two]);
    const syncs = await mockSync(page, openedMR);

    await page.getByRole("button", { name: "Sync to flavor" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByTestId("sync-diff")).toContainText("+      - name: nic-ring-buffer");
    await expect(dialog.getByTestId("sync-diff")).toContainText(PATH);
    const submit = dialog.getByRole("button", { name: "Open sync MR" });
    const removals = dialog.getByTestId("sync-removals");
    const first = removals.getByRole("checkbox", { name: /worker-kubeletconfig-reserved/ });
    const second = removals.getByRole("checkbox", { name: /restored-example-config/ });

    await expect(submit).toBeDisabled();
    await expect(dialog.getByTestId("sync-blocked")).toHaveText("Confirm each removal to sync (0 of 2 confirmed).");
    await first.check();
    await expect(submit).toBeDisabled();
    await expect(dialog.getByTestId("sync-blocked")).toHaveText("Confirm each removal to sync (1 of 2 confirmed).");
    await second.check();
    await expect(submit).toBeEnabled();
    await first.uncheck();
    await expect(submit).toBeDisabled();
    await first.check();
    await submit.click();

    await expect(page.getByText("Sync MR !61 opened")).toBeVisible();
    expect(syncs[0].postDataJSON()).toEqual({
      last_commit_id: READ_AT,
      spec_version: "1.1.0",
      hardware: [],
      confirm_removals: [
        { nodepool: 0, name: "worker-kubeletconfig-reserved" },
        { nodepool: 1, name: "restored-example-config" },
      ],
    });
  });

  test("the roll is stated for in-place and replaced nodepools", async ({ page }) => {
    await openDetail(page, drift(), [preview({
      removals: [],
      rebooting: [
        roll(0, { replicas: 3, upgrade_type: null }),
        roll(1, { replicas: 2, upgrade_type: "Replace", replaces_nodes: true }),
        roll(2, { replicas: 6, upgrade_type: "InPlace", max_unavailable: 2, nodepool: { index: 2, name: "prod-lark-site1-dell-r660-site1-gpu" } }),
        roll(3, { replicas: 4, upgrade_type: "InPlace", max_unavailable: "25%", nodepool: { index: 3, name: "prod-lark-site1-dell-r660-site1-edge" } }),
      ],
    })]);

    await page.getByRole("button", { name: "Sync to flavor" }).click();
    const rolling = page.getByRole("dialog").getByTestId("sync-rolling");
    await expect(rolling.getByTestId("sync-roll-0")).toContainText("Its 3 nodes are drained and rebooted in place, one node at a time.");
    await expect(rolling.getByTestId("sync-roll-1")).toContainText(
      "Its 2 nodes are replaced with new nodes (upgradeType: Replace): new nodes come up with the new configs, then the old ones are removed."
    );
    await expect(rolling.getByTestId("sync-roll-2")).toContainText("Its 6 nodes are drained and rebooted in place, 2 nodes at a time (inPlace.maxUnavailable).");
    await expect(rolling.getByTestId("sync-roll-3")).toContainText("drained and rebooted in place, 25% of the nodes at a time");
    await expect(rolling).toContainText("Nothing rolls until the MR is merged: merging is what starts it. Merge it in a window the cluster's owners accept.");
  });

  test("warnings are shown but don't block", async ({ page }) => {
    await openDetail(page, drift(), [preview({
      removals: [],
      warnings: ["nodepool[1]: this file lists mcFiles, so the CI renders only the configs it names, and nic-ring-buffer is not among them"],
    })]);

    await page.getByRole("button", { name: "Sync to flavor" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByTestId("sync-warnings")).toContainText("this file lists mcFiles");
    await expect(dialog.getByRole("button", { name: "Open sync MR" })).toBeEnabled();
  });

  test("once the MR is open, the missing add-ons are offered through day2", async ({ page }) => {
    await openDetail(page, drift({ addon_drift: [CLUSTER_ROLES] }), [preview({ removals: [], addons_to_install: [CLUSTER_ROLES] })]);
    await mockSync(page, openedMR);
    const install = page.waitForRequest((req: Request) => req.method() === "POST" && req.url().includes("/addons/redbull/cluster-roles"));
    await page.route(`**/api/day2/clusters/${encodeURIComponent(HOSTED_ID)}/addons/redbull/cluster-roles`, (r: Route) =>
      json(r, mockMR({ iid: 9, repo: "day2", team: "redbull" }), 201)
    );

    await page.getByRole("button", { name: "Sync to flavor" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByTestId("sync-addons")).toContainText("1 add-on the flavor lists is missing (cluster-roles)");
    await dialog.getByRole("button", { name: "Open sync MR" }).click();

    await expect(page.getByText("Sync MR !61 opened").first()).toBeVisible();
    const offer = page.getByRole("dialog").getByTestId("sync-addons-offer");
    await expect(offer).toContainText(`${FLAVOR} lists 1 add-on this cluster does not have`);
    await page.getByRole("dialog").getByRole("button", { name: "Install 1 add-on" }).click();

    // As the drift tab's Fix all: the id day2 resolved the name to, the values requested at create
    const request = await install;
    expect(new URL(request.url()).pathname).toBe(`/api/day2/clusters/${encodeURIComponent(HOSTED_ID)}/addons/redbull/cluster-roles`);
    expect(request.postDataJSON()).toEqual({ override_values: { replicas: 2 } });
    await expect(page.getByText("1 fix MR opened")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("when day2 did not answer, the MR still opens and says add-ons are unknown", async ({ page }) => {
    await openDetail(page, drift(), [preview({ removals: [], addons_error: "day2 did not answer: timeout" })]);
    await mockSync(page, openedMR);

    await page.getByRole("button", { name: "Sync to flavor" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Open sync MR" }).click();

    const offer = page.getByRole("dialog").getByTestId("sync-addons-offer");
    await expect(offer).toContainText("Day2 did not answer, so whether add-ons are missing is unknown (day2 did not answer: timeout)");
    await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("a stale preview (409) is said and read again, and its removals confirmed again", async ({ page }) => {
    const { previewBodies } = await openDetail(page, drift(), [preview(), preview({ last_commit_id: "1111111111111111111111111111111111111111" })]);
    let attempt = 0;
    const syncs = await mockSync(page, async (r) => {
      attempt += 1;
      if (attempt === 1) await fulfillProblem(r, 409, "REVISION_CONFLICT", "the cluster file changed since 8bc41021");
      else await openedMR(r);
    });

    await page.getByRole("button", { name: "Sync to flavor" }).click();
    const dialog = page.getByRole("dialog");
    const removal = dialog.getByRole("checkbox", { name: /restored-example-config/ });
    const submit = dialog.getByRole("button", { name: "Open sync MR" });
    await removal.check();
    await submit.click();

    await expect(dialog.getByTestId("sync-stale")).toContainText("The cluster file or the flavor changed since the preview, so no MR was opened.");
    await expect.poll(() => previewBodies.length).toBe(2);
    await expect(removal).not.toBeChecked();
    await expect(submit).toBeDisabled();

    await removal.check();
    await submit.click();
    await expect(page.getByText("Sync MR !61 opened")).toBeVisible();
    expect(syncs[1].postDataJSON()).toMatchObject({ last_commit_id: "1111111111111111111111111111111111111111" });
  });

  test("a refused sync (422) shows every problem", async ({ page }) => {
    await openDetail(page, drift(), [preview({ removals: [] })]);
    await mockSync(page, (r) =>
      fulfillProblem(r, 422, "VALIDATION_ERROR", "the sync removes configs the request does not confirm", {
        problems: ["nodepool[1]: restored-example-config is removed but not confirmed"],
      })
    );

    await page.getByRole("button", { name: "Sync to flavor" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Open sync MR" }).click();
    await expect(dialog.getByRole("alert")).toContainText("nodepool[1]: restored-example-config is removed but not confirmed");
    await expect(dialog.getByRole("alert")).toContainText("The sync was refused");
  });

  test("a preview day1 refuses (422) shows its problems instead of a diff", async ({ page }) => {
    await openDetail(page, drift(), [preview()]);
    await page.route(`**/api/day1/clusters/${NAME}/sync/preview?**`, (r) =>
      fulfillProblem(r, 422, "VALIDATION_ERROR", `the hardware chosen for ${NAME} is not usable`, {
        problems: ["hardware: nodepool[1] needs no hardware choice; its own network config is used"],
      })
    );

    await page.getByRole("button", { name: "Sync to flavor" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("alert")).toContainText("The sync cannot be previewed");
    await expect(dialog.getByRole("alert")).toContainText("needs no hardware choice");
    await expect(dialog.getByTestId("sync-diff")).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Open sync MR" })).toBeDisabled();
  });
});

// ── The cluster list: owner numbers ──────────────────────────────────────────

function row(name: string, owner: Record<string, string>): ClusterStatus {
  const short = name.replace(/^ocp4-/, "");
  return {
    name, site: SITE, mce: MCE, phase: "Unknown", spec_name: FLAVOR, spec_version: "1.0.0",
    created_by: "alice", created_at: "2026-11-07T10:00:00+00:00", mastertag: "4.16.27-x86_64",
    path: `sites/${SITE}/mces/${MCE}/hostedClusters/${name}.yaml`,
    hosted_cluster: { cluster_name: short, name: `openshift-${short}`, namespace: `hcp-${short}` },
    naming: { follows_convention: true, env: "prod", short_name: "x", sequence: null, problems: [] },
    owner, problems: [],
  };
}

const LIST: ClusterStatus[] = [
  row("ocp4-prod-alpha-site1", { merkaz: "1234", anaf: "56", mador: "7" }),
  row("ocp4-prod-bravo-site1", { merkaz: "1234", anaf: "57", mador: "7" }),
  row("ocp4-prod-charlie-site1", { merkaz: "990", anaf: "56", mador: "8" }),
  row("ocp4-prod-delta-site1", {}),
];
const SUMMARY: DriftSummaryItem[] = LIST.map((c) => ({ name: c.name, site: SITE, mce: MCE, state: "in_sync", is_drifted: false, error: null }));

test.describe("Cluster list owners", () => {
  test.beforeEach(async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters", (r) => json(r, LIST));
    await page.route("**/api/day1/clusters/drift-summary", (r) => json(r, SUMMARY));
    await page.route("**/api/day1/clusters/bulk-status", (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
    await go(page, "/clusters");
  });

  test("each row shows its owner numbers", async ({ page }) => {
    await expect(page.getByTestId("cluster-row-ocp4-prod-alpha-site1").getByTestId("cluster-owner")).toHaveText("1234 / 56 / 7");
    await expect(page.getByTestId("cluster-row-ocp4-prod-delta-site1")).toContainText("—");
    await expect(page.getByTestId("cluster-row-ocp4-prod-delta-site1").getByTestId("cluster-owner")).toHaveCount(0);
  });

  test("filters by each owner number, together, and clears", async ({ page }) => {
    const visible = (name: string) => page.getByTestId(`cluster-row-${name}`);

    await page.getByRole("combobox", { name: "Filter by anaf" }).click();
    await page.getByRole("option", { name: /^Anaf 56/ }).click();
    await expect(visible("ocp4-prod-alpha-site1")).toBeVisible();
    await expect(visible("ocp4-prod-charlie-site1")).toBeVisible();
    await expect(visible("ocp4-prod-bravo-site1")).toHaveCount(0);
    await expect(visible("ocp4-prod-delta-site1")).toHaveCount(0);
    await expect(page.getByText("2 of 4 clusters (filtered)")).toBeVisible();

    await page.getByRole("combobox", { name: "Filter by merkaz" }).click();
    await page.getByRole("option", { name: /^Merkaz 1234/ }).click();
    await expect(visible("ocp4-prod-alpha-site1")).toBeVisible();
    await expect(visible("ocp4-prod-charlie-site1")).toHaveCount(0);

    // "No mador": the clusters whose file sets none
    await page.getByRole("button", { name: "Clear filters" }).click();
    await page.getByRole("combobox", { name: "Filter by mador" }).click();
    await page.getByRole("option", { name: /^No mador/ }).click();
    await expect(visible("ocp4-prod-delta-site1")).toBeVisible();
    await expect(visible("ocp4-prod-alpha-site1")).toHaveCount(0);

    await page.getByRole("combobox", { name: "Filter by mador" }).click();
    await page.getByRole("option", { name: "Any mador" }).click();
    await expect(page.getByText("4 of 4 clusters")).toBeVisible();
  });

  test("groups by an owner number, with a heading and count per group", async ({ page }) => {
    await page.getByRole("group", { name: "Group by owner" }).getByRole("button", { name: "Merkaz" }).click();

    const body = page.locator("tbody tr");
    await expect(page.getByTestId("owner-group-merkaz-990")).toContainText("Merkaz 990");
    await expect(page.getByTestId("owner-group-merkaz-990")).toContainText("1 cluster");
    await expect(page.getByTestId("owner-group-merkaz-1234")).toContainText("2 clusters");
    await expect(page.getByTestId("owner-group-merkaz-none")).toContainText("No merkaz");
    // Numeric order (990 before 1234), the clusters without one last, rows under their heading
    await expect(body.nth(0)).toHaveAttribute("data-testid", "owner-group-merkaz-990");
    await expect(body.nth(1)).toHaveAttribute("data-testid", "cluster-row-ocp4-prod-charlie-site1");
    await expect(body.nth(2)).toHaveAttribute("data-testid", "owner-group-merkaz-1234");
    await expect(body.nth(3)).toHaveAttribute("data-testid", "cluster-row-ocp4-prod-alpha-site1");
    await expect(body.nth(4)).toHaveAttribute("data-testid", "cluster-row-ocp4-prod-bravo-site1");
    await expect(body.nth(5)).toHaveAttribute("data-testid", "owner-group-merkaz-none");
    await expect(body.nth(6)).toHaveAttribute("data-testid", "cluster-row-ocp4-prod-delta-site1");

    // Grouping and filtering combine; "None" ungroups
    await page.getByRole("combobox", { name: "Filter by anaf" }).click();
    await page.getByRole("option", { name: /^Anaf 56/ }).click();
    await expect(page.getByTestId("owner-group-merkaz-1234")).toContainText("1 cluster");
    await page.getByRole("group", { name: "Group by owner" }).getByRole("button", { name: "None" }).click();
    await expect(page.locator("[data-testid^=owner-group-]")).toHaveCount(0);
  });
});
