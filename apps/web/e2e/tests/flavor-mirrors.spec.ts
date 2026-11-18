/**
 * A flavor's image mirrors (ADR-0063, mocked): `image_content_sources` (the
 * cluster's own mirrors) and `disable_idms_merge` (drop the MCE's default
 * mirrors), each a preset or locked as a whole. The flavor editor saves them
 * as values, refuses dropping the MCE's mirrors with none of the cluster's
 * own, and shows day1's problems at the group; the flavor's Overview lists
 * them; the create form sends a preset as edited (the switch as a JSON
 * boolean) and shows a locked one read only. Invented hosts only.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis, mockMachineConfigs, mockMR } from "../fixtures/api-handlers";
import { ClusterNewPage } from "../pages/cluster-new.page";
import type { ClusterPreview, ClusterSpec, CreateClusterRequest, ErrorCode, Mce, SpecDetail, SpecEntry, TemplateField } from "../../types";

// ── Mock data ────────────────────────────────────────────────────────────────

const OPERATORS = { source: "registry.example.com/team/operators", mirrors: ["mirror.example.com/team/operators"] };
const RELEASE = { source: "registry.example.com/ocp/release", mirrors: ["mirror.example.com/ocp/release", "mirror2.example.com/ocp/release"] };
const STATIC = [{ name: "workers-chrony-configuration" }];

/** The fixture template's inputs with the two mirror inputs it reads. */
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
      { name: "replicas", type: "string", required: false, default: 2 },
      { name: "configs", type: "list", required: false, default: [], fields: [{ name: "name", type: "string", required: true }] },
    ],
  },
  {
    name: "image_content_sources",
    type: "list",
    required: false,
    default: [],
    fields: [
      { name: "source", type: "string", required: true },
      { name: "mirrors", type: "string", required: true },
    ],
  },
  { name: "disable_idms_merge", type: "string", required: false, default: false },
];

function flavor(name: string, day1: Partial<SpecEntry["spec"]["day1"]>): SpecDetail {
  return {
    apiVersion: "wingman.io/v1",
    kind: "ClusterSpec",
    metadata: { name, description: `The ${name} flavor`, version: "1.0.0", labels: {} },
    spec: {
      day1: {
        variables: [], structure: { nodepools: [{}] }, locked_paths: [], template: "# template",
        values: { nodepools: [{ configs: STATIC }] }, ...day1,
      },
      day2: { addons: [] },
    },
    load_error: null,
    load_problems: [],
    warnings: [],
    last_commit_id: "aaaaaaaa11111111aaaaaaaa11111111aaaaaaaa",
  };
}

/** Its own mirrors as a preset; the MCE's defaults dropped, as a preset too. */
const OWN = flavor("own-mirrors", {
  values: { nodepools: [{ configs: STATIC }], image_content_sources: [OPERATORS, RELEASE], disable_idms_merge: true },
});
/** Both locked: every cluster gets exactly these mirrors, and keeps the MCE's. */
const FIXED = flavor("fixed-mirrors", {
  locked_paths: ["image_content_sources", "disable_idms_merge"],
  values: { nodepools: [{ configs: STATIC }], image_content_sources: [OPERATORS], disable_idms_merge: false },
});

const MCES: Mce[] = [
  {
    name: "ocp4-prod-mce-site1-a", site: "site1", env: "prod", letter: "a", follows_convention: true, naming_problems: [],
    default_mastertag: "4.16.27-x86_64", hub_version: "4.16.27-x86_64", cluster_count: 4, stray_files: [], problems: [],
  },
];

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: status >= 400 ? "application/problem+json" : "application/json", body: JSON.stringify(body) });

