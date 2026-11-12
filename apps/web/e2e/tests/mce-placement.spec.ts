/**
 * MCE placement on the create form (docs/notes/2026-11-12-mce-placement-api.md,
 * ADR-0050): the person chooses site, prod or prep, version and owner; Wingman
 * picks the MCE and says why; an admin may choose another MCE that passes every
 * check, with a reason; a failing MCE says why and cannot be chosen; a pick
 * that changed under the form is a 409; and without placement (501) the form
 * keeps its MCE select. Every API is mocked.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, injectAdminAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import { ClusterNewPage } from "../pages/cluster-new.page";
import type {
  ClusterPreview, CreateClusterRequest, Mce, NameSuggestion, Placement, PlacementCandidate, SpecEntry, TemplateField,
} from "../../types";

// ── Mock data ─────────────────────────────────────────────────────────────────

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
    ],
  },
];

const RCS: SpecEntry = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name: "rcs", description: "The rcs flavor", version: "1.0.0", labels: {} },
  spec: {
    day1: { variables: [], structure: { nodepools: [{}] }, locked_paths: [], template: "# template", values: {} },
    day2: { addons: [] },
  },
  load_error: null,
  load_problems: [],
  warnings: [],
};

const A = "ocp4-prod-mce-site1-a";
const B = "ocp4-prod-mce-site1-b";
const C = "ocp4-prod-mce-site1-c";
const VERSIONS = ["4.18.22", "4.17.30", "4.16.27"];

function mce(name: string, env: "prod" | "prep"): Mce {
  return {
    name, site: "site1", env, letter: name.slice(-1), follows_convention: true, naming_problems: [],
    default_mastertag: "4.16.27-x86_64", hub_version: "4.16.27-x86_64", cluster_count: 2, stray_files: [], problems: [],
  };
}
const MCES: Mce[] = [mce(A, "prod"), mce(B, "prod"), mce(C, "prod"), mce("ocp4-prep-mce-site1-a", "prep")];

const PASS = (detail: string) => ({ status: "pass" as const, detail });
function candidate(name: string, overrides: Partial<PlacementCandidate>): PlacementCandidate {
  return {
    mce: name,
    eligible: true,
    picked: false,
    rank: null,
    behind_on: null,
    checks: [
      { check: "version", ...PASS("Hosts OpenShift 4.18.22.") },
      { check: "free_pods", ...PASS("212 free pods; a new cluster needs 70.") },
      { check: "readable", ...PASS("Wingman read its nodes and pods.") },
    ],
    versions: VERSIONS,
    clusters: 2,
    open_creates: 0,
    owner_clusters: 0,
    spare: { total: 3, usable: 2 },
    spare_detail: null,
    pods: { free: 212, allocatable: 500, used: 288, nodes_counted: 2, nodes_excluded: { control_plane: 3, not_ready: 0, unschedulable: 1 } },
    ...overrides,
  };
}

/** The contract's example: b picked over a on this owner's clusters; c fails two checks. */
function placement(query: URLSearchParams, overrides: Partial<Placement> = {}): Placement {
  const version = query.get("version");
  const owner = query.get("owner");
  const base = {
    site: query.get("site") ?? "site1",
    env: query.get("env") ?? "prod",
    version,
    owner,
    flavor: query.get("flavor"),
    min_free_pods: 70,
    versions: VERSIONS,
    server_scan_error: null,
  };
  if (!version) {
    // Without a version: the versions, the numbers, no pick
    return { ...base, pick: null, why: null, problems: ["Choose an OpenShift version."], candidates: [], ...overrides };
  }
  return {
    ...base,
    pick: B,
    why: `${B} has the fewest clusters of owner ${owner ?? "?"}: 0, against 2 on ${A}.`,
    problems: [],
    candidates: [
      candidate(B, { picked: true, rank: 1, open_creates: 1, owner_clusters: owner ? 0 : null }),
      candidate(A, {
        rank: 2, behind_on: "owner_clusters", clusters: 6, owner_clusters: owner ? 2 : null, spare: { total: 3, usable: 1 },
        pods: { free: 140, allocatable: 750, used: 610, nodes_counted: 3, nodes_excluded: { control_plane: 3, not_ready: 0, unschedulable: 0 } },
      }),
      candidate(C, {
        eligible: false,
        clusters: 1,
        checks: [
          { check: "version", status: "fail", detail: "Hosts 4.16 to 4.17 only (4.17.30, 4.16.27), not 4.18.22." },
          { check: "free_pods", status: "fail", detail: "40 free pods; a new cluster needs 70." },
          { check: "readable", ...PASS("Wingman read its nodes and pods.") },
        ],
        versions: ["4.17.30", "4.16.27"],
        spare: null,
        spare_detail: `server-scan names no server for ${C}, so its spare servers are unknown.`,
        pods: { free: 40, allocatable: 250, used: 210, nodes_counted: 1, nodes_excluded: { control_plane: 3, not_ready: 1, unschedulable: 0 } },
      }),
    ],
    ...overrides,
  };
}

