/**
 * Creating a cluster from a flavor (docs/notes/2026-11-12-create-from-flavor-api.md,
 * ADR-0040): the name day1 suggests and the person's override, the
 * one-letter sequence, a flavor's nodepool ratio sized by one number, and
 * the InfraEnv field with live status off. Every API is mocked.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
import { ClusterNewPage } from "../pages/cluster-new.page";
import type { ClusterPreview, CreateClusterRequest, Mce, NameSuggestion, SpecEntry, TemplateField } from "../../types";

// ── Mock data ─────────────────────────────────────────────────────────────────

/** `GET /specs/template/schema` on the fixtures' cluster-template.j2. */
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
      {
        name: "configs",
        type: "list",
        required: false,
        default: [],
        fields: [{ name: "name", type: "string", required: true, example: "worker-kubeletconfig-reserved" }],
      },
    ],
  },
];

const STATIC = [{ name: "workers-chrony-configuration" }];

function flavor(name: string, day1: Partial<SpecEntry["spec"]["day1"]>): SpecEntry {
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
  };
}

const RCS = flavor("rcs", {});
/** Three zones that grow together at 1:2:1. */
const ZONES = flavor("zones", {
  structure: { nodepools: [{}, {}, {}] },
  values: { nodepools: [{ configs: STATIC }, { configs: STATIC }, { configs: STATIC }] },
  nodepool_ratio: [1, 2, 1],
});

const MCES: Mce[] = [
  {
    name: "ocp4-prod-mce-site1-a", site: "site1", env: "prod", letter: "a", follows_convention: true, naming_problems: [],
    default_mastertag: "4.16.27-x86_64", hub_version: "4.16.27-x86_64", cluster_count: 4, stray_files: [], problems: [],
  },
];

const PREVIEW: ClusterPreview = {
  yaml: '# specName: "rcs"\n# specVersion: "1.0.0"\nmastertag: 4.16.27-x86_64\n',
  path: "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-rcs-site1-a.yaml",
};

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: status >= 400 ? "application/problem+json" : "application/json",
    body: JSON.stringify(body),
  });

// ── Mock helper ───────────────────────────────────────────────────────────────

interface Calls {
  previews: CreateClusterRequest[];
  suggestions: URLSearchParams[];
}

/** The create form's reads; the name suggestion answers `ocp4-<env>-<flavor>-<site>-a`, or `-b` for rcs. */
async function setup(page: Page): Promise<Calls> {
  const calls: Calls = { previews: [], suggestions: [] };
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/specs", (r) => json(r, [RCS, ZONES]));
  await page.route("**/api/day1/specs/template/schema", (r) => json(r, SCHEMA));
  await page.route("**/api/day1/sites", (r) => json(r, ["site1"]));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
  await page.route("**/api/day1/mces/*/infraenvs", (r) =>
    json(
      r,
      {
        type: "/problems/feature-disabled", title: "Feature Disabled", status: 501, code: "FEATURE_DISABLED",
        detail: "Live cluster status is disabled", instance: "/api/day1/mces/x/infraenvs", request_id: "req_1", details: {},
      },
      501
    )
  );
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/clusters/name-suggestion**", (r) => {
    const params = new URL(r.request().url()).searchParams;
    calls.suggestions.push(params);
    const flavorName = params.get("flavor") ?? "";
    const letter = flavorName === "rcs" ? "b" : "a";
    const suggestion: NameSuggestion = {
      name: `ocp4-prod-${flavorName}-${params.get("site")}-${letter}`,
      env: "prod",
      short_name: flavorName,
      sequence: letter,
      problems: [],
    };
    return json(r, suggestion);
  });
  await page.route("**/api/day1/clusters/preview", (r) => {
    calls.previews.push(r.request().postDataJSON());
    return json(r, PREVIEW);
  });
  return calls;
}

const infraEnvs = (page: Page) => page.getByPlaceholder("e.g. dell-r660-site1-128c-1024gb-5tb");

