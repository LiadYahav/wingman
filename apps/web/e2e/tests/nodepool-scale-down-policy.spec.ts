/**
 * A nodepool's own scale-down policy (ADR-0062, mocked): which servers leave
 * first when its NodePool scales down, the `redbull.io/scale-down-policy`
 * annotation update-nodepool reads. Day1 offers `nodepools[].scale_down_policy`
 * in the template schema only when the specs project's template writes it, so
 * the schema is the switch:
 * - the create form's select, whose platform default sends nothing, and a
 *   flavor's locked policy shown read only;
 * - the flavor editor's preset, which can be locked;
 * - Edit cluster's policy per nodepool, which edits the file's text.
 * Invented names only.
 */

import { test, expect, type Page, type Route, type Request } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis, mockMachineConfigs, mockMR, placementAnswer } from "../fixtures/api-handlers";
import { ClusterNewPage } from "../pages/cluster-new.page";
import type { ClusterDetail, ClusterPreview, ClusterSpec, CreateClusterRequest, Mce, SpecEntry, TemplateField } from "../../types";

const DELL = "dell-r660-site1-128c-1024gb-5tb";
const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const STATIC = [{ name: "workers-chrony-configuration" }];
const KEY = "redbull.io/scale-down-policy";

const schema = (on: boolean): TemplateField[] => [
  { name: "owner_merkaz", type: "string", required: true, example: "1234" },
  { name: "owner_anaf", type: "string", required: true, example: "56" },
  { name: "owner_mador", type: "string", required: true, example: "7" },
  {
    name: "nodepools",
    type: "list",
    required: true,
    fields: [
      { name: "infra_env", type: "string", required: true, example: DELL },
      { name: "replicas", type: "string", required: false, default: 2 },
      ...(on ? [{ name: "scale_down_policy", type: "string" as const, required: false, default: "" }] : []),
      { name: "configs", type: "list", required: false, default: [], fields: [{ name: "name", type: "string", required: true }] },
    ],
  },
];

const flavor = (name: string, pool: Record<string, unknown>, locked: string[] = []): SpecEntry => ({
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name, description: `The ${name} flavor`, version: "1.0.0", labels: {} },
  spec: {
    day1: { variables: [], structure: { nodepools: [{}] }, locked_paths: locked, template: "# template", values: { nodepools: [{ configs: STATIC, ...pool }] } },
    day2: { addons: [] },
  },
  load_error: null,
  load_problems: [],
  warnings: [],
});

const MCES: Mce[] = [
  {
    name: MCE, site: SITE, env: "prod", letter: "a", follows_convention: true, naming_problems: [],
    default_mastertag: "4.16.27-x86_64", hub_version: "4.16.27-x86_64", cluster_count: 4, stray_files: [], problems: [],
  },
];

const PREVIEW: ClusterPreview = { yaml: "mastertag: 4.16.27-x86_64\n", path: `sites/${SITE}/mces/${MCE}/hostedClusters/ocp4-prod-rcs-site1-a.yaml` };

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: status >= 400 ? "application/problem+json" : "application/json", body: JSON.stringify(body) });

async function base(page: Page, on: boolean) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/specs/template/schema**", (r) => json(r, schema(on)));
  await page.route("**/api/day1/mces/*/infraenvs", (r) => json(r, [DELL]));
  await page.route("**/api/day1/machine-configs", (r) => json(r, mockMachineConfigs));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
  await page.route("**/api/day2/addons", (r) => json(r, []));
}

const policy = (page: Page, testId = "nodepool-0-scale-down-policy") => page.getByTestId(testId);
const choose = async (page: Page, testId: string, name: string) => {
  await page.getByTestId(`${testId}-trigger`).click();
  await page.getByRole("option", { name: new RegExp(`^${name}`) }).click();
  await expect(page.getByRole("option")).toHaveCount(0); // closed, so the next select's options are the only ones
};

// ── The create form ──────────────────────────────────────────────────────────

async function openCreate(page: Page, on: boolean, spec: SpecEntry): Promise<{ form: ClusterNewPage; previews: CreateClusterRequest[] }> {
  const previews: CreateClusterRequest[] = [];
  await base(page, on);
  await page.route("**/api/day1/specs", (r) => json(r, [spec]));
  await page.route("**/api/day1/sites", (r) => json(r, [SITE]));
  await page.route("**/api/day1/placement**", (r) => json(r, placementAnswer(new URL(r.request().url()).searchParams)));
  await page.route("**/api/day1/clusters/name-suggestion**", (r) =>
    json(r, { name: `ocp4-prod-${spec.metadata.name}-site1-a`, env: "prod", short_name: spec.metadata.name, sequence: "a", problems: [] })
  );
  await page.route("**/api/day1/clusters/preview", (r) => {
    previews.push(r.request().postDataJSON());
    return json(r, PREVIEW);
  });
  const form = new ClusterNewPage(page);
  await form.goto();
  await form.chooseSpec(spec.metadata.name);
  await form.place({ site: SITE, env: "prod", version: "4.16.27" });
  for (const owner of ["1234", "56", "7"]) await form.templateInput(owner).fill(owner);
  await page.getByTestId("infra-env-select-nodepools[0].infra_env").click();
  await form.option(DELL).click();
  return { form, previews };
}