const PREVIEW: ClusterPreview = {
  yaml: '# specName: "rcs"\n# specVersion: "1.0.0"\nmastertag: 4.18.22\n',
  path: `sites/site1/mces/${B}/hostedClusters/ocp4-prod-rcs-site1-a.yaml`,
};

// ── Mock helper ───────────────────────────────────────────────────────────────

interface Calls {
  placements: URLSearchParams[];
  previews: CreateClusterRequest[];
  suggestions: URLSearchParams[];
  infraEnvMces: string[];
}

/**
 * The create form's reads with placement on. `answer` replaces the placement
 * for a version (the versions read keeps the default), `preview` the preview.
 */
async function setup(
  page: Page,
  options: { answer?: (query: URLSearchParams) => Placement; preview?: (route: Route) => Promise<void> | void } = {}
): Promise<Calls> {
  const calls: Calls = { placements: [], previews: [], suggestions: [], infraEnvMces: [] };
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/specs", (r) => json(r, [RCS]));
  await page.route("**/api/day1/specs/template/schema", (r) => json(r, SCHEMA));
  await page.route("**/api/day1/sites", (r) => json(r, ["site1"]));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
  await page.route("**/api/day1/mces/*/infraenvs", (r) => {
    calls.infraEnvMces.push(decodeURIComponent(new URL(r.request().url()).pathname.split("/")[4]));
    return fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled");
  });
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/placement**", (r) => {
    const query = new URL(r.request().url()).searchParams;
    calls.placements.push(query);
    return json(r, query.get("version") && options.answer ? options.answer(query) : placement(query));
  });
  await page.route("**/api/day1/clusters/name-suggestion**", (r) => {
    const params = new URL(r.request().url()).searchParams;
    calls.suggestions.push(params);
    const letter = params.get("mce") === A ? "c" : "a";
    const suggestion: NameSuggestion = {
      name: `ocp4-prod-rcs-site1-${letter}`, env: "prod", short_name: "rcs", sequence: letter, problems: [],
    };
    return json(r, suggestion);
  });
  await page.route("**/api/day1/clusters/preview", (r) => {
    calls.previews.push(r.request().postDataJSON());
    return options.preview ? options.preview(r) : json(r, PREVIEW);
  });
  return calls;
}

/** Spec rcs, site1, prod, 4.18.22; then the owner numbers (mador 7) and the nodepool. */
async function fillForm(form: ClusterNewPage) {
  await form.goto();
  await form.chooseSpec("rcs");
  await form.selectSite("site1");
  await form.selectEnv("prod");
  await form.selectVersion("4.18.22");
  await form.templateInput("1234").fill("1234");
  await form.templateInput("56").fill("56");
  await form.templateInput("7").fill("7");
  await form.page.getByPlaceholder("e.g. dell-r660-site1-128c-1024gb-5tb").fill("dell-r660-site1-128c-1024gb-5tb");
}