async function fillOwners(form: ClusterNewPage) {
  await form.templateInput("1234").fill("1234");
  await form.templateInput("56").fill("56");
  await form.templateInput("7").fill("7");
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe("Create from a flavor: the suggested name", () => {
  test("day1's name fills in once Wingman picks the MCE, and an edited name is the person's", async ({ page }) => {
    const calls = await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("rcs");
    await expect(form.nameInput).toHaveValue("");

    await form.place({ site: "site1", env: "prod", version: "4.16.27" });
    await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");
    await expect(form.nameInput).toHaveValue("ocp4-prod-rcs-site1-b");
    // A short mark; how the name was made is its tooltip and the input's description
    await expect(page.getByTestId("name-suggested")).toHaveText("Suggested · type to change", { useInnerText: true });
    await expect(page.getByTestId("name-suggested-why")).toHaveText(
      "Suggested from flavor rcs, site1 and the MCE's env, with the next free letter."
    );
    await expect(form.nameInput).toHaveAccessibleDescription(/^Suggested from flavor rcs, site1/);
    await page.getByTestId("name-suggested").getByRole("button", { name: "Suggested" }).hover();
    await expect(form.tooltip).toContainText("Suggested from flavor rcs");
    await expect(form.namingHint).toContainText("Follows the naming convention");
    const asked = calls.suggestions.at(-1)!;
    expect([asked.get("site"), asked.get("mce"), asked.get("flavor")]).toEqual(["site1", "ocp4-prod-mce-site1-a", "rcs"]);

    // An override: kept, checked, and sent; the suggestion is one click away
    await form.fillName("ocp4-prod-rcs-site1-d");
    await expect(page.getByTestId("name-suggested")).toHaveCount(0);
    await expect(page.getByTestId("use-suggested-name")).toContainText("ocp4-prod-rcs-site1-b");
    await fillOwners(form);
    await infraEnvs(page).fill("dell-r660-site1-128c-1024gb-5tb");
    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(calls.previews[0].name).toBe("ocp4-prod-rcs-site1-d");
    await page.keyboard.press("Escape");

    await page.getByTestId("use-suggested-name").click();
    await expect(form.nameInput).toHaveValue("ocp4-prod-rcs-site1-b");
  });

  test("a number as the sequence is flagged while typing", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("rcs");
    await form.fillName("ocp4-prod-rcs-site1-01");
    await expect(form.namingHint).toContainText('The sequence "01" must be one letter, a to z');
    await form.fillName("ocp4-prod-rcs-site1-c");
    await expect(form.namingHint).toContainText("Follows the naming convention");
  });
});

test.describe("Create from a flavor: the nodepool ratio", () => {
  test("one size sets every sized nodepool's replicas, and they are sent", async ({ page }) => {
    const calls = await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("zones");
    await form.place({ site: "site1", env: "prod", version: "4.16.27" });
    await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");
    await expect(form.nameInput).toHaveValue("ocp4-prod-zones-site1-a");

    const sizing = page.getByTestId("nodepool-size");
    await expect(sizing).toContainText("zones sizes its first 3 nodepools 1:2:1");
    await expect(page.getByTestId("nodepool-size-replicas")).toHaveText("Replicas 1 · 2 · 1 = 4 nodes");

    const size = page.getByTestId("nodepool-size-input");
    await size.fill("2");
    await expect(page.getByTestId("nodepool-size-replicas")).toHaveText("Replicas 2 · 4 · 2 = 8 nodes");
    // Each sized nodepool shows its replicas read-only, with where they come from
    await expect(page.getByTestId("nodepool-1-replicas-sized")).toHaveText("4ratio 2 × size 2");

    await size.fill("");
    await expect(page.getByTestId("nodepool-size-replicas")).toHaveText("Enter a whole number of at least 1");
    await size.fill("3");

    await fillOwners(form);
    for (const [i, zone] of ["zone-a", "zone-b", "zone-c"].entries()) await infraEnvs(page).nth(i).fill(zone);
    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    const pools = calls.previews[0].variables.nodepools as { infra_env: string; replicas: unknown }[];
    expect(pools.map((p) => [p.infra_env, p.replicas])).toEqual([
      ["zone-a", 3],
      ["zone-b", 6],
      ["zone-c", 3],
    ]);
  });

  test("a flavor without a ratio has no size, and its replicas stay editable", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("rcs");
    await expect(page.getByTestId("nodepool-size")).toHaveCount(0);
    await expect(page.locator('[data-field-path="nodepools[0].replicas"]').getByRole("textbox")).toBeEditable();
  });
});

test.describe("Create from a flavor: InfraEnvs", () => {
  test("with live status off each InfraEnv is typed, and the form says why", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("rcs");
    await expect(page.getByTestId("infraenv-off")).toHaveCount(0);
    await form.place({ site: "site1", env: "prod", version: "4.16.27" });
    await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");
    await expect(page.getByTestId("infraenv-off")).toContainText("live status is off");
    await expect(infraEnvs(page)).toBeEditable();
  });
});