function problem(status: number, code: ErrorCode, detail: string, details: Record<string, unknown> = {}) {
  return {
    type: `/problems/${code.toLowerCase().replace(/_/g, "-")}`, title: code.replace(/_/g, " "), status, detail,
    instance: "/api/day1/specs", code, request_id: "req_e2e0000000000063", details,
  };
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const field = (page: Page, path: string) => page.locator(`[data-field="${path}"]`);
const keepSwitch = (page: Page) => page.getByRole("switch", { name: "Keep the MCE's default mirrors" });
const mirrors = (page: Page) => page.getByTestId("flavor-mirror-entries");

/** The flavor editor at `path`, its reads mocked; each save's body is collected. */
async function openEditor(page: Page, path: string, onSave: (route: Route) => Promise<void>, stored?: SpecDetail): Promise<ClusterSpec[]> {
  const writes: ClusterSpec[] = [];
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/specs/template", (r) => json(r, "# cluster-template.j2"));
  await page.route("**/api/day1/specs/template/schema**", (r) => json(r, SCHEMA));
  await page.route("**/api/day1/machine-configs", (r) => json(r, mockMachineConfigs));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
  const save = async (r: Route) => {
    writes.push(r.request().postDataJSON());
    return onSave(r);
  };
  await page.route("**/api/day1/specs", (r) => (r.request().method() === "POST" ? save(r) : json(r, [])));
  if (stored) {
    await page.route(new RegExp(`/api/day1/specs/${stored.metadata.name}(\\?.*)?$`), (r) =>
      r.request().method() === "PUT" ? save(r) : json(r, stored)
    );
  }
  await go(page, path);
  return writes;
}

/** A new flavor with nodepool 1's network hardware chosen, so only the mirrors are in question. */
async function newFlavor(page: Page, onSave: (route: Route) => Promise<void> = (r) => json(r, mockMR({ repo: "specs", iid: 63 }), 201)) {
  const writes = await openEditor(page, "/specs/new", onSave);
  await expect(page.getByRole("heading", { name: "New Flavor" })).toBeVisible();
  await page.getByTestId("spec-name-input").fill("agent-mirrors");
  await page.getByTestId("nodepool-0-configs").getByRole("combobox", { name: /entry 1 hardware type$/ }).click();
  await page.getByRole("option").filter({ has: page.getByText("dell", { exact: true }) }).click();
  await expect(page.getByRole("option")).toHaveCount(0);
  return writes;
}

/** Add an entry at the end of the list, with its source and mirrors. */
async function addEntry(page: Page, list: ReturnType<Page["getByTestId"]>, index: number, source: string, ...mirrorNames: string[]) {
  await list.getByRole("button", { name: "Add image mirror" }).click();
  await list.getByLabel(`Image mirrors ${index + 1}: source`).fill(source);
  for (const [j, mirror] of mirrorNames.entries()) {
    // A new entry starts with one mirror to type; each further one is added to it
    if (j > 0) await list.getByRole("button", { name: "Add mirror" }).nth(index).click();
    await list.getByLabel(`Image mirrors ${index + 1}: mirror ${j + 1}`).fill(mirror);
  }
}

async function reviewAndConfirm(page: Page, button: RegExp = /review & create/i) {
  await page.getByRole("button", { name: button }).click();
  await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
}

// ── The flavor editor ────────────────────────────────────────────────────────

test.describe("Image mirrors in the flavor editor", () => {
  test("unset, nothing is written; set, the entries and the switch are saved as values, each locked as a whole", async ({ page }) => {
    const writes = await newFlavor(page);
    await expect(field(page, "image_content_sources")).toContainText("None: nothing is written, and the MCE's default mirrors apply.");
    await expect(keepSwitch(page)).toBeChecked();
    await expect(field(page, "disable_idms_merge")).toContainText("Not set: kept, as before.");

    await addEntry(page, mirrors(page), 0, OPERATORS.source, ...OPERATORS.mirrors);
    await addEntry(page, mirrors(page), 1, RELEASE.source, ...RELEASE.mirrors);
    await keepSwitch(page).click();
    await expect(keepSwitch(page)).not.toBeChecked();
    await expect(field(page, "disable_idms_merge")).toContainText("Off: only the cluster's own mirrors");
    await page.getByRole("radiogroup", { name: "The cluster's own mirrors: preset or locked" }).getByRole("radio", { name: "Locked" }).click();
    await expect(field(page, "image_content_sources")).toContainText("Fixed: every cluster gets exactly these mirrors.");

    // The review says what every cluster gets, in words
    const review = page.locator("section#review");
    await expect(review).toContainText("Image mirrors");
    await expect(review).toContainText(`${OPERATORS.source} → ${OPERATORS.mirrors[0]}`);
    await expect(review).toContainText("Dropped: only the cluster's own mirrors");

    await reviewAndConfirm(page);
    await expect(page.getByText("Flavor MR !63 opened")).toBeVisible();
    const day1 = writes[0].spec.day1;
    expect(day1.values?.image_content_sources).toEqual([OPERATORS, RELEASE]);
    expect(day1.values?.disable_idms_merge).toBe(true);
    expect(day1.locked_paths).toEqual(["image_content_sources"]);
  });

  test("dropping the MCE's mirrors with none of the cluster's own, or a source twice, stops the review", async ({ page }) => {
    const writes = await newFlavor(page);
    await keepSwitch(page).click();
    await expect(field(page, "disable_idms_merge")).toContainText(
      "The cluster would have no image mirrors: add its own, or keep the MCE's default mirrors"
    );
    await addEntry(page, mirrors(page), 0, OPERATORS.source, "mirror.example.com/a");
    await addEntry(page, mirrors(page), 1, OPERATORS.source, "mirror.example.com/b");
    await expect(field(page, "disable_idms_merge")).not.toContainText("would have no image mirrors");
    await expect(field(page, "image_content_sources")).toContainText(
      `Entry 2: ${OPERATORS.source} is listed twice (entry 1): give all its mirrors in one entry`
    );
    await expect(mirrors(page).getByLabel("Image mirrors 2: source")).toHaveAttribute("aria-invalid", "true");

    await page.getByRole("button", { name: /review & create/i }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(writes).toHaveLength(0);
  });

  test("day1's problems about the mirrors are shown at the group, entry by entry", async ({ page }) => {
    const problems = [
      "image_content_sources: the specs project's cluster-template.j2 does not read this input, so a cluster created from this flavor would get no image mirrors",
      "image_content_sources[0].mirrors[0]: is longer than 253 characters",
    ];
    await newFlavor(page, (r) => json(r, problem(422, "VALIDATION_ERROR", "spec 'agent-mirrors' cannot be saved", { problems }), 422));
    await addEntry(page, mirrors(page), 0, OPERATORS.source, ...OPERATORS.mirrors);
    await reviewAndConfirm(page);

    await expect(page.getByRole("dialog")).toHaveCount(0);
    const group = field(page, "image_content_sources");
    await expect(group).toContainText("the specs project's cluster-template.j2 does not read this input");
    await expect(group).toContainText("Entry 1, mirror 1: is longer than 253 characters");
  });

  test("a preset turned back to the defaults leaves the flavor file", async ({ page }) => {
    const writes = await openEditor(page, "/specs/own-mirrors/edit", (r) => json(r, mockMR({ repo: "specs", iid: 64 })), OWN);
    await expect(keepSwitch(page)).not.toBeChecked();
    await expect(mirrors(page).getByLabel("Image mirrors 2: mirror 2")).toHaveValue(RELEASE.mirrors[1]);

    await keepSwitch(page).click();
    for (const source of [OPERATORS.source, RELEASE.source]) await mirrors(page).getByRole("button", { name: `Remove ${source}` }).click();
    await expect(field(page, "image_content_sources")).toContainText("None: nothing is written");
    await page.getByTestId("spec-version-input").fill("1.1.0");
    await reviewAndConfirm(page, /review & update/i);

    await expect(page.getByText("Update MR !64 opened")).toBeVisible();
    const values = writes[0].spec.day1.values ?? {};
    expect("image_content_sources" in values).toBe(false);
    expect("disable_idms_merge" in values).toBe(false);
  });
});

// ── The flavor's Overview ────────────────────────────────────────────────────

test.describe("Image mirrors on a flavor's Overview", () => {
  test("the mirrors are one row, source → mirrors, beside the switch and a note on what they do", async ({ page }) => {
    const stored: SpecDetail = { ...OWN, spec: { ...OWN.spec, day1: { ...OWN.spec.day1, locked_paths: ["image_content_sources"] } } };
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters", (r) => json(r, []));
    await page.route("**/api/day1/specs/own-mirrors", (r) => json(r, stored));
    await page.route("**/api/day1/specs/own-mirrors/clusters", (r) => json(r, []));
    await go(page, "/specs/own-mirrors");

    const inputs = page.getByTestId("flavor-inputs");
    const list = inputs.getByTestId("flavor-input-image_content_sources");
    await expect(list).toHaveAttribute("data-kind", "locked");
    await expect(list.getByTestId("flavor-mirror-list").getByRole("listitem")).toHaveCount(2);
    await expect(list).toContainText(RELEASE.source);
    await expect(list).toContainText(RELEASE.mirrors[1]);
    // Not split into an item group per entry, as a list of nodepools is
    await expect(inputs.getByText("image content sources 1")).toHaveCount(0);

    const drop = inputs.getByTestId("flavor-input-disable_idms_merge");
    await expect(drop).toHaveAttribute("data-kind", "preset");
    await expect(drop).toContainText("Dropped: only the cluster's own mirrors");
    await expect(inputs.getByTestId("flavor-mirrors-note")).toContainText("drops those: the cluster uses only its own");  });
});

// ── The create form ──────────────────────────────────────────────────────────

const PREVIEW: ClusterPreview = {
  yaml: "mastertag: 4.16.27-x86_64\n",
  path: "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-own-site1-a.yaml",
};

/** The create form's reads, with the two flavors; resolves with each preview request. */
async function openCreate(page: Page, flavorName: string): Promise<{ form: ClusterNewPage; previews: CreateClusterRequest[] }> {
  const previews: CreateClusterRequest[] = [];
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/specs", (r) => json(r, [OWN, FIXED]));
  await page.route("**/api/day1/specs/template/schema", (r) => json(r, SCHEMA));
  await page.route("**/api/day1/machine-configs", (r) => json(r, mockMachineConfigs));
  await page.route("**/api/day1/sites", (r) => json(r, ["site1"]));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/clusters/name-suggestion**", (r) =>
    json(r, { name: "ocp4-prod-own-site1-a", env: "prod", short_name: "own", sequence: "a", problems: [] })
  );
  await page.route("**/api/day1/clusters/preview", (r) => {
    previews.push(r.request().postDataJSON());
    return json(r, PREVIEW);
  });
  const form = new ClusterNewPage(page);
  await form.goto();
  await form.chooseSpec(flavorName);
  await form.place({ site: "site1", env: "prod", version: "4.16.27" });
  await expect(form.nameInput).toHaveValue("ocp4-prod-own-site1-a");
  await form.templateInput("1234").fill("1234");
  await form.templateInput("56").fill("56");
  await form.templateInput("7").fill("7");
  await page.getByPlaceholder("e.g. dell-r660-site1-128c-1024gb-5tb").fill("dell-r660-site1-128c-1024gb-5tb");
  return { form, previews };
}

const createField = (page: Page, path: string) => page.locator(`[data-field-path="${path}"]`);

test.describe("Image mirrors on the create form", () => {
  test("a preset is prefilled and editable, and the switch is sent as a JSON boolean", async ({ page }) => {
    const { form, previews } = await openCreate(page, "own-mirrors");
    const list = createField(page, "image_content_sources");
    await expect(list.locator("[data-flavor-badge=preset]")).toBeVisible();
    const entries = page.getByTestId("create-mirror-entries");
    await expect(entries.getByLabel("Image mirrors 1: source")).toHaveValue(OPERATORS.source);
    await entries.getByLabel("Image mirrors 1: mirror 1").fill("mirror3.example.com/team/operators");

    const keep = createField(page, "disable_idms_merge").getByRole("switch", { name: "Keep the MCE's default mirrors" });
    await expect(keep).not.toBeChecked();
    await keep.click();
    await expect(keep).toBeChecked();

    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    const variables = previews[0].variables;
    expect(variables.image_content_sources).toEqual([{ ...OPERATORS, mirrors: ["mirror3.example.com/team/operators"] }, RELEASE]);
    expect(variables.disable_idms_merge).toBe(false);
  });

  test("dropping the MCE's mirrors after removing every entry is flagged before day1 is asked", async ({ page }) => {
    const { form, previews } = await openCreate(page, "own-mirrors");
    const entries = page.getByTestId("create-mirror-entries");
    for (const source of [OPERATORS.source, RELEASE.source]) await entries.getByRole("button", { name: `Remove ${source}` }).click();
    await expect(page.getByTestId("create-no-mirrors")).toContainText("The cluster would have no image mirrors");
    await form.review();
    await expect(form.reviewDialog).toHaveCount(0);
    expect(previews).toHaveLength(0);
  });

  test("a locked value is shown, never edited, and sent as the flavor has it", async ({ page }) => {
    const { form, previews } = await openCreate(page, "fixed-mirrors");
    const list = createField(page, "image_content_sources");
    await expect(list.locator("[data-flavor-badge=locked]")).toBeVisible();
    await expect(list.getByTestId("create-mirror-list")).toContainText(OPERATORS.mirrors[0]);
    await expect(list.getByRole("textbox")).toHaveCount(0);
    const keep = createField(page, "disable_idms_merge").getByRole("switch", { name: "Keep the MCE's default mirrors" });
    await expect(keep).toBeChecked();
    await expect(keep).toBeDisabled();

    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(previews[0].variables.image_content_sources).toEqual([OPERATORS]);
    expect(previews[0].variables.disable_idms_merge).toBe(false);
  });
});
