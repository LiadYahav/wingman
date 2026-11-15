/**
 * Tuning profiles (ADR-0061, docs/notes/2026-11-15-tuning-profiles-api.md),
 * mocked: picking a nodepool's profiles in a flavor from `tuning/` (one
 * PerformanceProfile per nodepool, a Tuned's PerformanceProfile one click
 * away), locking them on every nodepool, creating a cluster from a flavor
 * that locks them, day1's 422 for a name `tuning/` does not have shown at its
 * field, and drift plus a sync whose confirmation names the nodepools that
 * may reboot.
 */

import { test, expect, type Page, type Request, type Route } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, json, mockDashboardApis, mockMachineConfigsWithGeneric, mockMR } from "../fixtures/api-handlers";
import { mockTuningProfiles } from "../fixtures/tuning";
import { ClusterNewPage } from "../pages/cluster-new.page";
import type {
  ClusterDetail, ClusterDrift, ClusterPreview, ClusterSpec, CreateClusterRequest, Mce, SpecEntry, SyncPreview, TemplateField,
  TuningProfiles, ValueDrift,
} from "../../types";

const RULE = "nodepools[*].tuning_config";

/** The fixture template's inputs, with `tuning_config` a list of names. */
const SCHEMA: TemplateField[] = [
  { name: "owner_merkaz", type: "string", required: true, example: "1234" },
  { name: "owner_anaf", type: "string", required: true, example: "56" },
  { name: "owner_mador", type: "string", required: true, example: "7" },
  {
    name: "nodepools",
    type: "list",
    required: true,
    fields: [
      { name: "infra_env", type: "string", required: true, example: "dell-r660-site1-128c-1024gb-5tb" },
      { name: "replicas", type: "string", required: false, default: 2 },
      { name: "configs", type: "list", required: false, default: [], fields: [{ name: "name", type: "string", required: true }] },
      { name: "tuning_config", type: "list", required: false, default: [] },
    ],
  },
];

/** The fixtures' catalogue and a second PerformanceProfile, so one can replace the other. */
const CATALOG: TuningProfiles = {
  ...mockTuningProfiles,
  profiles: [
    {
      name: "performance-isolated", kind: "PerformanceProfile", summary: null, path: "tuning/performance-isolated.yaml",
      clusters: [], requires_performance_profile: null,
    },
    ...mockTuningProfiles.profiles,
  ],
};

const MCES: Mce[] = [
  {
    name: "ocp4-prod-mce-site1-a", site: "site1", env: "prod", letter: "a", follows_convention: true, naming_problems: [],
    default_mastertag: "4.16.27-x86_64", hub_version: "4.16.27-x86_64", cluster_count: 3, stray_files: [], problems: [],
  },
];

/** A nodepool's tuning picker, and its parts. */
const picker = (page: Page, index: number) => page.getByTestId(`nodepool-${index}-tuning`);
const addBox = (page: Page, index: number) => page.getByRole("combobox", { name: `Nodepool ${index + 1} tuning profiles: add a profile` });
const chips = (page: Page, index: number) => picker(page, index).locator("[data-testid^=tuning-profile-]");

/** Pick an option of a Combobox by its label (an option's name also holds its description). */
async function choose(page: Page, combobox: ReturnType<Page["getByRole"]>, option: string) {
  await combobox.click();
  await page.getByRole("option").filter({ has: page.getByText(option, { exact: true }) }).click();
  await expect(page.getByRole("option")).toHaveCount(0);
}

async function base(page: Page) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/tuning-profiles", (r) => json(r, CATALOG));
  // New nodepools' nm-conf starts at generic, so the configs need no choice here
  await page.route("**/api/day1/machine-configs", (r) => json(r, mockMachineConfigsWithGeneric));
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/specs/template", (r) => json(r, "# cluster-template.j2"));
  await page.route("**/api/day1/specs/template/schema**", (r) => json(r, SCHEMA));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
}

// ── The flavor editor ─────────────────────────────────────────────────────────

