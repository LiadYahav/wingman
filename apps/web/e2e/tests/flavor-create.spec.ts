/**
 * Mocked tests of the create form (/clusters/new) on flavors v2
 * (docs/notes/2026-11-08-flavors-v2-api-changes.md §1-§6, §9): locked values
 * shown read-only and sent as the flavor has them, presets prefilled and
 * editable, the configs rule (names fixed, hardware per nodepool), the
 * nodepool defaults, owner numbers, and day1's 422 problems at their fields.
 * The template schema is the one day1 serves for the fixtures'
 * cluster-template.j2; the flavors follow the fixtures' agent-dell,
 * agent-baseline and agent-standard.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
import { ClusterNewPage } from "../pages/cluster-new.page";
import type { ClusterPreview, CreateClusterRequest, Mce, Problem, SpecEntry, TemplateField } from "../../types";

// ── Mock data ─────────────────────────────────────────────────────────────────

/** `GET /specs/template/schema` on the fixtures' cluster-template.j2. */
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
      {
        name: "configs",
        type: "list",
        required: false,
        default: [],
        fields: [{ name: "name", type: "string", required: true, example: "worker-kubeletconfig-reserved" }],
      },
      { name: "node_labels", type: "object", required: false, default: {} },
      { name: "tuning_config", type: "string", required: false, default: "" },
    ],
  },
];

const DELL_CONFIGS = [
  { name: "nm-conf", hardware: "dell" },
  { name: "workers-chrony-configuration" },
  { name: "nic-ring-buffer" },
];

function flavor(name: string, day1: Partial<SpecEntry["spec"]["day1"]>): SpecEntry {
  return {
    apiVersion: "wingman.io/v1",
    kind: "ClusterSpec",
    metadata: { name, description: `The ${name} flavor`, version: "1.0.0", labels: { platform: "agent" } },
    spec: {
      day1: { variables: [], structure: { nodepools: [{ configs: [{}, {}, {}] }] }, locked_paths: [], template: "# template", values: {}, ...day1 },
      day2: { addons: [] },
    },
    load_error: null,
    load_problems: [],
    warnings: [],
  };
}

/** agent-dell, with its team's owner: nodepool 1's configs and owner_anaf locked; replicas and owner_merkaz preset. */
const DELL = flavor("agent-dell", {
  locked_paths: ["nodepools[0].configs", "owner_anaf"],
  values: { owner_merkaz: "1234", owner_anaf: "0056", nodepools: [{ replicas: 2, configs: DELL_CONFIGS }] },
});

/** agent-baseline: the configs rule; dell is nodepool 1's hardware preset. */
const BASELINE = flavor("agent-baseline", {
  locked_paths: ["nodepools[*].configs"],
  values: { nodepools: [{ configs: DELL_CONFIGS }] },
});

/** agent-standard: two nodepools and nothing set, so both start with the nodepool defaults. */
const STANDARD = flavor("agent-standard", { structure: { nodepools: [{ configs: [{}] }, { configs: [{}] }] } });

const MCES: Mce[] = [
  {
    name: "ocp4-prod-mce-site1-a", site: "site1", env: "prod", letter: "a", follows_convention: true, naming_problems: [],
    default_mastertag: "4.16.27-x86_64", hub_version: "4.16.27-x86_64", cluster_count: 4, stray_files: [], problems: [],
  },
];

const NAME = "ocp4-prod-falcon-site1";

const PREVIEW: ClusterPreview = {
  yaml: '# specName: "agent-dell"\n# specVersion: "1.0.0"\nnodepool:\n  - configs:\n      - name: nm-conf-prod-falcon-site1-dell\n',
  path: `sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/${NAME}.yaml`,
};

function problem(detail: string, problems: string[]): Problem {
  return {
    type: "/problems/validation-error",
    title: "Validation Error",
    status: 422,
    detail,
    instance: "/api/day1/clusters/preview",
    code: "VALIDATION_ERROR",
    request_id: "req_0000000000000042",
    details: { problems },
  };
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: status >= 400 ? "application/problem+json" : "application/json",
    body: JSON.stringify(body),
  });