const lastPlacement = (calls: Calls) => calls.placements.at(-1)!;

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe("MCE placement: Wingman's pick", () => {
  test("the pick and why come first, every candidate's numbers below, and the form follows the pick", async ({ page }) => {
    const calls = await setup(page);
    const form = new ClusterNewPage(page);
    await fillForm(form);

    // The owner is sent once typed (debounced), with the site, env, version and flavor
    await expect.poll(() => lastPlacement(calls).get("owner")).toBe("7");
    expect(Object.fromEntries(lastPlacement(calls))).toEqual({
      site: "site1", env: "prod", version: "4.18.22", owner: "7", flavor: "rcs",
    });
    await expect(page.getByTestId("placement-owner")).toContainText("Ranked for owner 7");

    await expect(form.placementPick).toContainText("Wingman's pick");
    await expect(page.getByTestId("placement-pick-name")).toHaveText(B);
    await expect(page.getByTestId("placement-why")).toHaveText(`${B} has the fewest clusters of owner 7: 0, against 2 on ${A}.`);
    await expect(form.candidateRadio(B)).toBeChecked();

    const runnerUp = form.candidate(A);
    await expect(runnerUp).toContainText("Passes every check");
    await expect(runnerUp).toContainText("behind the pick: more clusters of this owner");
    await expect(runnerUp.getByTestId("placement-cell-owner")).toContainText("2");
    await expect(runnerUp.getByTestId("placement-cell-clusters")).toContainText("6");
    await expect(runnerUp.getByTestId("placement-cell-spare")).toContainText(/1\s*of 3/);
    await expect(runnerUp.getByTestId("placement-cell-pods")).toContainText("140");
    await expect(form.candidate(B).getByTestId("placement-cell-clusters")).toContainText("1 in an open MR");

    // The name, the InfraEnvs and the request follow the pick
    await expect(form.nameInput).toHaveValue("ocp4-prod-rcs-site1-a");
    expect(calls.suggestions.at(-1)!.get("mce")).toBe(B);
    expect(calls.infraEnvMces).toContain(B);
    await expect(form.namingHint).toContainText("Follows the naming convention");
    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(calls.previews[0].mce).toBe(B);
    expect(calls.previews[0].placement).toEqual({ pick: B, reason: null });
    await expect(form.reviewDialog).toContainText("Wingman's pick");
  });

  test("the versions are what the candidates host; until a version is chosen nothing is picked", async ({ page }) => {
    const calls = await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("rcs");

    await expect(form.mceSelect).toBeVisible();
    await form.selectSite("site1");
    // Placement answered: prod or prep instead of an MCE select
    await expect(form.envSelect).toBeVisible();
    await expect(form.mceSelect).toHaveCount(0);
    await expect(form.versionSelect).toContainText("Choose prod or prep first");
    await expect(page.getByTestId("placement-waiting")).toContainText("once the environment and the OpenShift version are chosen");

    await form.selectEnv("prod");
    await form.versionSelect.click();
    await expect(page.getByRole("option")).toHaveText(VERSIONS);
    await page.keyboard.press("Escape");
    expect(calls.placements.every((q) => !q.get("version"))).toBe(true);
    await expect(page.getByTestId("placement-waiting")).toContainText("once the OpenShift version is chosen");
    await expect(page.getByTestId("placement-owner")).toContainText("Enter the owner's mador");
  });

  test("a failing MCE says why in plain words and cannot be chosen", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await fillForm(form);

    const failing = form.candidate(C);
    await expect(failing).toHaveAttribute("data-eligible", "false");
    await expect(failing.getByTestId("placement-check-version")).toHaveText("Hosts 4.16 to 4.17 only (4.17.30, 4.16.27), not 4.18.22.");
    await expect(failing.getByTestId("placement-check-free_pods")).toHaveText("40 free pods; a new cluster needs 70.");
    await expect(failing.getByTestId("placement-check-readable")).toHaveCount(0);
    await expect(failing.getByTestId("placement-cell-spare")).toContainText("unknown");
    await expect(failing).toContainText(`server-scan names no server for ${C}`);
    await expect(form.candidateRadio(C)).toBeDisabled();
    await failing.click({ force: true });
    await expect(form.candidateRadio(B)).toBeChecked();
    await expect(form.placementReason).toHaveCount(0);
  });

  test("no MCE that passes: the panel says why and Review is refused", async ({ page }) => {
    const calls = await setup(page, {
      answer: (query) => {
        const all = placement(query);
        return {
          ...all,
          pick: null,
          why: null,
          problems: ["No prod MCE at site1 passes every check."],
          candidates: all.candidates.map((c) => ({ ...c, eligible: false, picked: false, rank: null, behind_on: null })),
        };
      },
    });
    const form = new ClusterNewPage(page);
    await fillForm(form);

    await expect(page.getByTestId("placement-none")).toContainText("No prod MCE on site1 can take this cluster");
    await expect(page.getByTestId("placement-none")).toContainText("No prod MCE at site1 passes every check.");
    await form.review();
    await expect(form.formProblems).toContainText("No prod MCE on site1 can take this cluster: see MCE");
    expect(calls.previews).toEqual([]);
  });
});

