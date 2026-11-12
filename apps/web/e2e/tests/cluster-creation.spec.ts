/**
 * Mocked tests of the cluster create form (/clusters/new) against the
 * rewritten day1 API: read-only sites and MCEs, the naming convention, the
 * site, prod or prep and the version from which Wingman picks the MCE
 * (ADR-0050), the versions the env's MCEs host (ADR-0034), addon overrides
 * keyed `team/name`, and RFC 9457 problems shown inline. Mock shapes follow
 * apps/day1-service's schemas.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { injectAdminAuth, mockDashboardApis, mockPlacement } from "../fixtures/api-handlers";
import { ClusterNewPage } from "../pages/cluster-new.page";
import type {
  ClusterPreview, CreateClusterRequest, MRDetail, Mce, Problem, SpecEntry, TemplateField,
} from "../../types";

// ── Mock data ─────────────────────────────────────────────────────────────────

const SPEC: SpecEntry = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name: "agent-standard", description: "Bare-metal workers on the Agent platform", version: "1.0.0", labels: {} },
  spec: {
    day1: { variables: [], structure: { nodepools: [{}] }, locked_paths: [], template: "# template", values: {} },
    day2: {
      addons: [
        {
          team: "redbull",
          name: "cluster-roles",
          version: "main",
          overrideable: [
            { path: "rbac.enabled", type: "boolean", default: true, description: "Create the RBAC objects" },
            { path: "replicas", type: "integer", default: 1, description: "" },
          ],
        },
      ],
    },
  },
  load_error: null,
  load_problems: [],
};

const BROKEN_SPEC: SpecEntry = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name: "broken-spec", description: "", version: "", labels: {} },
  spec: { day1: { variables: [], structure: {}, locked_paths: [], template: "", values: {} }, day2: { addons: [] } },
  load_error: "the spec is not a valid ClusterSpec",
  load_problems: ["metadata.version: spec version 'one two' must be one word, like 1.2.0"],
};

const SCHEMA: TemplateField[] = [
  { name: "owner_merkaz", type: "string", required: true, example: "1234" },
  {
    name: "nodepools",
    type: "list",
    required: true,
    fields: [
      { name: "infra_env", type: "string", required: true, example: "dell-r660-site1" },
      { name: "replicas", type: "string", required: false, default: 2 },
    ],
  },
];

function mce(name: string, site: string, overrides: Partial<Mce> = {}): Mce {
  return {
    name,
    site,
    env: null,
    letter: null,
    follows_convention: false,
    naming_problems: [],
    default_mastertag: null,
    hub_version: null,
    cluster_count: 0,
    stray_files: [],
    problems: [],
    ...overrides,
  };
}

const MCES: Record<string, Mce[]> = {
  site1: [
    mce("ocp4-prod-mce-site1-a", "site1", {
      env: "prod", letter: "a", follows_convention: true, default_mastertag: "4.16.27-x86_64", cluster_count: 4,
    }),
    mce("ocp4-mce-workflow-test", "site1", {
      naming_problems: ["MCE 'ocp4-mce-workflow-test' does not follow ocp4-<env>-mce-site1-<letter>"],
      default_mastertag: null,
      cluster_count: 1,
    }),
  ],
  site2: [
    mce("ocp4-prep-mce-site2-a", "site2", {
      env: "prep", letter: "a", follows_convention: true, default_mastertag: "4.18.22-x86_64",
      stray_files: [".gitkeep"],
    }),
  ],
};

/** What each MCE hosts: the ladder's rungs in its minors. site1 has no prep MCE, site2 no prod one. */
const OFFERED: Record<string, string[]> = {
  "ocp4-prod-mce-site1-a": ["4.18.56", "4.17.58", "4.16.27"],
  "ocp4-prep-mce-site2-a": ["4.21.40", "4.20.44", "4.18.22"],
};

const PREVIEW: ClusterPreview = {
  yaml: '# specName: "agent-standard"\n# specVersion: "1.0.0"\nowner:\n  merkaz: "1234"\n\nmastertag: 4.16.27-x86_64\n',
  path: "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-herzi-site1.yaml",
};

