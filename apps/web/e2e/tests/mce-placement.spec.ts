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
  ClusterPreview, CreateClusterRequest, Mce, NameSuggestion, Placement, PlacementCandidate, PlacementCheck, PlacementNeed,
  PlacementNodeType, SpecEntry, TemplateField,
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
const DELL = "dell-r660-site1-128c-1024gb-5tb";
const HP = "hp-gen11-site1-64c-512gb";

/** Each MCE's free Agents and, of them, the healthy servers, per node type (a mock of day1's join). */
const FREE: Record<string, Record<string, { agents: number; healthy: number }>> = {
  [B]: { [DELL]: { agents: 4, healthy: 4 }, [HP]: { agents: 3, healthy: 2 } },
  [A]: { [DELL]: { agents: 5, healthy: 5 }, [HP]: { agents: 3, healthy: 3 } },
  [C]: { [DELL]: { agents: 1, healthy: 1 }, [HP]: { agents: 0, healthy: 0 } },
};

/** The `need` params, summed per InfraEnv and sorted, as day1 echoes them. */
function needsOf(query: URLSearchParams): PlacementNeed[] {
  const summed = new Map<string, number>();
  for (const need of query.getAll("need").filter(Boolean)) {
    const [infraEnv, replicas] = need.split(":");
    summed.set(infraEnv, (summed.get(infraEnv) ?? 0) + Number(replicas));
  }
  return [...summed].sort(([a], [b]) => a.localeCompare(b)).map(([infra_env, replicas]) => ({ infra_env, replicas }));
}

/** One node type's part of the servers check, from `FREE`. */
function nodeType(mce: string, need: PlacementNeed): PlacementNodeType {
  const free = FREE[mce]?.[need.infra_env] ?? { agents: 0, healthy: 0 };
  return {
    infra_env: need.infra_env,
    needed: need.replicas,
    free_agents: free.agents,
    healthy: free.healthy,
    not_in_server_scan: 0,
    status: free.healthy >= need.replicas ? "pass" : "fail",
    detail: `${need.infra_env}: ${free.healthy} healthy free of ${need.replicas} needed`,
  };
}

/** The servers check a candidate's node types make: one failing type fails it, one unknown makes it unknown. */
function serversCheck(types: PlacementNodeType[]): PlacementCheck {
  const status = types.some((t) => t.status === "fail") ? "fail" : types.some((t) => t.status === "unknown") ? "unknown" : "pass";
  const detail = types.length > 0 ? `${types.map((t) => t.detail).join("; ")}.` : "No nodepool names a node type yet.";
  return { check: "servers", status, detail };
}

const PODS = (free: number, allocatable: number, counted: number) => ({
  free, allocatable, used: allocatable - free, nodes_counted: counted,
  nodes_excluded: { control_plane: 3, infra: 3, not_ready: 0, unschedulable: 1, tainted: 0 },
});

function candidate(name: string, needs: PlacementNeed[], overrides: Partial<PlacementCandidate>): PlacementCandidate {
  const nodeTypes = overrides.node_types ?? needs.map((need) => nodeType(name, need));
  return {
    mce: name,
    eligible: true,
    picked: false,
    rank: null,
    behind_on: null,
    checks: [
      { check: "version", ...PASS("Hosts OpenShift 4.18.22.") },
      { check: "free_pods", ...PASS("212 free pods; a new cluster needs 70.") },
      serversCheck(nodeTypes),
      { check: "readable", ...PASS("Wingman read its nodes and pods.") },
    ],
    node_types: nodeTypes,
    versions: VERSIONS,
    clusters: 2,
    open_creates: 0,
    owner_clusters: 0,
    spare: { total: 3, usable: 2 },
    spare_detail: null,
    pods: PODS(212, 500, 2),
    ...overrides,
  };
}