test.describe("Tuning profiles in a flavor", () => {
  test("pick per nodepool, one PerformanceProfile, its pairing, then lock on every nodepool and save", async ({ page }) => {
    await base(page);
    const writes: ClusterSpec[] = [];
    await page.route("**/api/day1/specs", (r) => {
      if (r.request().method() !== "POST") return json(r, []);
      writes.push(r.request().postDataJSON());
      return json(r, mockMR({ repo: "specs", iid: 31 }), 201);
    });
    await go(page, "/specs/new");
    await page.getByTestId("spec-name-input").fill("agent-tuned");

    // Admins see the files tuning/ does not offer
    await expect(page.getByTestId("tuning-catalog-problems")).toContainText("tuning/tuned-misnamed.yaml");
    await expect(picker(page, 0)).toContainText("No tuning profiles.");

    // Each option shows its kind and summary
    await addBox(page, 0).click();
    await expect(page.getByRole("option").filter({ hasText: "tuned-network-latency" })).toContainText("Tuned · Lower network latency on worker nodes");
    await page.keyboard.press("Escape");
    await choose(page, addBox(page, 0), "tuned-network-latency");
    await choose(page, addBox(page, 0), "performance-pinned");

    // A second PerformanceProfile replaces the first, and the option says so before it is picked
    await addBox(page, 0).click();
    await expect(page.getByRole("option").filter({ hasText: "performance-isolated" })).toContainText(
      "A nodepool takes one PerformanceProfile; picking this replaces performance-pinned"
    );
    await page.getByRole("option").filter({ has: page.getByText("performance-isolated", { exact: true }) }).click();
    await expect(chips(page, 0)).toHaveCount(2);
    await expect(picker(page, 0).getByTestId("tuning-profile-performance-isolated")).toBeVisible();
    await expect(picker(page, 0).getByTestId("tuning-profile-performance-pinned")).toHaveCount(0);

    // A Tuned that builds on a PerformanceProfile the nodepool lacks: a warning, and the one click that adds it
    await choose(page, addBox(page, 0), "tuned-pinned-irq");
    const pairing = page.getByTestId("nodepool-0-tuning-pairing");
    await expect(pairing).toContainText("tuned-pinned-irq builds on performance-pinned, which this nodepool does not have.");
    await pairing.getByRole("button", { name: "Add performance-pinned" }).click();
    await expect(pairing).toHaveCount(0);
    await expect(chips(page, 0)).toHaveText([/^tuned-network-latency/, /^performance-pinned/, /^tuned-pinned-irq/]);

    // Locked: every nodepool, the one added later included, has the same profiles
    await page.getByRole("radiogroup", { name: "Tuning profiles: preset or locked" }).first().getByRole("radio", { name: "Locked" }).click();
    await page.getByRole("button", { name: "Add nodepool" }).click();
    await expect(chips(page, 1)).toHaveText([/^tuned-network-latency/, /^performance-pinned/, /^tuned-pinned-irq/]);
    await expect(page.locator('[data-field="nodepools[1].tuning_config"]')).toContainText("Locked on every nodepool");
    // An edit on either nodepool is the rule's
    await picker(page, 1).getByRole("button", { name: "Remove tuning profile tuned-pinned-irq" }).click();
    await expect(chips(page, 0)).toHaveCount(2);

    await page.getByRole("button", { name: /review & create/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
    await expect(page.getByText("Flavor MR !31 opened")).toBeVisible();
    const day1 = writes[0].spec.day1;
    expect(day1.locked_paths).toContain(RULE);
    const pools = day1.values?.nodepools as { tuning_config?: unknown }[];
    expect(pools.map((p) => p.tuning_config)).toEqual([
      ["tuned-network-latency", "performance-pinned"],
      ["tuned-network-latency", "performance-pinned"],
    ]);
  });
});

// ── The create form ───────────────────────────────────────────────────────────

function flavor(name: string, day1: Partial<SpecEntry["spec"]["day1"]>): SpecEntry {
  return {
    apiVersion: "wingman.io/v1",
    kind: "ClusterSpec",
    metadata: { name, description: `The ${name} flavor`, version: "1.0.0", labels: {} },
    spec: {
      day1: { variables: [], structure: { nodepools: [{}] }, locked_paths: [], template: "# template", values: {}, ...day1 },
      day2: { addons: [] },
    },
    load_error: null,
    load_problems: [],
    warnings: [],
  };
}

const STATIC = [{ name: "workers-chrony-configuration" }];
const TUNED = flavor("tuned", {
  locked_paths: [RULE],
  values: { nodepools: [{ configs: STATIC, tuning_config: ["tuned-network-latency"] }] },
});
/** A preset that names a profile tuning/ no longer has: day1 refuses it. */
const RETIRED = flavor("retired", { values: { nodepools: [{ configs: STATIC, tuning_config: ["tuned-retired"] }] } });

const PREVIEW: ClusterPreview = {
  yaml: '# specName: "tuned"\n# specVersion: "1.0.0"\nmastertag: 4.16.27-x86_64\n',
  path: "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-tuned-site1-a.yaml",
};
const UNKNOWN = "nodepools[0].tuning_config[0]: tuned-retired is not a tuning profile in tuning/ (did you mean tuned-network-latency?)";

async function openCreate(page: Page, spec: string) {
  const previews: CreateClusterRequest[] = [];
  await base(page);
  await page.route("**/api/day1/specs", (r) => json(r, [TUNED, RETIRED]));
  await page.route("**/api/day1/sites", (r) => json(r, ["site1"]));
  await page.route("**/api/day1/mces/*/infraenvs", (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled"));
  await page.route("**/api/day1/clusters/preview", (r) => {
    const body: CreateClusterRequest = r.request().postDataJSON();
    previews.push(body);
    return body.spec_name === "retired"
      ? fulfillProblem(r, 422, "VALIDATION_ERROR", "the cluster's inputs are not acceptable", { problems: [UNKNOWN] })
      : json(r, PREVIEW);
  });
  const form = new ClusterNewPage(page);
  await form.goto();
  await form.chooseSpec(spec);
  await form.place({ site: "site1", env: "prod", version: "4.16.27" });
  await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");
  await form.fillName(`ocp4-prod-${spec}-site1-a`);
  for (const [example, value] of [["1234", "1234"], ["56", "56"], ["7", "7"]]) await form.templateInput(example).fill(value);
  await page.getByPlaceholder("e.g. dell-r660-site1-128c-1024gb-5tb").fill("dell-r660-site1-128c-1024gb-5tb");
  return { form, previews };
}

test.describe("Tuning profiles at create", () => {
  test("a flavor's locked profiles are shown read-only and sent", async ({ page }) => {
    const { form, previews } = await openCreate(page, "tuned");
    const field = page.locator('[data-field-path="nodepools[0].tuning_config"]');
    await expect(field).toContainText("Tuning Profiles");
    await expect(field).toContainText("locked on every nodepool");
    await expect(picker(page, 0).getByTestId("tuning-profile-tuned-network-latency")).toContainText("Lower network latency on worker nodes");
    await expect(addBox(page, 0)).toHaveCount(0);
    await expect(picker(page, 0).getByRole("button", { name: /Remove tuning profile/ })).toHaveCount(0);

    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    const pools = previews[0].variables.nodepools as { tuning_config?: unknown }[];
    expect(pools[0].tuning_config).toEqual(["tuned-network-latency"]);
  });

  test("day1's 422 for a name tuning/ does not have is shown at the nodepool's field", async ({ page }) => {
    const { form } = await openCreate(page, "retired");
    // The catalogue already says so while the form is filled in
    await expect(picker(page, 0)).toContainText("tuned-retired is not a tuning profile in tuning/");
    await form.review();
    const field = page.locator('[data-field-path="nodepools[0].tuning_config"]');
    await expect(field.locator("[data-field-problems]")).toContainText("did you mean tuned-network-latency?");
    await expect(form.reviewDialog).not.toBeVisible();

    // Removed, and replaced from the picker: the field's problem goes
    await picker(page, 0).getByRole("button", { name: "Remove tuning profile tuned-retired" }).click();
    await choose(page, addBox(page, 0), "tuned-network-latency");
    await expect(field.locator("[data-field-problems]")).toHaveCount(0);
  });
});

// ── Drift and sync ────────────────────────────────────────────────────────────

const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const NAME = "ocp4-prod-lark-site1";
const PATH = `sites/${SITE}/mces/${MCE}/hostedClusters/${NAME}.yaml`;
const POOL1 = "prod-lark-site1-dell-r760-site1-64c-512gb-20tb";
const READ_AT = "8bc410218818998ff47e641db7e97007162c678f";

const DETAIL: ClusterDetail = {
  name: NAME, site: SITE, mce: MCE,
  yaml: `# specName: tuned\n# specVersion: 1.0.0\nnodepool:\n  - replicas: 3\n  - replicas: 2\n    tuningConfig: tuned-sysctl-baseline\n`,
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: PATH,
  last_commit_id: READ_AT,
  metadata: {
    spec_name: "tuned", spec_version: "1.0.0", created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { merkaz: "1234" },
    mastertag: "4.16.27-x86_64",
    platform: "agent",
    nodepools: [
      { name: "prod-lark-site1-dell", infra_env_name: "dell", replicas: 3, allow_deletion: false, configs: [], node_labels: {}, tuning_config: "tuned-network-latency" },
      { name: POOL1, infra_env_name: "dell", replicas: 2, allow_deletion: false, configs: [], node_labels: {}, tuning_config: "tuned-sysctl-baseline" },
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

/** nodepool[1] names another profile than the flavor's rule. */
const TUNING_DRIFT: ValueDrift = {
  path: RULE,
  file_key: "nodepool[1].tuningConfig",
  nodepool: { index: 1, name: POOL1 },
  flavor_value: "tuned-network-latency",
  cluster_value: "tuned-sysctl-baseline",
  in_file: true,
  added: ["tuned-network-latency"],
  removed: ["tuned-sysctl-baseline"],
  needs_decision: null,
  needs_hardware: false,
  reboots: true,
};

const DRIFT: ClusterDrift = {
  cluster: NAME, site: SITE, mce: MCE, state: "drifted", is_drifted: true, spec_name: "tuned", spec_version: "1.0.0",
  current_spec_version: "1.0.0", value_drift: [TUNING_DRIFT], addon_drift: [], version_differences: [], error: null, update: null,
};

const SYNC: SyncPreview = {
  cluster: NAME, site: SITE, mce: MCE, path: PATH, last_commit_id: READ_AT, spec_name: "tuned", spec_version: "1.0.0",
  file_spec_version: "1.0.0", changes: [TUNING_DRIFT],
  diff: `--- a/${PATH}\n+++ b/${PATH}\n@@ -6,1 +6,1 @@\n-    tuningConfig: tuned-sysctl-baseline\n+    tuningConfig: "tuned-network-latency"\n`,
  removals: [],
  rebooting: [{ nodepool: { index: 1, name: POOL1 }, replicas: 2, upgrade_type: null, max_unavailable: null, replaces_nodes: false, configs: false, tuning: true }],
  problems: [], warnings: [], can_sync: true, addons_to_install: [], version_differences: [], addons_error: null,
};

test.describe("Tuning profiles: drift and sync", () => {
  test("drift names the profiles a sync swaps, and its confirmation names the nodepool that may reboot", async ({ page }) => {
    await base(page);
    await page.route("**/api/day1/clusters/bulk-status", (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
    await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
    await page.route(`**/api/day1/clusters/${NAME}?**`, (r) => json(r, DETAIL));
    await page.route(`**/api/day1/clusters/${NAME}/drift?**`, (r) => json(r, DRIFT));
    await page.route(`**/api/day2/clusters/${NAME}/history?**`, (r) => json(r, []));
    await page.route(`**/api/day1/clusters/${NAME}/sync/preview?**`, (r) => json(r, SYNC));
    const syncs: Request[] = [];
    await page.route(`**/api/day1/clusters/${NAME}/sync?**`, (r: Route) => {
      syncs.push(r.request());
      return json(r, mockMR({ iid: 62, title: `[Wingman/Day1] Sync cluster ${NAME} to spec tuned v1.0.0` }), 201);
    });
    await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);
    await page.getByRole("tab", { name: "Drift" }).click();

    const item = page.getByTestId("value-drift-nodepool[1].tuningConfig");
    await expect(item).toContainText("Changing its tuning profiles may reboot the nodes");
    await expect(item).toContainText("A sync adds tuned-network-latency and removes tuned-sysctl-baseline.");

    await page.getByRole("button", { name: "Sync to flavor" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByTestId("sync-tuning-1")).toHaveText("Its tuning profiles change: its nodes may reboot.");
    await expect(dialog.getByTestId("sync-tuning-confirm")).toHaveText(
      `Tuning profiles change on ${POOL1}: their nodes may reboot when the MR merges.`
    );
    await dialog.getByRole("button", { name: "Open sync MR" }).click();
    await expect(page.getByText("Sync MR !62 opened")).toBeVisible();
    // Removing a profile needs no confirmation field: confirm_removals is about machine configs
    expect(syncs[0].postDataJSON()).toEqual({ last_commit_id: READ_AT, spec_version: "1.0.0", hardware: [], confirm_removals: [] });
  });
});