const MR: MRDetail = {
  iid: 7,
  project_id: 1,
  title: "[Wingman/Day1] Create cluster ocp4-prod-herzi-site1",
  description: "Creating hosted cluster",
  author: { username: "test-admin", name: "test-admin", avatar_url: "" },
  state: "opened",
  created_at: "2026-11-07T10:00:00Z",
  updated_at: "2026-11-07T10:00:00Z",
  merged_at: null,
  web_url: "https://gitlab.example.com/gitops-day1/platform-config/-/merge_requests/7",
  source_branch: "wingman/day1/create-cluster-ocp4-prod-herzi-site1",
  target_branch: "main",
  labels: ["wingman"],
  repo: "day1",
  has_conflicts: false,
  sha: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
};

function problem(status: number, code: Problem["code"], detail: string, details: Problem["details"] = {}): Problem {
  return {
    type: `/problems/${code.toLowerCase().replace(/_/g, "-")}`,
    title: code,
    status,
    detail,
    instance: "/api/day1/clusters/preview",
    code,
    request_id: "req_0000000000000001",
    details,
  };
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: status >= 400 ? "application/problem+json" : "application/json",
    body: JSON.stringify(body),
  });

// ── Mock helper ───────────────────────────────────────────────────────────────

interface Calls {
  mceSites: (string | null)[];
  /** Every placement read, by its query. */
  placements: URLSearchParams[];
  previews: CreateClusterRequest[];
  creates: CreateClusterRequest[];
}

async function setup(
  page: Page,
  { preview, offered = OFFERED }: { preview?: (route: Route) => Promise<void>; offered?: Record<string, string[]> } = {}
): Promise<Calls> {
  const calls: Calls = { mceSites: [], placements: [], previews: [], creates: [] };
  await injectAdminAuth(page);
  await mockDashboardApis(page);

  await page.route("**/api/day1/specs", (r) => json(r, [SPEC, BROKEN_SPEC]));
  await page.route("**/api/day1/specs/template/schema", (r) => json(r, SCHEMA));
  await mockPlacement(page, offered, calls.placements);
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/sites", (r) => json(r, ["site1", "site2"]));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => {
    const site = new URL(r.request().url()).searchParams.get("site");
    calls.mceSites.push(site);
    return json(r, site ? (MCES[site] ?? []) : Object.values(MCES).flat());
  });
  await page.route("**/api/day1/mces/*/infraenvs", (r) =>
    json(r, problem(501, "FEATURE_DISABLED", "Live cluster status is disabled in this deployment."), 501)
  );
  await page.route("**/api/day1/clusters", (r) => {
    if (r.request().method() !== "POST") return json(r, []);
    calls.creates.push(r.request().postDataJSON());
    return json(r, MR, 201);
  });
  await page.route("**/api/day1/clusters/preview", (r) => {
    calls.previews.push(r.request().postDataJSON());
    return preview ? preview(r) : json(r, PREVIEW);
  });
  await page.route("**/api/day1/approvals/7**", (r) => json(r, { mr: MR, diffs: [] }));
  return calls;
}