const sentPool = (previews: CreateClusterRequest[]) => (previews.at(-1)?.variables.nodepools as Record<string, unknown>[])[0];

test.describe("A nodepool's scale-down policy on the create form", () => {
  test("is the platform default, which sends nothing, or a policy, sent with the nodepool", async ({ page }) => {
    const { form, previews } = await openCreate(page, true, flavor("rcs", {}));
    const field = page.locator('[data-field-path="nodepools[0].scale_down_policy"]');
    await expect(field).toContainText("Scale-down policy");
    await expect(policy(page).getByTestId("nodepool-0-scale-down-policy-trigger")).toHaveText(/Platform default/);
    await expect(policy(page).getByTestId("nodepool-0-scale-down-policy-note")).toHaveText(/CAPI picks the nodes that leave at random/);

    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(sentPool(previews)).not.toHaveProperty("scale_down_policy");
    await page.keyboard.press("Escape");

    await choose(page, "nodepool-0-scale-down-policy", "least-utilized");
    await expect(policy(page).getByTestId("nodepool-0-scale-down-policy-note")).toHaveText(/metrics API/);
    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(sentPool(previews).scale_down_policy).toBe("least-utilized");
  });

  test("is not offered when the specs project's template does not write it", async ({ page }) => {
    const { form, previews } = await openCreate(page, false, flavor("rcs", {}));
    await expect(page.locator('[data-field-path="nodepools[0].scale_down_policy"]')).toHaveCount(0);
    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(sentPool(previews)).not.toHaveProperty("scale_down_policy");
  });

  test("a flavor's locked policy is shown read only and sent as the flavor has it", async ({ page }) => {
    const locked = flavor("quiet", { scale_down_policy: "least-requested" }, ["nodepools[0].scale_down_policy"]);
    const { form, previews } = await openCreate(page, true, locked);
    await expect(policy(page).getByTestId("nodepool-0-scale-down-policy-value")).toHaveText("least-requested");
    await expect(policy(page).getByTestId("nodepool-0-scale-down-policy-trigger")).toHaveCount(0);
    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(sentPool(previews).scale_down_policy).toBe("least-requested");
  });
});

// ── The flavor editor ────────────────────────────────────────────────────────

