/**
 * The flavor editor (`/specs/new`, `/specs/<name>/edit`) against the
 * flavors v2 contract (docs/notes/2026-11-08-flavors-v2-api-changes.md):
 * presets and locks saved as `spec.day1.values` and `locked_paths`, the
 * configs rule, the nodepool defaults, numeric owners, day1's 422 problems at
 * their fields, a stored flavor's warnings, and the cluster-file preview of a
 * saved flavor. Every API is mocked here, on the fixtures' names.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis, mockMachineConfigs, mockMR } from "../fixtures/api-handlers";
import type { ClusterSpec, CreateClusterRequest, ErrorCode, Mce, SpecDetail, TemplateField } from "../../types";

// ── Mock data ────────────────────────────────────────────────────────────────

/** The fixture template's inputs (`GET /specs/template/schema`, reserved ones left out). */
const SCHEMA: TemplateField[] = [
  { name: "owner_merkaz", type: "string", required: true, example: "1234" },
  { name: "owner_anaf", type: "string", required: true, example: "56" },
  { name: "owner_mador", type: "string", required: true, example: "7" },
  { name: "platform", type: "string", required: false, default: "" },
  {
    name: "nodepools",
    type: "list",
    required: true,
    fields: [
      { name: "infra_env", type: "string", required: true, example: "dell-r660-site1-128c-1024gb-5tb" },
      { name: "nodepool_name", type: "string", required: false, default: "" },
      { name: "replicas", type: "string", required: false, default: 2 },
      { name: "configs", type: "list", required: false, default: [], fields: [{ name: "name", type: "string", required: true }] },
      { name: "node_labels", type: "object", required: false, default: {} },
      { name: "tuning_config", type: "string", required: false, default: "" },
    ],
  },
];

/** `agent-dell` as day1 returns it: nodepool 0's configs locked, its replicas a preset. */
const AGENT_DELL: SpecDetail = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: {
    name: "agent-dell",
    description: "One nodepool of Dell workers with the team's machine configs, locked",
    version: "1.0.0",
    labels: { platform: "agent" },
  },
  spec: {
    day1: {
      variables: [],
      structure: { nodepools: [{ configs: [{}, {}, {}] }] },
      locked_paths: ["nodepools[0].configs"],
      template: "owner:\n  merkaz: \"{{ owner_merkaz }}\"\n",
      values: {
        nodepools: [
          {
            replicas: 2,
            configs: [{ name: "nm-conf", hardware: "dell" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
          },
        ],
      },
    },
    day2: { addons: [] },
  },
  load_error: null,
  load_problems: [],
  warnings: [],
  last_commit_id: "aaaaaaaa11111111aaaaaaaa11111111aaaaaaaa",
};

const MCES: Mce[] = [
  {
    name: "ocp4-prod-mce-site1-a",
    site: "site1",
    env: "prod",
    letter: "a",
    follows_convention: true,
    naming_problems: [],
    default_mastertag: "4.16.27-x86_64",
    hub_version: "4.16.27-x86_64",
    cluster_count: 3,
    stray_files: [],
    problems: [],
  },
];

function problem(status: number, code: ErrorCode, detail: string, details: Record<string, unknown> = {}) {
  return {
    type: `/problems/${code.toLowerCase().replace(/_/g, "-")}`,
    title: code.replace(/_/g, " "),
    status,
    detail,
    instance: "/api/day1/specs",
    code,
    request_id: "req_e2e0000000000002",
    details,
  };
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: status >= 400 ? "application/problem+json" : "application/json",
    body: JSON.stringify(body),
  });

/** A problem panel or field message with `text` (Next's route announcer is also an alert). */
const alertWith = (page: Page, text: string | RegExp) => page.getByRole("alert").filter({ hasText: text });

/** The `data-field` wrapper of one value, by its template-input path. */
const field = (page: Page, path: string) => page.locator(`[data-field="${path}"]`);

/** The Preset/Locked control of a value, by its label. */
const lockControl = (page: Page, label: string) => page.getByRole("radiogroup", { name: `${label}: preset or locked` });

async function lock(page: Page, label: string) {
  await lockControl(page, label).getByRole("radio", { name: "Locked" }).click();
}