/** Choose the spec, then fill everything the form requires for ocp4-prod-herzi-site1 (its name gives site and env). */
async function fillValidForm(form: ClusterNewPage) {
  await form.chooseSpec("agent-standard");
  await form.fillName("ocp4-prod-herzi-site1");
  await form.selectVersion("4.16.27");
  await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");
  await form.templateInput("1234").fill("1234");
  await form.templateInput("dell-r660-site1").fill("dell-r660-site1");
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe("Cluster create form", () => {
  test("a spec that does not parse is listed with its error and cannot be chosen", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();

    const broken = form.specCard("broken-spec");
    await expect(broken).toContainText("does not parse");
    await expect(broken).toContainText("must be one word");
    await expect(broken.getByRole("button")).toHaveCount(0);
    await expect(form.specCard("agent-standard")).toBeVisible();
  });

  test("Wingman picks the MCE from the site, prod or prep and the version; off-convention MCEs are noted", async ({ page }) => {
    const calls = await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");
    await expect(page.getByText(/step 2 of 2/i)).toBeVisible();

    await form.place({ site: "site1", env: "prod", version: "4.16.27" });
    await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");
    await expect(form.candidateRadio("ocp4-prod-mce-site1-a")).toBeChecked();
    expect(calls.mceSites).toContain("site1");
    const asked = calls.placements.at(-1)!;
    expect([asked.get("site"), asked.get("env"), asked.get("version")]).toEqual(["site1", "prod", "4.16.27"]);

    // An MCE off the convention is never a candidate, and the form says so
    await expect(form.offConventionMces).toContainText("ocp4-mce-workflow-test");
    await expect(form.candidate("ocp4-mce-workflow-test")).toHaveCount(0);
    await expect(form.mceSelect).toHaveCount(0);
  });

  test("the version picker waits for the site and prod or prep, and only then asks Wingman", async ({ page }) => {
    const calls = await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");

    await expect(form.versionSelect).toBeDisabled();
    await expect(form.versionSelect).toContainText("Choose a site first");
    await expect(page.getByTestId("placement-waiting")).toContainText(
      "once the site, prod or prep and the OpenShift version are chosen"
    );
    await form.selectSite("site1");
    await expect(form.versionSelect).toBeDisabled();
    await expect(form.versionSelect).toContainText("Choose prod or prep first");
    expect(calls.placements).toEqual([]);

    await form.selectEnv("prod");
    await expect(form.versionSelect).toBeEnabled();
    // No version yet; an empty `need` says the nodepools name no node type (rather than the flavor's)
    expect(calls.placements.map((q) => q.toString())).toEqual(["site=site1&env=prod&flavor=agent-standard&need="]);
    await expect(page.getByTestId("placement-waiting")).toContainText("once the OpenShift version is chosen");
  });

  test("the versions are what the env's MCEs host, and a choice they can't host is dropped", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");
    await form.selectSite("site1");
    await form.selectEnv("prod");

    await form.versionSelect.click();
    await expect(page.getByRole("option")).toHaveText(["4.18.56", "4.17.58", "4.16.27"]);
    await page.getByRole("option", { name: "4.17.58" }).click();
    await expect(form.versionSelect).toContainText("4.17.58");
    await expect(form.versionSource).toContainText("The releases the prod MCEs on site1 can host");

    // site2's prep MCE hosts newer releases, but not 4.17.58: the field empties, nothing is picked
    await form.selectSite("site2");
    await form.selectEnv("prep");
    await expect(form.versionSelect).toContainText("Select OpenShift version…");
    await expect(form.placementPick).toHaveCount(0);
    await form.versionSelect.click();
    await expect(page.getByRole("option")).toHaveText(["4.21.40", "4.20.44", "4.18.22"]);
    await page.keyboard.press("Escape");
  });

  test("an env whose MCEs host no version offers none, and Review asks for one", async ({ page }) => {
    await setup(page, { offered: { "ocp4-prod-mce-site1-a": [] } });
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");
    await form.selectSite("site1");
    await form.selectEnv("prod");

    await expect(form.versionSelect).toBeDisabled();
    await expect(form.versionSelect).toContainText("No prod MCE on site1 hosts a version");
    // Not free text: nothing to send
    await expect(page.getByTestId("ocp-version-input")).toHaveCount(0);
    await form.fillName("ocp4-prod-herzi-site1");
    await form.review();
    await expect(form.formProblems).toContainText("Choose an OpenShift version");
  });

  test("a spec's preset version prefills only when some MCE of the env hosts it", async ({ page }) => {
    await setup(page);
    const preset = (version: string): SpecEntry => ({
      ...SPEC,
      spec: { ...SPEC.spec, day1: { ...SPEC.spec.day1, values: { openshift_release_version: version } } },
    });
    let spec = preset("4.17.58-x86_64");
    await page.route("**/api/day1/specs", (r) => json(r, [spec]));
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");
    await form.selectSite("site1");
    await form.selectEnv("prod");
    await expect(form.versionSelect).toContainText("4.17.58");
    await expect(form.versionSource).toContainText("preset by spec agent-standard");
    await expect(form.versionPresetNote).toHaveCount(0);
    // A version is all the pick needs
    await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");

    // A preset no MCE of the env can host leaves the field empty and says why
    spec = preset("4.21.40-x86_64");
    await form.goto();
    await form.chooseSpec("agent-standard");
    await form.selectSite("site1");
    await form.selectEnv("prod");
    await expect(form.versionSelect).toContainText("Select OpenShift version…");
    await expect(form.versionPresetNote).toContainText(
      "Spec agent-standard presets 4.21.40-x86_64, which no prod MCE on site1 hosts"
    );
  });

  test("the picked MCE's stray files are shown as a warning", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");
    await form.place({ site: "site2", env: "prep", version: "4.18.22" });

    await expect(form.placementPickName).toHaveText("ocp4-prep-mce-site2-a");
    await expect(page.getByTestId("mce-warnings")).toContainText(".gitkeep");
  });

  test("there is no way to create a site or an MCE", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");

    await form.siteSelect.click();
    await expect(form.option("site1")).toBeVisible();
    await expect(page.getByRole("option", { name: /create/i })).toHaveCount(0);
    await form.option("site1").click();

    // The MCE is Wingman's pick among the MCE folders that exist
    await form.selectEnv("prod");
    await form.selectVersion("4.16.27");
    await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");
    await expect(form.mceSelect).toHaveCount(0);
    await expect(page.getByRole("button", { name: /new mce|create mce/i })).toHaveCount(0);
  });

  test("a conventional name gives its site and env; an off-convention one is flagged", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");

    await form.fillName("ocp4-prod-herzi-site1");
    await expect(form.siteSelect).toContainText("site1");
    await expect(form.envSelect.getByRole("radio", { name: "Prod" })).toBeChecked();
    await form.selectVersion("4.16.27");
    await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");
    await expect(form.namingHint).toContainText("Follows the naming convention");

    // site1 has no conventional prep MCE: nothing to pick, and the hint says why
    await form.fillName("ocp4-prep-herzi-site1");
    await expect(form.envSelect.getByRole("radio", { name: "Prep" })).toBeChecked();
    await expect(form.namingHint).toContainText('No "prep" MCE on site1 follows the convention');

    // Prod chosen by hand: Wingman picks the prod MCE, which the name's env does not match
    await form.selectEnv("prod");
    await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");
    await expect(form.namingHint).toContainText('Env "prep" does not match ocp4-prod-mce-site1-a');

    // With site1 chosen, a name for another site does not follow site1's convention
    await form.selectSite("site1");
    await form.fillName("ocp4-prod-herzi-site2");
    await expect(form.namingHint).toContainText("Does not follow ocp4-<env>-<name>-site1");

    await form.fillName("My_Cluster");
    await expect(form.namingHint).toContainText("lowercase letters, digits and '-'");
  });

  test("the form's own check lists every empty required field and calls nothing", async ({ page }) => {
    const calls = await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");

    await form.review();
    await expect(form.formProblems).toContainText("Choose a site");
    await expect(form.formProblems).toContainText("Choose the environment: prod or prep");
    await expect(form.formProblems).toContainText("Choose an OpenShift version");
    await expect(form.formProblems).not.toContainText("Choose an MCE");
    await expect(form.formProblems).toContainText("Enter a cluster name");
    await expect(form.formProblems).toContainText("Owner Merkaz is required");
    await expect(form.formProblems).toContainText("Nodepool 1 › Infra Env is required");
    expect(calls.previews).toHaveLength(0);
  });

  test("review shows the server's file and confirm sends exactly the reviewed request", async ({ page }) => {
    const calls = await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await fillValidForm(form);
    await form.overrideField("redbull", "cluster-roles", "replicas").fill("3");

    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    await expect(form.reviewDialog).toContainText(PREVIEW.path);
    await expect(form.reviewDialog).toContainText("replicas: 3");

    await form.confirm();
    await page.waitForURL("**/approvals/day1-7");

    expect(calls.creates).toHaveLength(1);
    const body = calls.creates[0];
    expect(body).toEqual(calls.previews[0]);
    expect(body).toMatchObject({
      name: "ocp4-prod-herzi-site1",
      site: "site1",
      mce: "ocp4-prod-mce-site1-a",
      spec_name: "agent-standard",
      spec_version: "1.0.0",
      // The MCE is Wingman's pick, sent back so day1 can tell a pick that changed
      placement: { pick: "ocp4-prod-mce-site1-a", reason: null },
    });
    expect(body.variables).toMatchObject({
      openshift_release_version: "4.16.27",
      owner_merkaz: "1234",
      nodepools: [{ infra_env: "dell-r660-site1", replicas: 2 }],
    });
    for (const removed of ["site_name", "mce_name", "cluster_name", "site", "mce"]) {
      expect(body.variables).not.toHaveProperty(removed);
    }
    expect(body.addon_overrides).toEqual({ "redbull/cluster-roles": { rbac: { enabled: true }, replicas: 3 } });
  });

  test("a 422 lists every problem inline instead of opening the review", async ({ page }) => {
    await setup(page, {
      preview: (r) =>
        json(
          r,
          problem(422, "VALIDATION_ERROR", "the rendered cluster file breaks the values-file contract", {
            problems: ["nodepool[0]: infraEnvName is missing", "mastertag '4.16' is not a release like 4.16.27"],
          }),
          422
        ),
    });
    const form = new ClusterNewPage(page);
    await form.goto();
    await fillValidForm(form);

    await form.review();
    await expect(form.formProblems).toContainText("nodepool[0]: infraEnvName is missing");
    await expect(form.formProblems).toContainText("mastertag '4.16' is not a release like 4.16.27");
    await expect(form.formProblems).toContainText("request req_0000000000000001");
    await expect(form.reviewDialog).not.toBeVisible();
  });

  test("a problem that names its item is listed by item, not as an object", async ({ page }) => {
    await setup(page, {
      preview: (r) =>
        json(
          r,
          problem(422, "VALIDATION_ERROR", "2 of the requested charts cannot be installed", {
            problems: [
              { team: "redbull", chart: "cluster-roles", detail: "version 9.9.9 is not released", rule: "version" },
              { team: "redbull", detail: "the team repo has no cluster folder" },
            ],
          }),
          422
        ),
    });
    const form = new ClusterNewPage(page);
    await form.goto();
    await fillValidForm(form);

    await form.review();
    await expect(form.formProblems).toContainText("redbull/cluster-roles: version 9.9.9 is not released");
    await expect(form.formProblems).toContainText("redbull: the team repo has no cluster folder");
    await expect(form.formProblems).not.toContainText("[object Object]");
  });

  test("FastAPI's field errors are listed by field", async ({ page }) => {
    await setup(page, {
      preview: (r) =>
        json(
          r,
          problem(422, "VALIDATION_ERROR", "The request is not valid.", {
            errors: [{ loc: ["body", "variables", "owner_merkaz"], msg: "Input should be a valid string", type: "string_type" }],
          }),
          422
        ),
    });
    const form = new ClusterNewPage(page);
    await form.goto();
    await fillValidForm(form);

    await form.review();
    await expect(form.formProblems).toContainText("variables.owner_merkaz: Input should be a valid string");
  });

  test("a 409 ALREADY_EXISTS says the name is taken", async ({ page }) => {
    await setup(page, {
      preview: (r) =>
        json(r, problem(409, "ALREADY_EXISTS", "cluster 'ocp4-prod-herzi-site1' already exists under site1/ocp4-prod-mce-site1-a"), 409),
    });
    const form = new ClusterNewPage(page);
    await form.goto();
    await fillValidForm(form);

    await form.review();
    await expect(form.formProblems).toContainText("This cluster name is taken");
    await expect(form.formProblems).toContainText("already exists under site1/ocp4-prod-mce-site1-a");
    await expect(form.formProblems).toContainText("an open MR already creates it");
  });

  test("a 409 REVISION_CONFLICT for a stale spec offers to reload the specs", async ({ page }) => {
    await setup(page, {
      preview: (r) =>
        json(r, problem(409, "REVISION_CONFLICT", "spec agent-standard is now v1.1.0, not v1.0.0; reload the form"), 409),
    });
    const form = new ClusterNewPage(page);
    await form.goto();
    await fillValidForm(form);

    await form.review();
    await expect(form.formProblems).toContainText("The flavor changed since you opened it");
    await form.formProblems.getByRole("button", { name: /reload flavors/i }).click();
    await expect(page.getByText(/step 1 of 2/i)).toBeVisible();
  });
});