/** The contract's example: b picked over a on this owner's clusters; c fails three checks. */
function placement(query: URLSearchParams, overrides: Partial<Placement> = {}): Placement {
  const version = query.get("version");
  const owner = query.get("owner");
  const needs = needsOf(query);
  const base = {
    site: query.get("site") ?? "site1",
    env: query.get("env") ?? "prod",
    version,
    owner,
    flavor: query.get("flavor"),
    min_free_pods: 70,
    needs,
    versions: VERSIONS,
    server_scan_error: null,
  };
  if (!version) {
    // Without a version: the versions, the numbers, no pick
    return { ...base, pick: null, why: null, problems: ["Choose an OpenShift version."], candidates: [], ...overrides };
  }
  const cTypes = needs.map((need) => nodeType(C, need));
  return {
    ...base,
    pick: B,
    why: `${B} has the fewest clusters of owner ${owner ?? "?"}: 0, against 2 on ${A}.`,
    problems: [],
    candidates: [
      candidate(B, needs, { picked: true, rank: 1, open_creates: 1, owner_clusters: owner ? 0 : null }),
      candidate(A, needs, {
        rank: 2, behind_on: "owner_clusters", clusters: 6, owner_clusters: owner ? 2 : null, spare: { total: 3, usable: 1 },
        pods: PODS(140, 750, 3),
      }),
      candidate(C, needs, {
        eligible: false,
        clusters: 1,
        checks: [
          { check: "version", status: "fail", detail: "Hosts 4.16 to 4.17 only (4.17.30, 4.16.27), not 4.18.22." },
          { check: "free_pods", status: "fail", detail: "40 free pods; a new cluster needs 70." },
          serversCheck(cTypes),
          { check: "readable", ...PASS("Wingman read its nodes and pods.") },
        ],
        node_types: cTypes,
        versions: ["4.17.30", "4.16.27"],
        spare: null,
        spare_detail: `server-scan names no server for ${C}, so its spare servers are unknown.`,
        pods: { ...PODS(40, 250, 1), nodes_excluded: { control_plane: 3, infra: 0, not_ready: 1, unschedulable: 0, tainted: 0 } },
      }),
    ],
    ...overrides,
  };
}