// ── Mock helper ───────────────────────────────────────────────────────────────

async function setup(page: Page, { preview }: { preview?: (route: Route) => Promise<void> } = {}) {
  const previews: CreateClusterRequest[] = [];
  await injectAdminAuth(page);
  // Also answers GET /api/day1/machine-configs with the fixtures' catalogue and defaults
  await mockDashboardApis(page);
  await page.route("**/api/day1/specs", (r) => json(r, [DELL, BASELINE, STANDARD]));
  await page.route("**/api/day1/specs/template/schema", (r) => json(r, SCHEMA));
  await page.route("**/api/day1/sites", (r) => json(r, ["site1"]));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
  await page.route("**/api/day1/mces/*/openshift-versions", (r) =>
    json(r, { mce: "ocp4-prod-mce-site1-a", versions: ["4.18.56", "4.16.27"], problems: [] })
  );
  await page.route("**/api/day1/mces/*/infraenvs", (r) =>
    json(r, { ...problem("Live cluster status is disabled", []), status: 501, code: "FEATURE_DISABLED" }, 501)
  );
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/clusters/preview", (r) => {
    previews.push(r.request().postDataJSON());
    return preview ? preview(r) : json(r, PREVIEW);
  });
  return previews;
}

const field = (page: Page, path: string) => page.locator(`[data-field-path="${path}"]`);
const configs = (page: Page, nodepool: number) => page.getByTestId(`nodepool-${nodepool}-configs`);
const hardware = (page: Page, nodepool: number, entry: number) =>
  page.getByRole("combobox", { name: `Nodepool ${nodepool + 1} configs: entry ${entry + 1} hardware type` });
const infraEnvs = (page: Page) => page.getByPlaceholder("e.g. dell-r660-site1-128c-1024gb-5tb");

/** The nodepool defaults (`nodepool-defaults.yaml` on the fixtures, `mockMachineConfigs`). */
const DEFAULTS = ["nm-conf", "workers-chrony-configuration", "nic-ring-buffer"];
/** A config picker's text: the chosen name, then the dropdown's arrow. */
const picked = (names: string[]) => names.map((name) => new RegExp(`^${name}\\W*$`));

async function pickHardware(page: Page, nodepool: number, entry: number, type: string) {
  await hardware(page, nodepool, entry).click();
  // By its label alone: "dell" is not "dell-data"
  await page.getByRole("option").filter({ has: page.getByText(type, { exact: true }) }).click();
  await expect(hardware(page, nodepool, entry)).toContainText(type);
  // Closed, so the next picker's options are the only ones
  await expect(page.getByRole("option")).toHaveCount(0);
}