test.describe("Searchable pickers", () => {
  test("the site, the env and the version are chosen by keyboard alone", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");

    await form.siteSelect.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByPlaceholder("Search sites…")).toBeFocused();
    await page.keyboard.type("2");
    await expect(page.getByRole("option")).toHaveText(["site2"]);
    // Typing highlights the first match; Enter chooses the highlighted option
    await expect(page.getByRole("option", { name: "site2" })).toHaveAttribute("data-highlighted", "");
    await page.keyboard.press("Enter");
    await expect(form.siteSelect).toContainText("site2");

    // prod or prep is a radio group: Space chooses the focused one, arrows move the choice
    await form.envSelect.getByRole("radio", { name: "Prod" }).focus();
    await page.keyboard.press("Space");
    await expect(form.envSelect.getByRole("radio", { name: "Prod" })).toBeChecked();
    await page.keyboard.press("ArrowRight");
    await expect(form.envSelect.getByRole("radio", { name: "Prep" })).toBeChecked();

    // ArrowDown opens the version picker too, and its search filters the versions
    await expect(form.versionSelect).toBeEnabled();
    await form.versionSelect.focus();
    await page.keyboard.press("ArrowDown");
    await expect(page.getByPlaceholder("Search versions…")).toBeFocused();
    await page.keyboard.type("4.18");
    await expect(page.getByPlaceholder("Search versions…")).toHaveValue("4.18");
    await expect(page.getByRole("option")).toHaveText(["4.18.22"]);
    await expect(page.getByRole("option")).toHaveAttribute("data-highlighted", "");
    await page.keyboard.press("Enter");
    await expect(form.versionSelect).toContainText("4.18.22");
    await expect(form.placementPickName).toHaveText("ocp4-prep-mce-site2-a");
  });

  test("a version search that matches nothing says so", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");
    await form.selectSite("site1");
    await form.selectEnv("prod");

    await form.versionSelect.click();
    await page.getByPlaceholder("Search versions…").fill("9.99");
    await expect(page.getByRole("option")).toHaveCount(0);
    await expect(page.getByText("No version matches.")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(form.versionSelect).toContainText("Select OpenShift version…");
  });

  test("infra envs the MCE hub lists are picked from a searchable list, and sent", async ({ page }) => {
    const calls = await setup(page);
    await page.route("**/api/day1/mces/*/infraenvs", (r) => json(r, ["dell-r660-site1", "dell-r750-site1", "hpe-dl380-site1"]));
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("agent-standard");
    await form.fillName("ocp4-prod-herzi-site1");
    await form.selectVersion("4.16.27");
    await expect(form.placementPickName).toHaveText("ocp4-prod-mce-site1-a");

    const infraEnv = page.getByRole("combobox", { name: "Infra Env", exact: true });
    await infraEnv.click();
    await page.getByPlaceholder("Search infra envs…").fill("r750");
    await expect(page.getByRole("option")).toHaveText(["dell-r750-site1"]);
    await page.getByRole("option", { name: "dell-r750-site1" }).click();
    await expect(infraEnv).toContainText("dell-r750-site1");

    await form.templateInput("1234").fill("1234");
    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(calls.previews[0].variables.nodepools).toEqual([{ infra_env: "dell-r750-site1", replicas: 2 }]);
  });
});