/** `placement` with candidate A's node types replaced (and its servers check and eligibility made from them). */
function withATypes(query: URLSearchParams, types: (needs: PlacementNeed[]) => PlacementNodeType[]): Placement {
  const all = placement(query);
  const nodeTypes = types(all.needs);
  const servers = serversCheck(nodeTypes);
  return {
    ...all,
    why: `${B} is the only MCE that passes every check.`,
    candidates: all.candidates.map((c) =>
      c.mce === A
        ? {
            ...c, node_types: nodeTypes, eligible: servers.status === "pass", rank: null, behind_on: null,
            checks: c.checks.map((check) => (check.check === "servers" ? servers : check)),
          }
        : c
    ),
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

    // The owner and the nodepool's need are sent once typed (debounced), with the site, env, version and flavor
    await expect.poll(() => lastPlacement(calls).toString()).toContain("owner=7");
    await expect.poll(() => lastPlacement(calls).getAll("need")).toEqual([`${DELL}:2`]);
    expect(lastPlacement(calls).toString()).toBe(
      `site=site1&env=prod&version=4.18.22&owner=7&flavor=rcs&need=${DELL}%3A2`
    );
    await expect(page.getByTestId("placement-owner")).toContainText("Ranked for owner 7");
    await expect(page.getByTestId("placement-needs")).toHaveText(`Servers counted for the nodepools: 2 × ${DELL}.`);
    // Each candidate's healthy free servers of the type, against the need
    await expect(form.candidate(B).getByTestId(`placement-node-type-${DELL}`)).toHaveText(
      `${DELL}: 4 healthy free of 2 needed`
    );
    await expect(form.candidate(A).getByTestId(`placement-node-type-${DELL}`)).toHaveAttribute("data-status", "pass");

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
    // The servers check is told per node type, not as one more sentence
    await expect(failing.getByTestId("placement-check-servers")).toHaveCount(0);
    await expect(failing.getByTestId(`placement-node-type-${DELL}`)).toHaveText(`${DELL}: 1 healthy free of 2 needed`);
    await expect(failing.getByTestId(`placement-node-type-${DELL}`)).toHaveAttribute("data-status", "fail");
    await expect(failing.getByTestId("placement-cell-spare")).toContainText("unknown");
    await expect(failing).toContainText(`server-scan names no server for ${C}`);
    await expect(form.candidateRadio(C)).toBeDisabled();
    await failing.click({ force: true });
    await expect(form.candidateRadio(B)).toBeChecked();
    await expect(form.placementReason).toHaveCount(0);
  });

  test("an MCE short only of servers of a node type is explained and cannot be chosen", async ({ page }) => {
    await setup(page, {
      answer: (query) =>
        withATypes(query, (needs) =>
          needs.map((need) => ({
            ...nodeType(A, need), healthy: 1, status: "fail" as const,
            detail: `${need.infra_env}: 1 healthy free of ${need.replicas} needed`,
          }))
        ),
    });
    const form = new ClusterNewPage(page);
    await fillForm(form);
    await expect.poll(async () => (await form.candidate(A).getAttribute("data-eligible")) ?? "").toBe("false");

    const short = form.candidate(A);
    // Its version, free pods and readability pass: only the node type is listed, and why
    await expect(short.locator("[data-testid^='placement-check-']")).toHaveCount(0);
    await expect(short.getByTestId(`placement-node-type-${DELL}`)).toHaveText(`${DELL}: 1 healthy free of 2 needed`);
    await expect(short.getByTestId(`placement-node-type-${DELL}`)).toHaveAttribute("data-status", "fail");
    await expect(short).not.toContainText("Passes every check");
    await expect(form.candidateRadio(A)).toBeDisabled();
    await expect(form.candidateRadio(B)).toBeChecked();
  });

  test("a node type Wingman cannot count is unknown, and that MCE is not offered", async ({ page }) => {
    await setup(page, {
      answer: (query) =>
        withATypes(query, (needs) =>
          needs.map((need) => ({
            ...nodeType(A, need), healthy: null, not_in_server_scan: 0, status: "unknown" as const,
            detail: `${need.infra_env}: 5 free Agents for ${need.replicas} needed; server-scan did not answer, so their health is unknown`,
          }))
        ),
    });
    const form = new ClusterNewPage(page);
    await fillForm(form);

    const unknown = form.candidate(A).getByTestId(`placement-node-type-${DELL}`);
    await expect(unknown).toHaveAttribute("data-status", "unknown");
    await expect(unknown).toHaveText(
      `Unknown: ${DELL}: 5 free Agents for 2 needed; server-scan did not answer, so their health is unknown`
    );
    await expect(form.candidate(A)).toHaveAttribute("data-eligible", "false");
    await expect(form.candidateRadio(A)).toBeDisabled();
  });

  test("each nodepool's InfraEnv and replicas are sent as a need, and a change asks again", async ({ page }) => {
    const calls = await setup(page);
    const form = new ClusterNewPage(page);
    await form.goto();
    await form.chooseSpec("rcs");
    await form.selectSite("site1");
    await form.selectEnv("prod");
    await form.selectVersion("4.18.22");

    // No InfraEnv yet: nothing to count, said calmly; the pick may change once there is one
    await expect(page.getByTestId("placement-pick-name")).toHaveText(B);
    await expect(page.getByTestId("placement-no-needs")).toContainText("No nodepool names a node type yet");
    expect(calls.placements.every((q) => q.getAll("need").join("") === "")).toBe(true);
    expect(lastPlacement(calls).getAll("need")).toEqual([""]);
    await expect(form.candidate(B).getByTestId("placement-node-types")).toHaveCount(0);

    await page.getByPlaceholder(`e.g. ${DELL}`).fill(DELL);
    await expect.poll(() => lastPlacement(calls).getAll("need")).toEqual([`${DELL}:2`]);
    await expect(page.getByTestId("placement-needs")).toContainText(`2 × ${DELL}`);

    // The replicas shown, as typed; a count day1 would refuse (0) is not a need
    // The template field is named by its placeholder, the default (2), as every template input is
    const replicas = page.getByPlaceholder("2", { exact: true });
    await replicas.fill("0");
    await expect(page.getByTestId("placement-no-needs")).toBeVisible();
    await replicas.fill("3");
    await expect.poll(() => lastPlacement(calls).getAll("need")).toEqual([`${DELL}:3`]);
    expect(calls.placements.some((q) => q.getAll("need").includes(`${DELL}:0`))).toBe(false);
    expect(lastPlacement(calls).toString()).toContain(`need=${DELL}%3A3`);
    await expect(page.getByTestId("placement-needs")).toContainText(`3 × ${DELL}`);

    // An InfraEnv that is not a Kubernetes name is not a need until it is one
    await page.getByPlaceholder(`e.g. ${DELL}`).fill("Dell R660");
    await expect(page.getByTestId("placement-no-needs")).toBeVisible();
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