test.describe("A nodepool's scale-down policy in the flavor editor", () => {
  test("is a preset that can be locked, saved with the nodepool", async ({ page }) => {
    const writes: ClusterSpec[] = [];
    await base(page, true);
    await page.route("**/api/day1/specs/template", (r) => json(r, "# cluster-template.j2"));
    await page.route("**/api/day1/specs", (r) => {
      if (r.request().method() !== "POST") return json(r, []);
      writes.push(r.request().postDataJSON());
      return json(r, mockMR({ repo: "specs", iid: 65 }), 201);
    });
    await go(page, "/specs/new");
    await expect(page.getByRole("heading", { name: "New Flavor" })).toBeVisible();
    await page.getByTestId("spec-name-input").fill("agent-quiet");
    await page.getByTestId("nodepool-0-configs").getByRole("combobox", { name: /entry 1 hardware type$/ }).click();
    await page.getByRole("option").filter({ has: page.getByText("dell", { exact: true }) }).click();

    const card = page.getByTestId("nodepool-0");
    const lock = card.getByRole("radiogroup", { name: "Scale-down policy: preset or locked" });
    await lock.getByRole("radio", { name: "Locked" }).click();
    await expect(card).toContainText("the platform default cannot be locked");
    await choose(page, "nodepool-0-scale-down-policy", "fewest-pods");
    await expect(policy(page).getByTestId("nodepool-0-scale-down-policy-note")).toHaveText(/fewest workload pods/);

    await page.getByRole("button", { name: /review & create/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
    await expect.poll(() => writes.length).toBe(1);
    const day1 = writes[0].spec.day1;
    expect((day1.values?.nodepools as Record<string, unknown>[])[0].scale_down_policy).toBe("fewest-pods");
    expect(day1.locked_paths).toContain("nodepools[0].scale_down_policy");
  });
});

// ── Edit cluster ─────────────────────────────────────────────────────────────

const NAME = "ocp4-prod-lark-site1";
const YAML = `owner:
  merkaz: "1"
mastertag: 4.16.27-x86_64
nodepool:
- infraEnvName: ${DELL}
  replicas: 2
  labels:
    allowDeletion: false
- name: storage
  infraEnvName: dell-r760-site1-64c-512gb-20tb
  annotations:
    ${KEY}: least-requested  # quiet nodes first
  replicas: 1
`;
const pool = (infra: string, name: string | null) => ({
  name, infra_env_name: infra, additional_infra_env_names: [], replicas: 1, allow_deletion: false, configs: [], node_labels: {}, tuning_config: null,
});
const DETAIL: ClusterDetail = {
  name: NAME,
  site: SITE,
  mce: MCE,
  yaml: YAML,
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${NAME}.yaml`,
  last_commit_id: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
  metadata: { spec_name: null, spec_version: null, created_by: "alice", created_at: null, site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [] },
  values: {
    owner: { merkaz: "1", anaf: "2", mador: "3" },
    mastertag: "4.16.27-x86_64",
    platform: "agent",
    nodepools: [pool(DELL, null), pool("dell-r760-site1-64c-512gb-20tb", "storage")],
    network: { vlan_id: null, dhcp_network: null, segment: null },
    cluster_name: null,
    automation_keys: [],
  },
  hosted_cluster: { cluster_name: "prod-lark-site1", name: "openshift-prod-lark-site1", namespace: "hcp-prod-lark-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "lark", sequence: null, problems: [] },
  mce_default_mastertag: "4.16.27-x86_64",
  problems: [],
  segments_manager: null,
};

async function openEdit(page: Page, on: boolean, yaml = YAML) {
  await base(page, on);
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r) => json(r, {}, 501));
  await page.route(`**/api/day1/clusters/${NAME}?**`, (r) =>
    r.request().method() === "PATCH" ? json(r, mockMR({ iid: 65, title: `[Wingman/Day1] Modify cluster ${NAME}` })) : json(r, { ...DETAIL, yaml })
  );
  await page.route(`**/api/day1/clusters/${NAME}/drift?**`, (r) => json(r, { cluster: NAME, site: SITE, mce: MCE, state: "not_linked", is_drifted: false, spec_name: null, spec_version: null, current_spec_version: null, value_drift: [], addon_drift: [], version_differences: [], error: null, update: null }));
  await page.route(`**/api/day2/clusters/${NAME}/**`, (r) => json(r, r.request().url().includes("/history") ? [] : { cluster: NAME, mce: MCE, id: `hosted:${SITE}:prod:${MCE}:${NAME}`, kind: "hosted", site: SITE, env: "prod", ocp_version: "4.16.27", installed: [], excluded: [], warnings: [], argocd_note: "" }));
  await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);
  await page.getByRole("button", { name: "Edit" }).click();
}

test.describe("A nodepool's scale-down policy in Edit cluster", () => {
  test("is set per nodepool in the file's text, every other line kept", async ({ page }) => {
    await openEdit(page, true);
    const panel = page.getByTestId("edit-policies");
    await expect(panel).toContainText("rolls no node");
    await expect(panel.getByTestId("edit-policy-1-select-trigger")).toHaveText(/least-requested/);

    await choose(page, "edit-policy-0-select", "fewest-pods");
    const added = YAML.replace("    allowDeletion: false\n", `    allowDeletion: false\n  annotations:\n    ${KEY}: fewest-pods\n`);
    await expect(page.getByLabel("Cluster file")).toHaveValue(added);
    await choose(page, "edit-policy-1-select", "Platform default");
    const edited = added.replace(`  annotations:\n    ${KEY}: least-requested  # quiet nodes first\n`, "");
    await expect(page.getByLabel("Cluster file")).toHaveValue(edited);

    const patch = page.waitForRequest((req: Request) => req.method() === "PATCH");
    await page.getByRole("button", { name: /review & submit/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
    expect((await patch).postDataJSON().updated_yaml).toBe(edited);
  });

  test("shows a file's own policy even when the template does not write one, and leaves a flow mapping to the person", async ({ page }) => {
    await openEdit(page, false, YAML.replace(`  annotations:\n    ${KEY}: least-requested  # quiet nodes first\n`, `  annotations: {${KEY}: least-requested}\n`));
    await choose(page, "edit-policy-1-select", "fewest-pods");
    await expect(page.getByTestId("edit-policies-refused")).toContainText("change its redbull.io/scale-down-policy in the file below");
    await expect(page.getByLabel("Cluster file")).toHaveValue(/annotations: \{redbull.io\/scale-down-policy: least-requested\}/);
  });

  test("is the file alone when the template does not write it and no nodepool sets one", async ({ page }) => {
    await openEdit(page, false, YAML.replace(`  annotations:\n    ${KEY}: least-requested  # quiet nodes first\n`, ""));
    await expect(page.getByLabel("Cluster file")).toBeVisible();
    await expect(page.getByTestId("edit-policies")).toHaveCount(0);
  });
});