/** Choose the flavor and the cluster's name, site, MCE and version (detected from the name). */
async function start(form: ClusterNewPage, name: string) {
  await form.goto();
  await form.chooseSpec(name);
  await form.fillName(NAME);
  await expect(form.mceSelect).toContainText("ocp4-prod-mce-site1-a");
  await expect(form.versionSelect).toContainText("4.16.27");
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe("Create form: a flavor's locks and presets", () => {
  test("a locked value is read-only, shows the flavor's value, and is sent as the flavor has it", async ({ page }) => {
    const previews = await setup(page);
    const form = new ClusterNewPage(page);
    await start(form, "agent-dell");

    // owner_anaf: the flavor's 0056 behind a lock, no input
    const anaf = field(page, "owner_anaf");
    await expect(anaf.locator('[data-flavor-badge="locked"]')).toBeVisible();
    await expect(anaf).toContainText("0056");
    await expect(anaf.getByRole("textbox")).toHaveCount(0);

    // Nodepool 1's configs: the file names day1 writes for this cluster, nothing to change
    const locked = configs(page, 0);
    await expect(field(page, "nodepools[0].configs").locator('[data-flavor-badge="locked"]')).toBeVisible();
    await expect(locked.getByRole("listitem")).toHaveText([
      "nm-conf-prod-falcon-site1-dell",
      "workers-chrony-configuration",
      "nic-ring-buffer",
    ]);
    await expect(locked.getByRole("combobox")).toHaveCount(0);
    await expect(locked.getByRole("button")).toHaveCount(0);

    await form.templateInput("7").fill("7");
    await infraEnvs(page).first().fill("dell-r660-site1-128c-1024gb-5tb");
    await form.review();
    await expect(form.reviewDialog).toBeVisible();

    const sent = previews[0].variables as { owner_anaf: unknown; nodepools: { configs: unknown }[] };
    expect(sent.owner_anaf).toBe("0056");
    // Exactly the flavor's value: day1 compares it as JSON
    expect(sent.nodepools[0].configs).toEqual(DELL_CONFIGS);
  });

  test("a preset is prefilled, marked, and yours to change", async ({ page }) => {
    const previews = await setup(page);
    const form = new ClusterNewPage(page);
    await start(form, "agent-dell");

    const merkaz = field(page, "owner_merkaz");
    await expect(merkaz.locator('[data-flavor-badge="preset"]')).toBeVisible();
    await expect(form.templateInput("1234")).toHaveValue("1234");
    const replicas = field(page, "nodepools[0].replicas");
    await expect(replicas.locator('[data-flavor-badge="preset"]')).toBeVisible();
    await expect(replicas.getByRole("textbox")).toHaveValue("2");
    await expect(page.getByTestId("flavor-legend")).toContainText("yours to change");

    await form.templateInput("1234").fill("4321");
    await replicas.getByRole("textbox").fill("3");
    await form.templateInput("7").fill("7");
    await infraEnvs(page).first().fill("dell-r660-site1-128c-1024gb-5tb");
    await form.review();
    await expect(form.reviewDialog).toBeVisible();

    const sent = previews[0].variables as { owner_merkaz: unknown; nodepools: { replicas: unknown }[] };
    expect(sent.owner_merkaz).toBe("4321");
    expect(sent.nodepools[0].replicas).toBe("3");
  });

  test("the configs rule fixes every nodepool's names; each nodepool picks its hardware", async ({ page }) => {
    const previews = await setup(page);
    const form = new ClusterNewPage(page);
    await start(form, "agent-baseline");

    await expect(page.getByTestId("configs-rule")).toContainText("Every nodepool has exactly nm-conf, workers-chrony-configuration, nic-ring-buffer");
    const first = configs(page, 0);
    await expect(field(page, "nodepools[0].configs").locator('[data-flavor-badge="rule"]')).toContainText("names locked");
    await expect(first.getByTestId("nodepool-0-configs-entry-1-name")).toHaveText("workers-chrony-configuration");
    // The names: no picker, no remove, no add; the hardware: the flavor's dell, as a preset
    await expect(first.getByRole("combobox")).toHaveCount(1);
    await expect(first.getByRole("button")).toHaveCount(0);
    await expect(hardware(page, 0, 0)).toContainText("dell");
    await expect(first).toContainText("Written as nm-conf-prod-falcon-site1-dell");

    // A nodepool added here has the rule's names, and its own hardware to choose
    await page.getByTestId("add-nodepools").click();
    const second = configs(page, 1);
    await expect(second.locator('[data-testid$="-name"]')).toHaveText(["nm-conf", "workers-chrony-configuration", "nic-ring-buffer"]);
    await expect(hardware(page, 1, 0)).toContainText("Hardware…");

    await form.templateInput("1234").fill("1234");
    await form.templateInput("56").fill("56");
    await form.templateInput("7").fill("7");
    await infraEnvs(page).nth(0).fill("dell-r660-site1-128c-1024gb-5tb");
    await infraEnvs(page).nth(1).fill("cisco-c240-site1-64c-512gb-20tb");
    await form.review();
    await expect(form.formProblems).toContainText("Nodepool 2 › Configs › nm-conf: Choose the hardware type (cisco, dell, dell-data)");
    expect(previews).toHaveLength(0);

    await pickHardware(page, 1, 0, "cisco");
    await expect(second).toContainText("Written as nm-conf-prod-falcon-site1-cisco");
    await pickHardware(page, 0, 0, "dell-data");
    await form.review();
    await expect(form.reviewDialog).toBeVisible();

    const sent = previews[0].variables as { nodepools: { configs: unknown }[] };
    expect(sent.nodepools.map((pool) => pool.configs)).toEqual([
      [{ name: "nm-conf", hardware: "dell-data" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
      [{ name: "nm-conf", hardware: "cisco" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
    ]);
  });

  test("the nodepool defaults fill a nodepool the flavor does not set, and one added here", async ({ page }) => {
    const previews = await setup(page);
    const form = new ClusterNewPage(page);
    await start(form, "agent-standard");

    // The flavor's two nodepools set no configs: both start with the defaults, which stay editable
    for (const nodepool of [0, 1]) {
      const list = configs(page, nodepool);
      await expect(list.getByRole("combobox", { name: /^Nodepool \d configs: entry \d$/ })).toHaveText([
        ...picked(DEFAULTS),
      ]);
      await expect(list.getByTestId(`nodepool-${nodepool}-configs-add`)).toBeVisible();
    }
    // The flavor's nodepools stay; one added here can go again
    await expect(page.getByRole("button", { name: /^Remove nodepool/ })).toHaveCount(0);
    await page.getByTestId("add-nodepools").click();
    await expect(configs(page, 2).getByRole("combobox", { name: /^Nodepool 3 configs: entry \d$/ })).toHaveText([
      ...picked(DEFAULTS),
    ]);
    await page.getByRole("button", { name: "Remove nodepool 3" }).click();
    await expect(configs(page, 2)).toHaveCount(0);

    // Edit nodepool 2's list: drop nic-ring-buffer, add the kubevirt tuning
    await configs(page, 1).getByRole("button", { name: "Remove nic-ring-buffer (entry 3)" }).click();
    await configs(page, 1).getByTestId("nodepool-1-configs-add").click();
    await page.getByRole("option", { name: /^kubevirt-worker-tuning/ }).click();

    await form.templateInput("1234").fill("1234");
    await form.templateInput("56").fill("56");
    await form.templateInput("7").fill("7");
    await infraEnvs(page).nth(0).fill("dell-r660-site1-128c-1024gb-5tb");
    await infraEnvs(page).nth(1).fill("dell-r760-site1-64c-512gb-20tb");
    await pickHardware(page, 0, 0, "dell");
    await pickHardware(page, 1, 0, "dell-data");
    await form.review();
    await expect(form.reviewDialog).toBeVisible();

    const sent = previews[0].variables as { nodepools: { configs: unknown }[] };
    expect(sent.nodepools.map((pool) => pool.configs)).toEqual([
      [{ name: "nm-conf", hardware: "dell" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
      [{ name: "nm-conf", hardware: "dell-data" }, { name: "workers-chrony-configuration" }, { name: "kubevirt-worker-tuning" }],
    ]);
  });

  test("a nodepool added beside a positional lock starts with the defaults, not the lock", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await start(form, "agent-dell");

    await page.getByTestId("add-nodepools").click();
    await expect(field(page, "nodepools[1].configs").locator("[data-flavor-badge]")).toHaveCount(0);
    await expect(configs(page, 1).getByRole("combobox", { name: /^Nodepool 2 configs: entry \d$/ })).toHaveText([
      ...picked(DEFAULTS),
    ]);
    await expect(hardware(page, 1, 0)).toContainText("Hardware…");
  });
});

test.describe("Create form: owners and day1's problems", () => {
  test("an owner takes digits only, on a numeric keypad, and the review refuses anything else", async ({ page }) => {
    const previews = await setup(page);
    const form = new ClusterNewPage(page);
    await start(form, "agent-standard");

    const mador = page.getByTestId("owner-input-owner_mador");
    await expect(mador).toHaveAttribute("inputmode", "numeric");
    await mador.fill("5x");
    await expect(mador).toHaveAttribute("aria-invalid", "true");
    await expect(field(page, "owner_mador").getByRole("alert")).toHaveText("Digits 0-9 only, like 1234");
    await form.templateInput("1234").fill("12345678901");
    await expect(field(page, "owner_merkaz").getByRole("alert")).toHaveText("At most 10 digits (this is 11)");

    await form.review();
    await expect(form.formProblems).toContainText("Owner Mador: Digits 0-9 only, like 1234");
    await expect(form.formProblems).toContainText("Owner Merkaz: At most 10 digits (this is 11)");
    expect(previews).toHaveLength(0);

    // A leading zero is a number too, and is sent as the text typed
    await mador.fill("007");
    await expect(field(page, "owner_mador").getByRole("alert")).toHaveCount(0);
    await expect(mador).toHaveAttribute("aria-invalid", "false");
  });

  test("day1's 422 problems show at their fields; the rest are listed above the button", async ({ page }) => {
    const previews = await setup(page, {
      preview: (r) =>
        json(
          r,
          problem("the cluster's inputs are not acceptable", [
            "owner_anaf: must be a number of 1 to 10 digits, sent as a string like \"1234\" (got '56 ')",
            "nodepools[1].configs[2]: no machine config 'nic-ring-buffer' in mc-files/",
            "nodepools[0].configs: locked by flavor agent-standard to [], the request sends [...]",
            "nodepools[2].replicas: the flavor locks it to 3, but the cluster has no nodepools[2]",
            "nodepool[0]: infraEnvName is missing",
          ]),
          422
        ),
    });
    const form = new ClusterNewPage(page);
    await start(form, "agent-standard");
    await form.templateInput("1234").fill("1234");
    await form.templateInput("56").fill("56");
    await form.templateInput("7").fill("7");
    await infraEnvs(page).nth(0).fill("dell-r660-site1-128c-1024gb-5tb");
    await infraEnvs(page).nth(1).fill("dell-r760-site1-64c-512gb-20tb");
    await pickHardware(page, 0, 0, "dell");
    await pickHardware(page, 1, 0, "dell");
    await form.review();
    expect(previews).toHaveLength(1);
    await expect(form.reviewDialog).not.toBeVisible();

    // At the field, without the path
    await expect(field(page, "owner_anaf").getByRole("alert")).toHaveText(
      "must be a number of 1 to 10 digits, sent as a string like \"1234\" (got '56 ')"
    );
    await expect(field(page, "nodepools[0].configs").locator("[data-field-problems]")).toContainText("locked by flavor agent-standard");
    // A config entry's problem at that entry of that nodepool
    await expect(page.getByTestId("nodepool-1-configs-entry-2").getByRole("alert")).toContainText(
      "no machine config 'nic-ring-buffer' in mc-files/"
    );
    await expect(page.getByTestId("nodepool-0-configs-entry-2").getByRole("alert")).toHaveCount(0);

    // What no field of the form is about stays above the button
    await expect(form.formProblems).toContainText("nodepools[2].replicas: the flavor locks it to 3");
    await expect(form.formProblems).toContainText("nodepool[0]: infraEnvName is missing");
    await expect(form.formProblems).toContainText("And 3 more, marked at the fields they are about.");
    await expect(form.formProblems).not.toContainText("owner_anaf");
    await expect(form.formProblems).toContainText("request req_0000000000000042");

    // A field's problem goes once the field changes
    await form.templateInput("56").fill("57");
    await expect(field(page, "owner_anaf").getByRole("alert")).toHaveCount(0);
    await expect(page.getByTestId("nodepool-1-configs-entry-2").getByRole("alert")).toHaveCount(1);
  });
});