/** Pick an option of a Combobox by its label (an option's name also holds its description). */
async function choose(page: Page, combobox: ReturnType<Page["getByRole"]>, option: string) {
  await combobox.click();
  await page.getByRole("option").filter({ has: page.getByText(option, { exact: true }) }).click();
  // The list is a popup (role dialog) until its exit animation ends
  await expect(page.getByRole("option")).toHaveCount(0);
}

/** The posted or put spec of the next write, and the URL it went to. */
interface Write {
  body: ClusterSpec;
  url: URL;
}

/** Auth, the dashboard, the editor's reads, and `routes` (registered last, so they win). */
async function open(page: Page, path: string, routes: (page: Page) => Promise<void> = async () => {}) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/specs/template", (r) => json(r, "# cluster-template.j2"));
  await page.route("**/api/day1/specs/template/schema**", (r) => json(r, SCHEMA));
  await page.route("**/api/day1/machine-configs", (r) => json(r, mockMachineConfigs));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
  await page.route("**/api/day1/mces/*/openshift-versions", (r) =>
    json(r, { mce: "ocp4-prod-mce-site1-a", versions: ["4.16.30", "4.16.27"], problems: [] })
  );
  await routes(page);
  await go(page, path);
}

/** A new flavor whose create is answered by `onPost`; the writes are collected. */
async function openNew(page: Page, onPost: (route: Route) => Promise<void> = (r) => json(r, mockMR({ repo: "specs", iid: 21 }), 201)) {
  const writes: Write[] = [];
  await open(page, "/specs/new", async (p) => {
    await p.route("**/api/day1/specs", (r) => {
      if (r.request().method() !== "POST") return json(r, []);
      writes.push({ body: r.request().postDataJSON(), url: new URL(r.request().url()) });
      return onPost(r);
    });
  });
  await expect(page.getByRole("heading", { name: "New Flavor" })).toBeVisible();
  return writes;
}

async function reviewAndConfirm(page: Page, button: RegExp = /review & create/i) {
  await page.getByRole("button", { name: button }).click();
  await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
}

// ── New flavor ───────────────────────────────────────────────────────────────

