/**
 * Tuning profiles (ADR-0061, docs/notes/2026-11-15-tuning-profiles-api.md),
 * mocked: picking a nodepool's profiles in a flavor from `tuning/` (one
 * PerformanceProfile per nodepool, a Tuned's PerformanceProfile one click
 * away), locking them on every nodepool, creating a cluster from a flavor
 * that locks them, day1's 422 for a name `tuning/` does not have shown at its
 * field, and drift plus a sync whose confirmation names the nodepools that
 * may reboot. With configs the same on every nodepool, the panel's tuning
 * switch: on from Nodepool 1's names, off when the nodepools differ, an empty
 * rule refused, and saved flavors loading as they were saved.
 */

import { test, expect, type Page, type Request, type Route } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, json, mockDashboardApis, mockMachineConfigsWithGeneric, mockMR } from "../fixtures/api-handlers";
import { mockTuningProfiles } from "../fixtures/tuning";
import { ClusterNewPage } from "../pages/cluster-new.page";
import type {
  ClusterDetail, ClusterDrift, ClusterPreview, ClusterSpec, CreateClusterRequest, Mce, SpecDetail, SpecEntry, SyncPreview, TemplateField,
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

// ── The every-nodepool panel (ADR-0061's 2026-11-16 amendment) ────────────────

const CONFIGS_RULE = "nodepools[*].configs";
const ruleSwitch = (page: Page) => page.getByRole("switch", { name: "Same tuning profiles on every nodepool" });
const rulePicker = (page: Page) => page.getByTestId("rule-tuning");
const ruleAdd = (page: Page) => page.getByRole("combobox", { name: "Tuning profiles on every nodepool: add a profile" });
const ruleLine = (page: Page, index: number) => page.getByTestId(`nodepool-${index}-tuning-rule`);
const cardLocks = (page: Page) => page.getByRole("radiogroup", { name: "Tuning profiles: preset or locked" });
const EMPTY_RULE = "Choose the profiles every nodepool gets, or turn off the same tuning profiles";

async function configsMode(page: Page, mode: RegExp) {
  await page.getByRole("radiogroup", { name: "Machine configs and tuning profiles", exact: true }).getByRole("radio", { name: mode }).click();
}

/** A new flavor named `name`; its creates are collected. */
async function newFlavor(page: Page, name: string) {
  await base(page);
  const writes: ClusterSpec[] = [];
  await page.route("**/api/day1/specs", (r) => {
    if (r.request().method() !== "POST") return json(r, []);
    writes.push(r.request().postDataJSON());
    return json(r, mockMR({ repo: "specs", iid: 32 }), 201);
  });
  await go(page, "/specs/new");
  await page.getByTestId("spec-name-input").fill(name);
  return writes;
}

async function create(page: Page) {
  await page.getByRole("button", { name: /review & create/i }).click();
  await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
  await expect(page.getByText("Flavor MR !32 opened")).toBeVisible();
}

const tuningOf = (spec: ClusterSpec) => (spec.spec.day1.values?.nodepools as { tuning_config?: unknown }[]).map((p) => p.tuning_config);

test.describe("Tuning profiles in the every-nodepool panel", () => {
  test("the same on every nodepool includes Nodepool 1's profiles, locked as a rule, on every nodepool", async ({ page }) => {
    const writes = await newFlavor(page, "agent-rule-tuned");
    await choose(page, addBox(page, 0), "tuned-network-latency");
    await choose(page, addBox(page, 0), "performance-pinned");

    await configsMode(page, /The same on every nodepool/);
    await expect(ruleSwitch(page)).toBeChecked();
    await expect(page.getByTestId("rule-tuning-part")).toContainText("Locked as a rule");
    await expect(rulePicker(page).locator("[data-testid^=tuning-profile-]")).toHaveText([/^tuned-network-latency/, /^performance-pinned/]);
    // The card names the rule's profiles: no picker or lock of its own
    await expect(ruleLine(page, 0)).toHaveText("Gets the rule's tuning profiles: tuned-network-latency, performance-pinned");
    await expect(picker(page, 0)).toHaveCount(0);
    await expect(cardLocks(page)).toHaveCount(0);

    // A nodepool added under the rule gets the rule's profiles; the panel's picker edits every nodepool's
    await page.getByRole("button", { name: "Add nodepool" }).click();
    await expect(ruleLine(page, 1)).toHaveText("Gets the rule's tuning profiles: tuned-network-latency, performance-pinned");
    await choose(page, ruleAdd(page), "tuned-pinned-irq");
    await expect(ruleLine(page, 1)).toHaveText("Gets the rule's tuning profiles: tuned-network-latency, performance-pinned, tuned-pinned-irq");

    await create(page);
    expect(writes[0].spec.day1.locked_paths).toEqual([CONFIGS_RULE, RULE]);
    const names = ["tuned-network-latency", "performance-pinned", "tuned-pinned-irq"];
    expect(tuningOf(writes[0])).toEqual([names, names]);
  });

  test("nodepools with different profiles keep them: the switch starts off and nothing is overwritten", async ({ page }) => {
    const writes = await newFlavor(page, "agent-rule-own");
    await choose(page, addBox(page, 0), "tuned-network-latency");
    await page.getByRole("button", { name: "Add nodepool" }).click();
    await choose(page, addBox(page, 1), "tuned-sysctl-baseline");

    await configsMode(page, /The same on every nodepool/);
    await expect(ruleSwitch(page)).not.toBeChecked();
    await expect(page.getByTestId("rule-tuning-differ")).toHaveText(
      "The nodepools name different tuning profiles, so each keeps its own. Turning this on gives every nodepool Nodepool 1's: tuned-network-latency."
    );
    // Each card keeps its picker, a preset; the lock is the panel's switch
    await expect(chips(page, 0)).toHaveText([/^tuned-network-latency/]);
    await expect(chips(page, 1)).toHaveText([/^tuned-sysctl-baseline/]);
    await expect(cardLocks(page)).toHaveCount(0);
    await expect(page.locator('[data-field="nodepools[1].tuning_config"]')).toContainText(
      "Prefilled: a cluster may change them. To lock them on every nodepool, use the switch under On every nodepool."
    );

    await create(page);
    expect(writes[0].spec.day1.locked_paths).toEqual([CONFIGS_RULE]);
    expect(tuningOf(writes[0])).toEqual([["tuned-network-latency"], ["tuned-sysctl-baseline"]]);
  });

  test("on with nothing picked blocks the save; off gives the cards their pickers back; each nodepool its own keeps the names", async ({ page }) => {
    const writes = await newFlavor(page, "agent-rule-switch");
    await page.getByRole("button", { name: "Add nodepool" }).click();

    // No nodepool names a profile yet: the same on every one, so the panel includes tuning
    await configsMode(page, /The same on every nodepool/);
    await expect(ruleSwitch(page)).toBeChecked();
    await expect(rulePicker(page)).toContainText("No tuning profiles.");
    await expect(ruleLine(page, 1)).toHaveText("Gets the rule's tuning profiles: none");
    await expect(rulePicker(page)).toContainText(EMPTY_RULE);
    await page.getByRole("button", { name: /review & create/i }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("alert").filter({ hasText: "before saving" })).toContainText(`Every nodepool · Tuning profiles: ${EMPTY_RULE}`);
    expect(writes).toHaveLength(0);

    await choose(page, ruleAdd(page), "tuned-network-latency");
    await expect(rulePicker(page)).not.toContainText(EMPTY_RULE);

    // Off: each card has its picker again, the rule's names its preset
    await ruleSwitch(page).click();
    await expect(ruleSwitch(page)).not.toBeChecked();
    await expect(chips(page, 0)).toHaveText([/^tuned-network-latency/]);
    await expect(chips(page, 1)).toHaveText([/^tuned-network-latency/]);
    // Once they differ, turning it on gives every nodepool Nodepool 1's
    await picker(page, 1).getByRole("button", { name: "Remove tuning profile tuned-network-latency" }).click();
    await expect(page.getByTestId("rule-tuning-differ")).toContainText("Nodepool 1's: tuned-network-latency.");
    await ruleSwitch(page).click();
    await expect(ruleLine(page, 1)).toHaveText("Gets the rule's tuning profiles: tuned-network-latency");

    // Each nodepool its own: both rules go, each nodepool keeps its configs and names as presets
    await configsMode(page, /Each nodepool its own/);
    await expect(page.getByTestId("configs-rule")).toHaveCount(0);
    await expect(chips(page, 1)).toHaveText([/^tuned-network-latency/]);
    await expect(cardLocks(page)).toHaveCount(2);
    await expect(cardLocks(page).nth(1).getByRole("radio", { name: "Preset" })).toHaveAttribute("aria-checked", "true");

    await create(page);
    expect(writes[0].spec.day1.locked_paths).toEqual([]);
    expect(tuningOf(writes[0])).toEqual([["tuned-network-latency"], ["tuned-network-latency"]]);
  });

  test("a saved flavor loads as it was saved: the panel's switch off without the rule, on with it, and the 3.37.0 card lock", async ({ page }) => {
    const configs = [{ name: "nm-conf", hardware: "generic" }, { name: "workers-chrony-configuration" }];
    const saved = (name: string, locked: string[]): SpecDetail => ({
      apiVersion: "wingman.io/v1",
      kind: "ClusterSpec",
      metadata: { name, description: `The ${name} flavor`, version: "1.0.0", labels: {} },
      spec: {
        day1: {
          variables: [],
          structure: { nodepools: [{}, {}] },
          locked_paths: locked,
          template: "# cluster-template.j2",
          values: { nodepools: [0, 1].map(() => ({ configs, tuning_config: ["tuned-network-latency"] })) },
        },
        day2: { addons: [] },
      },
      load_error: null,
      load_problems: [],
      warnings: [],
      last_commit_id: "cccccccc33333333cccccccc33333333cccccccc",
    });
    const flavors = [saved("rule-preset", [CONFIGS_RULE]), saved("rule-locked", [CONFIGS_RULE, RULE]), saved("card-locked", [RULE])];
    const writes: ClusterSpec[] = [];
    await base(page);
    await page.route("**/api/day1/mces/*/openshift-versions", (r) => json(r, { mce: MCES[0].name, versions: ["4.16.27"], problems: [] }));
    await page.route("**/api/day1/clusters/preview", (r) => json(r, { yaml: "", path: "" }));
    await page.route(/\/api\/day1\/specs\/[a-z-]+(\?.*)?$/, (r) => {
      const name = new URL(r.request().url()).pathname.split("/").at(-1);
      if (r.request().method() !== "PUT") return json(r, flavors.find((f) => f.metadata.name === name));
      writes.push(r.request().postDataJSON());
      return json(r, mockMR({ repo: "specs", iid: 33 }));
    });

    // The configs rule without the tuning rule: the switch is off though the nodepools agree
    await go(page, "/specs/rule-preset/edit");
    await expect(ruleSwitch(page)).not.toBeChecked();
    await expect(chips(page, 1)).toHaveText([/^tuned-network-latency/]);
    await page.getByTestId("spec-version-input").fill("1.1.0");
    await page.getByRole("button", { name: /review & update/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
    await expect(page.getByText("Update MR !33 opened")).toBeVisible();
    expect(writes[0].spec.day1.locked_paths).toEqual([CONFIGS_RULE]);
    expect(tuningOf(writes[0])).toEqual([["tuned-network-latency"], ["tuned-network-latency"]]);

    // With it: on, the cards name the rule's profiles
    await go(page, "/specs/rule-locked/edit");
    await expect(ruleSwitch(page)).toBeChecked();
    await expect(ruleLine(page, 1)).toHaveText("Gets the rule's tuning profiles: tuned-network-latency");

    // Configs per nodepool with the tuning rule (3.37.0): the card's lock, as before
    await go(page, "/specs/card-locked/edit");
    await expect(page.getByTestId("configs-rule")).toHaveCount(0);
    await expect(cardLocks(page).first().getByRole("radio", { name: "Locked" })).toHaveAttribute("aria-checked", "true");
    await expect(page.locator('[data-field="nodepools[1].tuning_config"]')).toContainText("Locked on every nodepool");
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
