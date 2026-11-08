/**
 * The flavor page (mocked): presets and locks on the overview, the flavor's
 * warnings, Delete refused while clusters follow it, and "Add existing
 * clusters" (ADR-0037): pick with filters, a preview with every status, a
 * re-link only with its checkbox, the import request, and a stale preview.
 * Shapes follow docs/notes/2026-11-08-flavors-v2-api-changes.md §5, §6, §9-§11.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, json, mockDashboardApis, mockMR } from "../fixtures/api-handlers";
import type {
  ClusterDrift,
  ClusterStatus,
  ImportCandidate,
  ImportPreview,
  ImportRequest,
  SpecCluster,
  SpecDetail,
  ValueDrift,
} from "../../types";

// ── Mock data ────────────────────────────────────────────────────────────────

const FLAVOR = "agent-baseline";
const MCE1 = "ocp4-prod-mce-site1-a";
const MCE2 = "ocp4-prep-mce-site2-a";

const SPEC: SpecDetail = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name: FLAVOR, description: "Every nodepool gets the team's machine configs", version: "1.0.0", labels: { platform: "agent" } },
  spec: {
    day1: {
      variables: [],
      structure: { nodepools: [{ configs: [{}, {}, {}] }] },
      locked_paths: ["owner_anaf", "nodepools[*].configs", "owner_mador"],
      template: "",
      values: {
        owner_merkaz: "1234",
        owner_anaf: "56",
        nodepools: [
          {
            replicas: 2,
            configs: [{ name: "nm-conf", hardware: "dell" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
          },
        ],
      },
    },
    day2: { addons: [{ team: "redbull", name: "cluster-roles", version: "main", overrideable: [] }] },
  },
  load_error: null,
  load_problems: [],
  warnings: ["locked_paths: owner_mador is locked but spec.day1.values sets no value for it"],
  last_commit_id: "aaaaaaaa11111111aaaaaaaa11111111aaaaaaaa",
};

function cluster(name: string, site: string, mce: string, owner: Record<string, string>, spec_name: string | null = null): ClusterStatus {
  const short = name.replace(/^ocp4-/, "");
  return {
    name, site, mce, phase: "Unknown", spec_name, spec_version: spec_name ? "1.0.0" : null,
    created_by: "alice", created_at: "2026-11-07T10:00:00+00:00", mastertag: "4.16.27-x86_64",
    path: `sites/${site}/mces/${mce}/hostedClusters/${name}.yaml`,
    hosted_cluster: { cluster_name: short, name: `ocp4-${short}`, namespace: `hcp-${short}` },
    naming: { follows_convention: true, env: "prod", short_name: short, sequence: null, problems: [] },
    owner, problems: [],
  };
}

const CLUSTERS: ClusterStatus[] = [
  cluster("ocp4-prod-heron-site1", "site1", MCE1, { merkaz: "1234", anaf: "56", mador: "7" }),
  cluster("ocp4-prod-lark-site1", "site1", MCE1, { merkaz: "1234", anaf: "99", mador: "7" }, "agent-standard"),
  cluster("ocp4-prod-owl-site1", "site1", MCE1, { merkaz: "1234", anaf: "56", mador: "8" }, FLAVOR),
  cluster("ocp4-prod-hawk-site1", "site1", MCE1, { merkaz: "1234", anaf: "56", mador: "7" }),
  cluster("ocp4-prep-kite-site2", "site2", MCE2, { merkaz: "4321", anaf: "56", mador: "7" }),
  cluster("ocp4-prep-wren-site2", "site2", MCE2, {}),
];
const byName = (name: string) => CLUSTERS.find((c) => c.name === name)!;

function drift(name: string, overrides: Partial<ClusterDrift> = {}): ClusterDrift {
  const c = byName(name);
  return {
    cluster: c.name, site: c.site, mce: c.mce, state: "in_sync", is_drifted: false,
    spec_name: FLAVOR, spec_version: "1.0.0", current_spec_version: "1.0.0",
    value_drift: [], addon_drift: [], version_differences: [], error: null, ...overrides,
  };
}

const CONFIGS_DRIFT: ValueDrift = {
  path: "nodepools[*].configs",
  file_key: "nodepool[0].configs",
  nodepool: { index: 0, name: "prod-heron-site1-dell-r660-site1-128c-1024gb-5tb" },
  flavor_value: [{ name: "nm-conf-prod-heron-site1-dell" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
  cluster_value: [{ name: "nm-conf-prod-heron-site1-dell" }, { name: "workers-chrony-configuration" }, { name: "restored-example-config" }],
  in_file: true,
  added: ["nic-ring-buffer"],
  removed: ["restored-example-config"],
  needs_decision: null,
  needs_hardware: false,
  reboots: true,
};

const NEEDS_HARDWARE: ValueDrift = {
  ...CONFIGS_DRIFT,
  file_key: "nodepool[1].configs",
  nodepool: { index: 1, name: "prod-heron-site1-dell-r760-site1-64c-512gb-20tb" },
  flavor_value: [{ name: "nm-conf" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
  cluster_value: [{ name: "workers-chrony-configuration" }],
  added: [],
  removed: [],
  needs_decision: "nodepool[1] names no network config, so its hardware type must be chosen",
  needs_hardware: true,
};

const OWNER_DRIFT: ValueDrift = {
  path: "owner_anaf", file_key: "owner.anaf", nodepool: null, flavor_value: "56", cluster_value: "99", in_file: true,
  added: [], removed: [], needs_decision: null, needs_hardware: false, reboots: false,
};

function candidate(name: string, overrides: Partial<ImportCandidate>): ImportCandidate {
  const c = byName(name);
  return {
    name: c.name, site: c.site, mce: c.mce, path: c.path,
    last_commit_id: `${name.length.toString(16).padStart(2, "0")}c904bfafde4c4ed24416190ea224ee25cdcf7`,
    status: "ready", linked_spec: null, problems: [], drift: drift(name), ...overrides,
  };
}

const POSITIONAL_WARNING =
  "nodepools[0].replicas locks one nodepool by position: on a cluster the flavor did not create it compares the file's nodepool[0], whichever that is";

const PREVIEW: ImportPreview = {
  spec_name: FLAVOR,
  spec_version: "1.0.0",
  warnings: [POSITIONAL_WARNING],
  clusters: [
    candidate("ocp4-prod-heron-site1", {
      drift: drift("ocp4-prod-heron-site1", {
        state: "drifted", is_drifted: true,
        value_drift: [CONFIGS_DRIFT, NEEDS_HARDWARE],
        addon_drift: [{ addon_name: "cluster-roles", team: "redbull", reason: "missing", expected_version: "main", override_values: {} }],
      }),
    }),
    candidate("ocp4-prod-lark-site1", {
      status: "relink",
      linked_spec: { name: "agent-standard", version: "1.0.0" },
      problems: ["ocp4-prod-lark-site1: follows flavor agent-standard v1.0.0; send relink: true to link it to agent-baseline instead"],
      drift: drift("ocp4-prod-lark-site1", { state: "drifted", is_drifted: true, value_drift: [OWNER_DRIFT] }),
    }),
    candidate("ocp4-prod-hawk-site1", {
      status: "refused",
      problems: ["ocp4-prod-hawk-site1: the file's layout cannot be edited: nodepool is written in flow style"],
    }),
    candidate("ocp4-prep-kite-site2", {
      status: "linked",
      linked_spec: { name: FLAVOR, version: "1.0.0" },
      problems: ["ocp4-prep-kite-site2: already follows flavor agent-baseline v1.0.0; sync it instead"],
    }),
  ],
};

const FOLLOWERS: SpecCluster[] = [
  { name: "ocp4-prod-owl-site1", site: "site1", mce: MCE1, phase: "Unknown", state: "drifted", is_drifted: true, error: null },
  { name: "ocp4-prod-herzi-site1", site: "site1", mce: MCE1, phase: "Unknown", state: "in_sync", is_drifted: false, error: null },
];

// ── Helpers ──────────────────────────────────────────────────────────────────

const base = `**/api/day1/specs/${FLAVOR}`;

/** Auth, the dashboard, the flavor and its followers, every cluster; then the routes a test adds. */
async function open(
  page: Page,
  {
    followers = [] as SpecCluster[],
    clusters = CLUSTERS,
    routes = (async () => {}) as (page: Page) => Promise<void>,
  } = {}
) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters", (r) => json(r, clusters));
  await page.route(base, (r) => json(r, SPEC));
  await page.route(`${base}/clusters`, (r) => json(r, followers));
  await routes(page);
  await go(page, `/specs/${FLAVOR}`);
}

const sheet = (page: Page) => page.getByTestId("import-sheet");
const pickRow = (page: Page, name: string) => page.getByTestId(`import-pick-${name}`);
const candidateCard = (page: Page, name: string) => page.getByTestId(`import-candidate-${name}`);

async function openImport(page: Page) {
  await page.getByRole("main").getByRole("button", { name: "Add existing clusters" }).first().click();
  await expect(sheet(page).getByRole("heading", { name: "Add existing clusters" })).toBeVisible();
}

/** Pick the four clusters of the preview and preview them; resolves with each preview request's body. */
async function previewFour(page: Page, previews: unknown[]) {
  await openImport(page);
  for (const name of ["ocp4-prod-heron-site1", "ocp4-prod-lark-site1", "ocp4-prod-hawk-site1", "ocp4-prep-kite-site2"]) {
    await pickRow(page, name).click();
  }
  await expect(sheet(page).getByTestId("import-picked-count")).toContainText("4 of at most 50 picked");
  await sheet(page).getByRole("button", { name: "Preview 4 clusters" }).click();
  await expect(candidateCard(page, "ocp4-prod-heron-site1")).toBeVisible();
  expect(previews.length).toBeGreaterThan(0);
}

function previewRoute(previews: unknown[], answer: (route: Route) => Promise<void> = (r) => json(r, PREVIEW)) {
  return async (p: Page) => {
    await p.route(`${base}/import/preview`, async (r) => {
      previews.push(r.request().postDataJSON());
      await answer(r);
    });
  };
}

// ── Overview ─────────────────────────────────────────────────────────────────

test.describe("Flavor overview", () => {
  test("each value is a preset or locked, and configs read as configs", async ({ page }) => {
    await open(page);

    const inputs = page.getByTestId("flavor-inputs");
    await expect(inputs.getByTestId("flavor-input-counts")).toHaveText("2 presets · 2 locked");
    await expect(inputs.getByTestId("flavor-input-owner_merkaz")).toHaveAttribute("data-kind", "preset");
    await expect(inputs.getByTestId("flavor-input-owner_merkaz")).toContainText("Preset");
    await expect(inputs.getByTestId("flavor-input-owner_anaf")).toHaveAttribute("data-kind", "locked");
    await expect(inputs.getByTestId("flavor-input-owner_anaf")).toContainText("Locked");
    await expect(inputs.getByTestId("flavor-input-nodepools[0].replicas")).toHaveAttribute("data-kind", "preset");

    // The rule locks every nodepool's configs; nm-conf is the cluster's own network config
    const configs = inputs.getByTestId("flavor-input-nodepools[0].configs");
    await expect(configs).toHaveAttribute("data-kind", "locked");
    await expect(configs).toContainText("Locked · every nodepool");
    await expect(configs).toContainText("nm-conf");
    await expect(configs).toContainText("network config · dell hardware");
    await expect(configs).toContainText("workers-chrony-configuration");
    await expect(configs).toContainText("nic-ring-buffer");
    await expect(configs).not.toContainText("{");
    await expect(inputs.getByTestId("flavor-configs-rule")).toContainText("every nodepool of a cluster has exactly these configs");

    // A lock with no value fixes nothing, and says so
    await expect(inputs.getByTestId("flavor-locks-without-value")).toContainText("owner_mador");
    // The stage 1 wording is gone: a lock is a fixed value, not "locked after create"
    await expect(page.getByText(/locked after create/i)).toHaveCount(0);
  });

  test("the rules the stored flavor breaks are shown above the tabs", async ({ page }) => {
    await open(page);

    const warnings = page.getByTestId("flavor-warnings");
    await expect(warnings).toContainText("This flavor breaks 1 rule");
    await expect(warnings).toContainText("owner_mador is locked but spec.day1.values sets no value for it");
    await expect(warnings).toContainText("saving it unchanged is refused");
  });

  test("no warnings, no panel", async ({ page }) => {
    await open(page, {
      routes: async (p) => {
        await p.route(base, (r) => json(r, { ...SPEC, warnings: [] }));
      },
    });

    await expect(page.getByTestId("flavor-inputs")).toBeVisible();
    await expect(page.getByTestId("flavor-warnings")).toHaveCount(0);
  });
});

// ── Clusters and delete ──────────────────────────────────────────────────────

test.describe("Clusters that follow the flavor", () => {
  test("Delete is refused while clusters follow the flavor, and says why", async ({ page }) => {
    await open(page, { followers: FOLLOWERS });

    const del = page.getByRole("main").getByRole("button", { name: "Delete", exact: true });
    await expect(del).toBeDisabled();
    await expect(del).toHaveAccessibleDescription(/2 clusters follow this flavor, so it can't be deleted/);
    await expect(page.getByTestId("flavor-followers")).toHaveText("2 clusters follow it");

    await page.getByRole("button", { name: "Clusters (2)" }).click();
    await expect(page.getByTestId("spec-cluster-ocp4-prod-owl-site1")).toContainText("Drifted");
    await expect(page.getByRole("link", { name: "ocp4-prod-owl-site1" })).toHaveAttribute(
      "href", `/clusters/ocp4-prod-owl-site1?site=site1&mce=${MCE1}`
    );
  });

  test("a flavor no cluster follows can be deleted, and offers to add clusters", async ({ page }) => {
    await open(page);

    await expect(page.getByRole("main").getByRole("button", { name: "Delete", exact: true })).toBeEnabled();
    await expect(page.getByTestId("flavor-followers")).toHaveText("None follow it yet");
    await page.getByRole("button", { name: "Clusters (0)" }).click();
    const empty = page.getByTestId("spec-clusters-empty");
    await expect(empty).toContainText("No clusters follow this flavor yet");
    await empty.getByRole("button", { name: "Add existing clusters" }).click();
    await expect(sheet(page).getByRole("heading", { name: "Add existing clusters" })).toBeVisible();
  });
});

// ── Pick ─────────────────────────────────────────────────────────────────────

test.describe("Add existing clusters: pick", () => {
  test("search and filter by site, MCE and owner; a cluster on this flavor can't be picked", async ({ page }) => {
    await open(page);
    await openImport(page);

    const list = sheet(page).getByTestId("import-pick-list");
    await expect(list.getByRole("checkbox")).toHaveCount(CLUSTERS.length + 1); // and "Pick all shown"
    await expect(sheet(page).getByTestId("import-pick-shown")).toContainText("6 of 6 clusters · 1 already on this flavor");

    // Already on this flavor: marked and not pickable
    const owl = pickRow(page, "ocp4-prod-owl-site1");
    await expect(owl).toContainText("On this flavor");
    await expect(owl).toHaveAttribute("aria-disabled", "true");
    await owl.click({ force: true });
    await expect(owl).toHaveAttribute("aria-checked", "false");
    // Following another flavor: marked, and pickable
    await expect(pickRow(page, "ocp4-prod-lark-site1")).toContainText("Follows agent-standard");
    await expect(pickRow(page, "ocp4-prod-heron-site1")).toContainText("merkaz 1234 · anaf 56 · mador 7");
    await expect(pickRow(page, "ocp4-prep-wren-site2")).toContainText("no owner");

    // Site
    await sheet(page).getByRole("combobox", { name: "Site" }).click();
    await page.getByRole("option", { name: "site2" }).click();
    await expect(list.getByTestId(/^import-pick-ocp4/)).toHaveCount(2);
    await expect(pickRow(page, "ocp4-prep-kite-site2")).toBeVisible();
    await sheet(page).getByRole("button", { name: "Clear filters" }).click();

    // MCE
    await sheet(page).getByRole("combobox", { name: "MCE" }).click();
    await page.getByRole("option", { name: MCE1 }).click();
    await expect(list.getByTestId(/^import-pick-ocp4/)).toHaveCount(4);
    await sheet(page).getByRole("button", { name: "Clear filters" }).click();

    // Owner numbers, exact
    await sheet(page).getByLabel("Owner anaf").fill("56");
    await sheet(page).getByLabel("Owner mador").fill("7");
    await expect(list.getByTestId(/^import-pick-ocp4/)).toHaveCount(3); // heron, hawk, kite
    await expect(pickRow(page, "ocp4-prod-owl-site1")).toHaveCount(0);
    await sheet(page).getByLabel("Owner merkaz").fill("4321");
    await expect(list.getByTestId(/^import-pick-ocp4/)).toHaveCount(1);
    await expect(pickRow(page, "ocp4-prep-kite-site2")).toBeVisible();

    // A pick survives the filters that hide it
    await pickRow(page, "ocp4-prep-kite-site2").click();
    await sheet(page).getByRole("button", { name: "Clear filters" }).click();
    await sheet(page).getByLabel("Search clusters by name").fill("heron");
    await expect(list.getByTestId(/^import-pick-ocp4/)).toHaveCount(1);
    await pickRow(page, "ocp4-prod-heron-site1").click();
    await expect(sheet(page).getByTestId("import-picked-count")).toContainText("2 of at most 50 picked");
    await expect(sheet(page).getByText("1 picked cluster is not shown by the filters.")).toBeVisible();
    await expect(sheet(page).getByRole("button", { name: "Preview 2 clusters" })).toBeEnabled();
  });

  test("one import takes at most 50 clusters", async ({ page }) => {
    const many = [
      ...Array.from({ length: 50 }, (_, i) => cluster(`ocp4-prod-c${String(i).padStart(2, "0")}-site1`, "site1", MCE1, { merkaz: "1" })),
      ...Array.from({ length: 5 }, (_, i) => cluster(`ocp4-prep-d${i}-site2`, "site2", MCE2, { merkaz: "2" })),
    ];
    await open(page, { clusters: many });
    await openImport(page);

    // 55 shown: picking them all would be more than one import takes
    const pickAll = sheet(page).getByRole("checkbox", { name: /Pick all 55 shown/ });
    await expect(pickAll).toHaveAttribute("aria-disabled", "true");

    await sheet(page).getByRole("combobox", { name: "Site" }).click();
    await page.getByRole("option", { name: "site1" }).click();
    await sheet(page).getByRole("checkbox", { name: /Pick all 50 shown/ }).click();
    await expect(sheet(page).getByTestId("import-picked-count")).toContainText("50 of at most 50 picked");
    await expect(sheet(page).getByTestId("import-pick-full")).toContainText("one import takes at most 50 clusters");

    await sheet(page).getByRole("button", { name: "Clear filters" }).click();
    const extra = pickRow(page, "ocp4-prep-d0-site2");
    await expect(extra).toHaveAttribute("aria-disabled", "true");
    await extra.click({ force: true });
    await expect(extra).toHaveAttribute("aria-checked", "false");
    await expect(sheet(page).getByRole("button", { name: "Preview 50 clusters" })).toBeEnabled();
  });
});

// ── Preview and import ───────────────────────────────────────────────────────

test.describe("Add existing clusters: preview and import", () => {
  test("the preview shows every status, the flavor's warnings and what will drift", async ({ page }) => {
    const previews: unknown[] = [];
    await open(page, { routes: previewRoute(previews) });
    await previewFour(page, previews);

    // The request pins each pick's file, in the order they were picked
    expect(previews[0]).toEqual({
      clusters: [
        { name: "ocp4-prod-heron-site1", site: "site1", mce: MCE1 },
        { name: "ocp4-prod-lark-site1", site: "site1", mce: MCE1 },
        { name: "ocp4-prod-hawk-site1", site: "site1", mce: MCE1 },
        { name: "ocp4-prep-kite-site2", site: "site2", mce: MCE2 },
      ],
    });

    // What the import does, and the flavor's warnings
    await expect(sheet(page).getByTestId("import-explainer")).toContainText("writes only the flavor link");
    await expect(sheet(page).getByTestId("import-explainer")).toContainText("Nothing on the clusters changes");
    await expect(sheet(page).getByTestId("import-preview-warnings")).toContainText(POSITIONAL_WARNING);

    // ready: what will show as drift once linked
    const heron = candidateCard(page, "ocp4-prod-heron-site1");
    await expect(heron).toHaveAttribute("data-status", "ready");
    await expect(heron).toContainText("Ready");
    await expect(heron).toContainText("2 locked values differ · 1 needs a person to decide · 1 add-on missing");
    const configs = heron.getByTestId("value-drift-nodepool[0].configs");
    await expect(configs).toContainText("prod-heron-site1-dell-r660-site1-128c-1024gb-5tb");
    await expect(configs.getByText("nic-ring-buffer")).toBeVisible();
    await expect(configs.getByText("restored-example-config")).toBeVisible();
    await expect(configs).toContainText("a sync rolls this nodepool's nodes");
    await expect(heron.getByTestId("value-drift-nodepool[1].configs")).toContainText(
      "nodepool[1] names no network config, so its hardware type must be chosen"
    );
    await expect(heron).toContainText("Missing add-ons:");
    await expect(heron).toContainText("cluster-roles");

    // relink: follows another flavor; moving it is a choice
    const lark = candidateCard(page, "ocp4-prod-lark-site1");
    await expect(lark).toContainText("On another flavor");
    await expect(lark).toContainText("Follows flavor agent-standard v1.0.0");
    await expect(lark.getByRole("checkbox", { name: `Move to ${FLAVOR}` })).toHaveAttribute("aria-checked", "false");
    await expect(lark.getByTestId("value-drift-owner.anaf")).toContainText("flavor 56 · file 99");
    await expect(lark).not.toContainText("send relink: true");

    // refused: its problems
    const hawk = candidateCard(page, "ocp4-prod-hawk-site1");
    await expect(hawk).toContainText("Can't be imported");
    await expect(hawk).toContainText("nodepool is written in flow style");

    // linked: nothing to import, sync it instead
    const kite = candidateCard(page, "ocp4-prep-kite-site2");
    await expect(kite).toContainText("Already on this flavor");
    await expect(kite.getByRole("link", { name: /Sync it from its page/ })).toHaveAttribute(
      "href", `/clusters/ocp4-prep-kite-site2?site=site2&mce=${MCE2}`
    );

    await expect(sheet(page).getByTestId("import-summary")).toHaveText("1 to link · 3 left out");
  });

  test("a cluster on another flavor is imported only when moved, and the request carries the preview", async ({ page }) => {
    const previews: unknown[] = [];
    let sent: ImportRequest | null = null;
    await open(page, {
      routes: async (p) => {
        await previewRoute(previews)(p);
        await p.route(`${base}/import`, async (r) => {
          sent = r.request().postDataJSON();
          await json(r, mockMR({ iid: 21, title: `[Wingman/Day1] Import spec ${FLAVOR} into 2 clusters` }), 201);
        });
      },
    });
    await previewFour(page, previews);

    const importButton = sheet(page).getByRole("button", { name: /^Import \d+ clusters?$/ });
    await expect(importButton).toHaveText("Import 1 cluster");
    await candidateCard(page, "ocp4-prod-lark-site1").getByRole("checkbox", { name: `Move to ${FLAVOR}` }).click();
    await expect(sheet(page).getByTestId("import-summary")).toHaveText("2 to link · 2 left out");
    await expect(importButton).toHaveText("Import 2 clusters");
    await importButton.click();

    await expect(page.getByText("Import MR !21 opened")).toBeVisible();
    await expect(sheet(page)).toHaveCount(0);
    const byCandidate = (name: string) => PREVIEW.clusters.find((c) => c.name === name)!;
    expect(sent).toEqual({
      spec_version: "1.0.0",
      clusters: [
        { name: "ocp4-prod-heron-site1", site: "site1", mce: MCE1, last_commit_id: byCandidate("ocp4-prod-heron-site1").last_commit_id, relink: false },
        { name: "ocp4-prod-lark-site1", site: "site1", mce: MCE1, last_commit_id: byCandidate("ocp4-prod-lark-site1").last_commit_id, relink: true },
      ],
    });
  });

  test("a file or the flavor that changed since the preview asks to preview again", async ({ page }) => {
    const previews: unknown[] = [];
    let imports = 0;
    await open(page, {
      routes: async (p) => {
        await previewRoute(previews)(p);
        await p.route(`${base}/import`, async (r) => {
          imports += 1;
          await fulfillProblem(r, 409, "REVISION_CONFLICT",
            "changed since the preview: ocp4-prod-heron-site1 (0c904bfa → 8bc41021); preview the import again");
        });
      },
    });
    await previewFour(page, previews);
    await sheet(page).getByRole("button", { name: "Import 1 cluster" }).click();

    const stale = sheet(page).getByTestId("import-stale");
    await expect(stale).toContainText("changed since this preview, so nothing was imported");
    await expect(sheet(page).getByRole("button", { name: "Import 1 cluster" })).toBeDisabled();
    await stale.getByRole("button", { name: "Preview again" }).click();

    await expect(stale).toHaveCount(0);
    await expect(candidateCard(page, "ocp4-prod-heron-site1")).toBeVisible();
    expect(previews).toHaveLength(2);
    expect(previews[1]).toEqual(previews[0]);
    await expect(sheet(page).getByRole("button", { name: "Import 1 cluster" })).toBeEnabled();
    expect(imports).toBe(1);
  });

  test("a refused import lists every problem and keeps the sheet open", async ({ page }) => {
    const previews: unknown[] = [];
    const problems = [
      "ocp4-prod-heron-site1: already follows flavor agent-baseline v1.0.0; sync it instead",
    ];
    await open(page, {
      routes: async (p) => {
        await previewRoute(previews)(p);
        await p.route(`${base}/import`, (r) =>
          fulfillProblem(r, 422, "VALIDATION_ERROR", "these clusters cannot be imported into flavor agent-baseline", { problems })
        );
      },
    });
    await previewFour(page, previews);
    await sheet(page).getByRole("button", { name: "Import 1 cluster" }).click();

    const alert = sheet(page).getByRole("alert").filter({ hasText: "The import was refused" });
    await expect(alert).toContainText(problems[0]);
    await expect(candidateCard(page, "ocp4-prod-heron-site1")).toBeVisible();
  });

  test("a preview that is refused shows why, and Back keeps the picks", async ({ page }) => {
    const previews: unknown[] = [];
    await open(page, {
      routes: previewRoute(previews, (r) =>
        fulfillProblem(r, 422, "VALIDATION_ERROR", "the clusters picked cannot be imported", {
          problems: ["clusters: ocp4-prod-heron-site1 is picked twice"],
        })
      ),
    });
    await openImport(page);
    await pickRow(page, "ocp4-prod-heron-site1").click();
    await sheet(page).getByRole("button", { name: "Preview 1 cluster" }).click();

    await expect(sheet(page).getByRole("alert").filter({ hasText: "could not be previewed" })).toContainText(
      "ocp4-prod-heron-site1 is picked twice"
    );
    await sheet(page).getByRole("button", { name: "Back" }).click();
    await expect(pickRow(page, "ocp4-prod-heron-site1")).toHaveAttribute("aria-checked", "true");
  });
});