test.describe("Flavor editor: a new flavor", () => {
  test("the first nodepool and every added one start with a copy of the nodepool defaults", async ({ page }) => {
    const writes = await openNew(page);
    await page.getByTestId("spec-name-input").fill("agent-new");

    const first = page.getByTestId("nodepool-0-configs");
    await expect(first.getByRole("combobox", { name: /entry 1$/ })).toContainText("nm-conf");
    await expect(first.getByRole("combobox", { name: /entry 2$/ })).toContainText("workers-chrony-configuration");
    await expect(first.getByRole("combobox", { name: /entry 3$/ })).toContainText("nic-ring-buffer");
    // A flavor's nm-conf needs a hardware type (day1 refuses it without one)
    await expect(first.getByText(/Choose the hardware type/)).toBeVisible();
    await choose(page, first.getByRole("combobox", { name: /entry 1 hardware type$/ }), "dell");

    await page.getByRole("button", { name: "Add nodepool" }).click();
    const second = page.getByTestId("nodepool-1-configs");
    await expect(second.getByRole("combobox", { name: /entry 3$/ })).toContainText("nic-ring-buffer");
    // A copy: choosing nodepool 2's hardware leaves nodepool 1's alone
    await choose(page, second.getByRole("combobox", { name: /entry 1 hardware type$/ }), "cisco");
    await expect(first.getByText("Written as nm-conf-<cluster>-dell")).toBeVisible();

    await reviewAndConfirm(page);
    await expect(page.getByText("Flavor MR !21 opened")).toBeVisible();
    const day1 = writes[0].body.spec.day1;
    expect(day1.structure).toEqual({ nodepools: [{}, {}] });
    expect(day1.values).toEqual({
      nodepools: [
        { configs: [{ name: "nm-conf", hardware: "dell" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }] },
        { configs: [{ name: "nm-conf", hardware: "cisco" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }] },
      ],
    });
    expect(day1.locked_paths).toEqual([]);
  });

  test("presets and locks are saved as values and locked_paths, never immutable_paths", async ({ page }) => {
    const writes = await openNew(page);
    await page.getByTestId("spec-name-input").fill("agent-locked");

    await page.getByLabel("Merkaz", { exact: true }).fill("1234");
    await page.getByLabel("Anaf", { exact: true }).fill("0056");
    await lock(page, "Anaf");
    await expect(field(page, "owner_anaf")).toContainText("Fixed: every cluster gets exactly this value.");
    await page.getByRole("radiogroup", { name: "Platform", exact: true }).getByRole("radio", { name: "KubeVirt" }).click();
    await lock(page, "Platform");

    const pool = page.getByTestId("nodepool-0");
    await pool.getByLabel("Replicas", { exact: true }).fill("3");
    await lock(page, "Replicas");
    await choose(page, pool.getByRole("combobox", { name: /entry 1 hardware type$/ }), "dell");
    await lock(page, "Machine configs");
    await pool.getByRole("button", { name: "Add label" }).click();
    await pool.getByLabel("Nodepool 1 node labels: key 1").fill("zone");
    await pool.getByLabel("Nodepool 1 node labels: value 1").fill("a");

    // The review lists what every cluster gets
    const locked = page.getByTestId("review-locked");
    await expect(locked).toContainText("Owner · Anaf");
    await expect(locked).toContainText("Nodepool 1 · Replicas");
    await expect(page.getByTestId("review-presets")).toContainText("Owner · Merkaz");
    await expect(page.getByTestId("review-presets")).toContainText("zone=a");

    await reviewAndConfirm(page);
    await expect(page.getByText("Flavor MR !21 opened")).toBeVisible();
    const day1 = writes[0].body.spec.day1 as ClusterSpec["spec"]["day1"] & { immutable_paths?: unknown };
    expect(day1).not.toHaveProperty("immutable_paths");
    expect(day1.locked_paths).toEqual(["owner_anaf", "platform", "nodepools[0].replicas", "nodepools[0].configs"]);
    expect(day1.values).toEqual({
      owner_merkaz: "1234",
      owner_anaf: "0056",
      platform: "kubevirt",
      nodepools: [
        {
          replicas: 3,
          configs: [{ name: "nm-conf", hardware: "dell" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
          node_labels: { zone: "a" },
        },
      ],
    });
  });

  test("owners are 1 to 10 digits, a locked value needs one, and nothing is sent until both hold", async ({ page }) => {
    const writes = await openNew(page);
    await page.getByTestId("spec-name-input").fill("agent-owners");
    await choose(page, page.getByTestId("nodepool-0-configs").getByRole("combobox", { name: /entry 1 hardware type$/ }), "dell");

    const merkaz = page.getByLabel("Merkaz", { exact: true });
    await expect(merkaz).toHaveAttribute("inputmode", "numeric");
    await merkaz.fill("12a");
    await expect(field(page, "owner_merkaz")).toContainText("A number of 1 to 10 digits, like 1234");
    await lock(page, "Mador");
    await expect(field(page, "owner_mador")).toContainText("A locked value needs a value");
    // A new flavor has no saved locks, so none of them is "not enforced"
    await expect(page.getByTestId("lock-not-enforced")).toHaveCount(0);

    await page.getByRole("button", { name: /review & create/i }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(alertWith(page, "Fix these 2 before saving")).toBeVisible();
    await expect(page.getByRole("button", { name: /Flavor parts|Basics/ }).first()).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Flavor parts" }).getByLabel("2 to fix")).toBeVisible();
    expect(writes).toHaveLength(0);

    await merkaz.fill("12");
    await page.getByLabel("Mador", { exact: true }).fill("7");
    await reviewAndConfirm(page);
    await expect(page.getByText("Flavor MR !21 opened")).toBeVisible();
    expect(writes[0].body.spec.day1.values).toMatchObject({ owner_merkaz: "12", owner_mador: "7" });
    expect(writes[0].body.spec.day1.locked_paths).toEqual(["owner_mador"]);
  });

  test("the configs rule: one list on every nodepool, each with its own hardware, locked as nodepools[*].configs", async ({ page }) => {
    const writes = await openNew(page);
    await page.getByTestId("spec-name-input").fill("agent-baseline-2");
    const pool0 = page.getByTestId("nodepool-0");
    await lock(page, "Machine configs");

    await page.getByRole("radiogroup", { name: "Machine configs", exact: true }).getByRole("radio", { name: /The same on every nodepool/ }).click();
    const rule = page.getByTestId("configs-rule");
    await expect(rule).toContainText("Locked as a rule");
    // The rule's list is the defaults; nm-conf takes each nodepool's hardware, so it has none here
    await expect(rule.getByRole("combobox", { name: /entry 1$/ })).toContainText("nm-conf");
    await expect(rule.getByRole("combobox", { name: /hardware type$/ })).toHaveCount(0);
    await choose(page, rule.getByRole("combobox", { name: /add a config$/ }), "worker-kubeletconfig-reserved");

    await choose(page, pool0.getByRole("combobox", { name: "Nodepool 1 network hardware" }), "dell");
    await page.getByRole("button", { name: "Add nodepool" }).click();
    const pool1 = page.getByTestId("nodepool-1");
    await expect(pool1).toContainText("Gets the rule's configs: nm-conf, workers-chrony-configuration, nic-ring-buffer, worker-kubeletconfig-reserved");
    // Each nodepool picks its own hardware before a save
    await page.getByRole("button", { name: /review & create/i }).click();
    await expect(field(page, "nodepools[1].configs")).toContainText("Choose this nodepool's network hardware");
    await choose(page, pool1.getByRole("combobox", { name: "Nodepool 2 network hardware" }), "dell-data");

    await reviewAndConfirm(page);
    await expect(page.getByText("Flavor MR !21 opened")).toBeVisible();
    const day1 = writes[0].body.spec.day1;
    // The rule replaces the positional lock on nodepool 1's configs
    expect(day1.locked_paths).toEqual(["nodepools[*].configs"]);
    const statics = [{ name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }, { name: "worker-kubeletconfig-reserved" }];
    expect(day1.values).toEqual({
      nodepools: [
        { configs: [{ name: "nm-conf", hardware: "dell" }, ...statics] },
        { configs: [{ name: "nm-conf", hardware: "dell-data" }, ...statics] },
      ],
    });
  });

  test("the rule must list nm-conf once", async ({ page }) => {
    const writes = await openNew(page);
    await page.getByTestId("spec-name-input").fill("agent-no-network");
    await page.getByRole("radiogroup", { name: "Machine configs", exact: true }).getByRole("radio", { name: /The same on every nodepool/ }).click();
    const rule = page.getByTestId("configs-rule");
    await rule.getByRole("button", { name: "Remove nm-conf (entry 1)" }).click();
    await expect(rule).toContainText("List nm-conf exactly once: every nodepool needs its own network config");
    await page.getByRole("button", { name: /review & create/i }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(writes).toHaveLength(0);
  });

  test("day1's problems are shown at their fields, and the rest at the top", async ({ page }) => {
    const problems = [
      "owner_anaf: must be a number of 1 to 10 digits, sent as a string like \"1234\" (got '5x')",
      "nodepools[0].configs[1]: no machine config 'workers-chrony-configuration' in mc-files/ (did you mean 'workers-chrony-config'?)",
      "locked_paths: platform is locked but spec.day1.values sets no value for it",
      "spec.day2.addons: addons listed twice: redbull/cluster-roles",
    ];
    await openNew(page, (r) => json(r, problem(422, "VALIDATION_ERROR", "spec 'agent-refused' cannot be saved", { problems }), 422));
    await page.getByTestId("spec-name-input").fill("agent-refused");
    await page.getByLabel("Anaf", { exact: true }).fill("56");
    await choose(page, page.getByTestId("nodepool-0-configs").getByRole("combobox", { name: /entry 1 hardware type$/ }), "dell");
    await reviewAndConfirm(page);

    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(field(page, "owner_anaf")).toContainText("must be a number of 1 to 10 digits");
    await expect(page.getByTestId("nodepool-0-configs-entry-1")).toContainText("no machine config 'workers-chrony-configuration' in mc-files/");
    await expect(field(page, "platform")).toContainText("platform is locked but spec.day1.values sets no value for it");
    const top = alertWith(page, "spec 'agent-refused' cannot be saved");
    await expect(top).toContainText("spec.day2.addons: addons listed twice: redbull/cluster-roles");
    await expect(top).toContainText("3 more are shown at their fields below.");
    await expect(top).not.toContainText("owner_anaf");
  });

  test("a new flavor has no cluster-file preview yet, and says why", async ({ page }) => {
    let previews = 0;
    await openNew(page);
    await page.route("**/api/day1/clusters/preview", (r) => {
      previews++;
      return json(r, { yaml: "", path: "" });
    });
    const review = page.locator("section#review");
    await review.scrollIntoViewIfNeeded();
    await expect(review.getByTestId("flavor-yaml")).toContainText("kind: ClusterSpec");
    await review.getByRole("tab", { name: "Cluster file" }).click();
    await expect(review.getByTestId("cluster-preview-unavailable")).toContainText("once this flavor is saved");
    expect(previews).toBe(0);
  });
});

// ── Edit ─────────────────────────────────────────────────────────────────────

test.describe("Flavor editor: editing a flavor", () => {
  test("a stored flavor's warnings are shown at the top, and a lock this page cannot show can be removed", async ({ page }) => {
    const stored: SpecDetail = {
      ...AGENT_DELL,
      spec: {
        ...AGENT_DELL.spec,
        day1: {
          ...AGENT_DELL.spec.day1,
          // An old file: a lock on a field that cannot be locked, and an owner locked with no value
          locked_paths: ["nodepools[0].configs", "nodepools[0].infra_env", "owner_mador"],
        },
      },
      warnings: [
        "locked_paths: nodepools[0].infra_env cannot be locked; lockable inputs are owner_merkaz, owner_anaf, owner_mador, platform, nodepools[<i>].replicas, nodepools[<i>].configs, nodepools[<i>].node_labels",
        "locked_paths: owner_mador is locked but spec.day1.values sets no value for it",
      ],
      // A create enforces only the locks that keep the rules
      enforced_locks: ["nodepools[0].configs"],
    };
    const writes: Write[] = [];
    await open(page, "/specs/agent-dell/edit", async (p) => {
      await p.route(/\/api\/day1\/specs\/agent-dell(\?.*)?$/, (r) => {
        if (r.request().method() !== "PUT") return json(r, stored);
        writes.push({ body: r.request().postDataJSON(), url: new URL(r.request().url()) });
        return json(r, mockMR({ repo: "specs", iid: 22, title: "[Wingman/Specs] Update spec agent-dell" }));
      });
    });

    const warnings = page.getByTestId("flavor-warnings");
    await expect(warnings).toContainText("saving it unchanged would be refused");
    await expect(warnings).toContainText("nodepools[0].infra_env cannot be locked");
    const mador = field(page, "owner_mador");
    await expect(mador.getByTestId("lock-not-enforced")).toContainText(
      "Locked, but not enforced: owner_mador is locked but spec.day1.values sets no value for it"
    );
    await expect(mador).toContainText("A locked value needs a value");
    await expect(field(page, "nodepools[0].configs").getByTestId("lock-not-enforced")).toHaveCount(0);
    // Locked values load as locked: nodepool 1's configs
    await expect(lockControl(page, "Machine configs").getByRole("radio", { name: "Locked" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("nodepool-0-configs").getByRole("combobox", { name: /entry 1 hardware type$/ })).toContainText("dell");

    await warnings.getByRole("button", { name: "Remove the lock on nodepools[0].infra_env" }).click();
    await page.getByLabel("Mador", { exact: true }).fill("7");
    await reviewAndConfirm(page, /review & update/i);

    await expect(page.getByText("Update MR !22 opened")).toBeVisible();
    expect(writes[0].url.searchParams.get("last_commit_id")).toBe(AGENT_DELL.last_commit_id);
    expect(writes[0].body.spec.day1.locked_paths).toEqual(["nodepools[0].configs", "owner_mador"]);
    expect(writes[0].body.spec.day1.values).toEqual({ ...AGENT_DELL.spec.day1.values, owner_mador: "7" });
    for (const extra of ["warnings", "enforced_locks", "last_commit_id", "load_error", "load_problems"]) {
      expect(writes[0].body).not.toHaveProperty(extra);
    }
  });

  test("old files' immutable_paths arrive as locked_paths and are saved under the new name", async ({ page }) => {
    const writes: Write[] = [];
    const legacy: SpecDetail = {
      ...AGENT_DELL,
      spec: {
        ...AGENT_DELL.spec,
        day1: { ...AGENT_DELL.spec.day1, locked_paths: ["nodepools[0].replicas"] },
      },
    };
    await open(page, "/specs/agent-dell/edit", async (p) => {
      await p.route(/\/api\/day1\/specs\/agent-dell(\?.*)?$/, (r) => {
        if (r.request().method() !== "PUT") return json(r, legacy);
        writes.push({ body: r.request().postDataJSON(), url: new URL(r.request().url()) });
        return json(r, mockMR({ repo: "specs", iid: 23 }));
      });
    });
    await expect(lockControl(page, "Replicas").getByRole("radio", { name: "Locked" })).toHaveAttribute("aria-checked", "true");
    await expect(lockControl(page, "Machine configs").getByRole("radio", { name: "Preset" })).toHaveAttribute("aria-checked", "true");
    await lockControl(page, "Replicas").getByRole("radio", { name: "Preset" }).click();
    await reviewAndConfirm(page, /review & update/i);
    await expect(page.getByText("Update MR !23 opened")).toBeVisible();
    const day1 = writes[0].body.spec.day1 as ClusterSpec["spec"]["day1"] & { immutable_paths?: unknown };
    expect(day1.locked_paths).toEqual([]);
    expect(day1).not.toHaveProperty("immutable_paths");
  });

  test("the review previews the cluster file day1 renders, live, with saved locks shown as saved", async ({ page }) => {
    const previews: CreateClusterRequest[] = [];
    await open(page, "/specs/agent-dell/edit", async (p) => {
      await p.route(/\/api\/day1\/specs\/agent-dell(\?.*)?$/, (r) => json(r, AGENT_DELL));
      await p.route("**/api/day1/clusters/preview", (r) => {
        const body = r.request().postDataJSON() as CreateClusterRequest;
        previews.push(body);
        const pool = (body.variables.nodepools as { replicas?: number }[])[0];
        return json(r, {
          path: `sites/${body.site}/mces/${body.mce}/hostedClusters/${body.name}.yaml`,
          yaml: `# specName: agent-dell\nowner:\n  merkaz: "${body.variables.owner_merkaz}"\nmastertag: ${body.variables.openshift_release_version}\nnodepool:\n  - replicas: ${pool.replicas}\n`,
        });
      });
    });

    const review = page.locator("section#review");
    await review.scrollIntoViewIfNeeded();
    const yaml = review.getByTestId("cluster-preview-yaml");
    await expect(yaml).toContainText("mastertag: 4.16.27");
    const first = previews[0];
    expect(first).toMatchObject({
      name: "ocp4-prod-flavor-preview-site1",
      site: "site1",
      mce: "ocp4-prod-mce-site1-a",
      spec_name: "agent-dell",
      spec_version: "1.0.0",
    });
    // What each cluster sets is filled with the template's examples
    expect(first.variables).toMatchObject({ owner_merkaz: "1234", owner_anaf: "56", owner_mador: "7", openshift_release_version: "4.16.27" });
    expect((first.variables.nodepools as Record<string, unknown>[])[0]).toMatchObject({ infra_env: "dell-r660-site1-128c-1024gb-5tb", replicas: 2 });
    await expect(review.getByTestId("preview-samples")).toContainText("Owner · Merkaz");

    // A preset changes the preview as it is typed
    await page.getByLabel("Merkaz", { exact: true }).fill("4321");
    await page.getByTestId("nodepool-0").getByLabel("Replicas", { exact: true }).fill("5");
    await expect(yaml).toContainText('merkaz: "4321"');
    await expect(yaml).toContainText("replicas: 5");

    // A saved lock changed here is sent as saved (day1 would refuse another value), and listed
    await page.getByTestId("nodepool-0-configs").getByRole("button", { name: "Remove nic-ring-buffer (entry 3)" }).click();
    await expect(review.getByTestId("preview-as-saved")).toContainText("Nodepool 1 · Machine configs");
    await expect.poll(() => (previews.at(-1)!.variables.nodepools as { configs: unknown[] }[])[0].configs).toEqual(
      AGENT_DELL.spec.day1.values!.nodepools instanceof Array ? (AGENT_DELL.spec.day1.values!.nodepools[0] as { configs: unknown[] }).configs : []
    );
  });
});

test.describe("Flavor editor: the nodepool ratio (ADR-0040)", () => {
  test("nodepools sized by a ratio are saved as nodepool_ratio, one part per nodepool", async ({ page }) => {
    const writes = await openNew(page);
    await page.getByTestId("spec-name-input").fill("agent-zones");
    // One nodepool has no ratio to choose
    await expect(page.getByTestId("nodepool-ratio")).toHaveCount(0);
    for (let i = 0; i < 2; i++) await page.getByRole("button", { name: "Add nodepool" }).click();
    for (const [i, type] of ["dell", "dell", "cisco"].entries()) {
      await choose(page, page.getByTestId(`nodepool-${i}-configs`).getByRole("combobox", { name: /entry 1 hardware type$/ }), type);
    }

    const ratio = page.getByTestId("nodepool-ratio");
    await expect(ratio).toContainText("Off");
    await ratio.getByRole("switch", { name: "Size the nodepools by a ratio" }).click();
    await expect(page.getByTestId("nodepool-ratio-label")).toHaveText("1:1:1");
    await page.getByTestId("nodepool-1-ratio").getByRole("textbox", { name: "Ratio" }).fill("2");
    await expect(page.getByTestId("nodepool-ratio-label")).toHaveText("1:2:1");

    // A part that is not a whole number from 1 to 100 is refused before anything is sent
    await page.getByTestId("nodepool-2-ratio").getByRole("textbox", { name: "Ratio" }).fill("0");
    await expect(page.getByTestId("nodepool-2-ratio").getByRole("alert")).toContainText("A whole number from 1 to 100");
    await page.getByTestId("nodepool-2-ratio").getByRole("textbox", { name: "Ratio" }).fill("1");

    await reviewAndConfirm(page);
    await expect(page.getByText("Flavor MR !21 opened")).toBeVisible();
    const day1 = writes[0].body.spec.day1;
    expect(day1.nodepool_ratio).toEqual([1, 2, 1]);
    expect(day1.structure).toEqual({ nodepools: [{}, {}, {}] });
  });

  test("one nodepool's replicas move the others by the ratio", async ({ page }) => {
    await openNew(page);
    await page.getByTestId("spec-name-input").fill("agent-zones");
    for (let i = 0; i < 2; i++) await page.getByRole("button", { name: "Add nodepool" }).click();
    await page.getByTestId("nodepool-ratio").getByRole("switch", { name: "Size the nodepools by a ratio" }).click();
    await page.getByTestId("nodepool-1-ratio").getByRole("textbox", { name: "Ratio" }).fill("2");
    const replicas = (i: number) => page.getByTestId(`nodepool-${i}`).getByRole("textbox", { name: "Replicas" });
    const all = async () => Promise.all([0, 1, 2].map((i) => replicas(i).inputValue()));

    await replicas(0).fill("3");
    await expect.poll(all).toEqual(["3", "6", "3"]);
    await expect(page.getByTestId("nodepool-ratio-replicas")).toHaveText("3 · 6 · 3");

    await replicas(1).fill("4");
    await expect.poll(all).toEqual(["2", "4", "2"]);

    // Not a multiple of its part: kept as typed, and flagged
    await replicas(1).fill("5");
    await expect.poll(all).toEqual(["2", "5", "2"]);
    await expect(page.getByTestId("nodepool-1")).toContainText("A multiple of 2");

    // A part that changes keeps the size: 2 · 4 · 2 at 1:2:3 is 2 · 4 · 6
    await replicas(1).fill("4");
    await page.getByTestId("nodepool-2-ratio").getByRole("textbox", { name: "Ratio" }).fill("3");
    await expect.poll(all).toEqual(["2", "4", "6"]);
  });

  test("a flavor saved without a ratio sends none", async ({ page }) => {
    const writes = await openNew(page);
    await page.getByTestId("spec-name-input").fill("agent-plain");
    await choose(page, page.getByTestId("nodepool-0-configs").getByRole("combobox", { name: /entry 1 hardware type$/ }), "dell");
    await reviewAndConfirm(page);
    await expect(page.getByText("Flavor MR !21 opened")).toBeVisible();
    expect(writes[0].body.spec.day1).not.toHaveProperty("nodepool_ratio");
  });
});

// ── Add-ons layout ───────────────────────────────────────────────────────────

test.describe("Flavor editor: the add-ons catalog beside a long selection", () => {
  test("side by side, the catalog stays in view and uses the screen's height; stacked, it keeps its own 500px box", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openNew(page);
    const available = page.getByTestId("addons-available");
    const list = available.locator("div.overflow-y-auto").first();
    await expect(available).toHaveCSS("position", "sticky");
    // 100dvh - 13rem: taller than the old fixed 500px on a 900px screen
    expect(parseFloat(await list.evaluate((el) => getComputedStyle(el).maxHeight))).toBeGreaterThan(500);

    await page.setViewportSize({ width: 800, height: 900 });
    await expect(available).toHaveCSS("position", "static");
    await expect(list).toHaveCSS("max-height", "500px");
  });
});