test.describe("MCE placement: an admin's other choice", () => {
  test("another MCE that passes needs a reason, and the reason is sent", async ({ page }) => {
    const calls = await setup(page);
    const form = new ClusterNewPage(page);
    await fillForm(form);
    await expect(form.candidateRadio(B)).toBeChecked();
    await expect(form.placementReason).toHaveCount(0);

    await form.candidateRadio(A).check();
    await expect(form.placementReason).toBeVisible();
    await expect(page.getByTestId("placement-override")).toContainText(`Why ${A} instead of Wingman's pick?`);
    // The name and InfraEnvs follow the choice
    await expect(form.nameInput).toHaveValue("ocp4-prod-rcs-site1-c");
    expect(calls.infraEnvMces).toContain(A);

    // Without a reason the form refuses, and says where
    await form.review();
    await expect(form.formProblems).toContainText(`Say why ${A} instead of Wingman's pick ${B}, under MCE`);
    await expect(form.placementReason).toHaveAttribute("aria-invalid", "true");
    expect(calls.previews).toEqual([]);

    await form.placementReason.fill("Next to owner 7's storage\non site1-a");
    await expect(form.placementReason).toHaveAttribute("aria-invalid", "false");
    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(calls.previews[0].mce).toBe(A);
    expect(calls.previews[0].placement).toEqual({ pick: B, reason: "Next to owner 7's storage on site1-a" });
    await expect(form.reviewDialog).toContainText(`You, over Wingman's pick ${B}: Next to owner 7's storage on site1-a`);
    await page.keyboard.press("Escape");

    // Back to the pick: no reason is needed or sent
    await page.getByTestId("placement-use-pick").click();
    await expect(form.candidateRadio(B)).toBeChecked();
    await expect(form.placementReason).toHaveCount(0);
    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(calls.previews.at(-1)!.placement).toEqual({ pick: B, reason: null });
  });

  test("the candidates are a keyboard radio group; a failing one is skipped", async ({ page }) => {
    await setup(page);
    const form = new ClusterNewPage(page);
    await fillForm(form);

    await expect(page.getByRole("radiogroup", { name: "MCE for the new cluster" })).toBeVisible();
    await form.candidateRadio(B).focus();
    await page.keyboard.press("ArrowDown");
    await expect(form.candidateRadio(A)).toBeChecked();
    await expect(form.placementReason).toBeVisible();
    await page.keyboard.press("ArrowDown");
    // C fails its checks, so the choice wraps back to the pick
    await expect(form.candidateRadio(B)).toBeChecked();
    await expect(form.placementReason).toHaveCount(0);
  });

  test("at phone width every candidate's numbers fit, without a horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setup(page);
    const form = new ClusterNewPage(page);
    await fillForm(form);
    await form.candidateRadio(A).check();
    await expect(form.placementReason).toBeVisible();

    // On a phone each number is labelled above it, under the MCE's name
    await expect(form.candidate(A).getByTestId("placement-cell-pods")).toContainText("Free pods");
    const pods = await form.candidate(A).getByTestId("placement-cell-pods").boundingBox();
    expect(pods!.x + pods!.width).toBeLessThanOrEqual(390);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

test.describe("MCE placement: what day1 says on review", () => {
  test("a pick that changed since the form showed it is a 409: the form says so and reads the numbers again", async ({ page }) => {
    let changed = false;
    const calls = await setup(page, {
      answer: (query) => {
        const now = placement(query);
        if (!changed) return now;
        // A merge put a cluster of owner 7 on b: Wingman now picks a
        return {
          ...now,
          pick: A,
          why: `${A} has the fewest clusters overall: 6, against 7 on ${B}.`,
          candidates: [
            { ...now.candidates[1], picked: true, rank: 1, behind_on: null },
            { ...now.candidates[0], picked: false, rank: 2, behind_on: "clusters" },
            now.candidates[2],
          ],
        };
      },
      preview: (r) => {
        changed = true;
        return fulfillProblem(r, 409, "REVISION_CONFLICT", `Wingman's pick changed from ${B} to ${A} since the form showed it`, {
          pick: A,
        });
      },
    });
    const form = new ClusterNewPage(page);
    await fillForm(form);
    await expect(page.getByTestId("placement-pick-name")).toHaveText(B);
    const before = calls.placements.length;

    await form.review();
    await expect(form.formProblems).toContainText("Wingman's pick changed");
    await expect(form.formProblems).toContainText(`Wingman now picks ${A}`);
    await expect(form.formProblems).not.toContainText("The flavor changed");
    await expect(page.getByTestId("placement-pick-name")).toHaveText(A);
    expect(calls.placements.length).toBeGreaterThan(before);
    await expect(form.candidateRadio(A)).toBeChecked();
    await expect(form.placementReason).toHaveCount(0);
  });

  test("a flavor that changed is still the flavor's 409", async ({ page }) => {
    await setup(page, {
      preview: (r) => fulfillProblem(r, 409, "REVISION_CONFLICT", "spec rcs is now v1.1.0, not v1.0.0; reload the form"),
    });
    const form = new ClusterNewPage(page);
    await fillForm(form);
    await expect(page.getByTestId("placement-pick-name")).toHaveText(B);
    await form.review();
    await expect(form.formProblems).toContainText("The flavor changed since you opened it");
  });
});

test.describe("MCE placement: off", () => {
  test("without placement (501) the form keeps its MCE select", async ({ page }) => {
    await setup(page);
    await page.route("**/api/day1/placement**", (r) =>
      fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled in this deployment (CLUSTER_STATUS_ENABLED=false).")
    );
    await page.route("**/api/day1/mces/*/openshift-versions", (r) => json(r, { mce: A, versions: VERSIONS, problems: [] }));
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("rcs");
    await form.selectSite("site1");
    await form.selectMce(A);

    await expect(form.mceSelect).toContainText(A);
    await expect(form.envSelect).toHaveCount(0);
    await expect(form.placement).toHaveCount(0);
    await expect(form.versionSelect).toContainText("4.16.27");
    await expect(form.versionSource).toContainText(`default of ${A}`);
  });
});
