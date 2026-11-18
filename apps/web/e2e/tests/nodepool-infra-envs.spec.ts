/**
 * A nodepool that draws Agents from several InfraEnvs (ADR-0064, mocked).
 * Day1 offers `nodepools[].additional_infra_envs` in the template schema only
 * with `DAY1_MULTI_INFRAENV_NODEPOOLS` on, so the schema is the switch:
 * - the create form's "Also draws from", from the MCE's InfraEnvs, sent with
 *   the nodepool and asked of placement as one node type (`a,b:n`);
 * - the flavor editor's preset, typed;
 * - Edit cluster's InfraEnvs per nodepool, which edits the file's text and
 *   leaves a Replace NodePool's as they are;
 * - the cluster page's nodepools, which name the others.
 * Off, none of it shows. Invented names only.
 */

import { test, expect, type Page, type Route, type Request } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis, mockMachineConfigs, mockMR, placementAnswer } from "../fixtures/api-handlers";
import { ClusterNewPage } from "../pages/cluster-new.page";
import type { ClusterDetail, ClusterPreview, ClusterSpec, CreateClusterRequest, Mce, SpecEntry, TemplateField } from "../../types";

const DELL = "dell-r660-site1-128c-1024gb-5tb";
const DELL7 = "dell-r760-site1-64c-512gb-20tb";
const HP = "hp-gen11-site1-64c";
const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const STATIC = [{ name: "workers-chrony-configuration" }];

const nodepoolFields = (on: boolean): TemplateField[] => [
  { name: "infra_env", type: "string", required: true, example: DELL },
  ...(on ? [{ name: "additional_infra_envs", type: "list" as const, required: false, default: [] }] : []),
  { name: "replicas", type: "string", required: false, default: 2 },
  { name: "configs", type: "list", required: false, default: [], fields: [{ name: "name", type: "string", required: true }] },
];
const schema = (on: boolean): TemplateField[] => [
  { name: "owner_merkaz", type: "string", required: true, example: "1234" },
  { name: "owner_anaf", type: "string", required: true, example: "56" },
  { name: "owner_mador", type: "string", required: true, example: "7" },
  { name: "nodepools", type: "list", required: true, fields: nodepoolFields(on) },
];

const RCS: SpecEntry = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name: "rcs", description: "The rcs flavor", version: "1.0.0", labels: {} },
  spec: {
    day1: { variables: [], structure: { nodepools: [{}] }, locked_paths: [], template: "# template", values: { nodepools: [{ configs: STATIC }] } },
    day2: { addons: [] },
  },
  load_error: null,
  load_problems: [],
  warnings: [],
};

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
  await page.route("**/api/day1/mces/*/infraenvs", (r) => json(r, [DELL, DELL7, HP]));
  await page.route("**/api/day1/machine-configs", (r) => json(r, mockMachineConfigs));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
  await page.route("**/api/day2/addons", (r) => json(r, []));
}

// ── The create form ──────────────────────────────────────────────────────────

interface Calls {
  previews: CreateClusterRequest[];
  needs: string[][];
}

async function openCreate(page: Page, on: boolean): Promise<{ form: ClusterNewPage; calls: Calls }> {
  const calls: Calls = { previews: [], needs: [] };
  await base(page, on);
  await page.route("**/api/day1/specs", (r) => json(r, [RCS]));
  await page.route("**/api/day1/sites", (r) => json(r, [SITE]));
  await page.route("**/api/day1/placement**", (r) => {
    const query = new URL(r.request().url()).searchParams;
    calls.needs.push(query.getAll("need"));
    return json(r, placementAnswer(query));
  });
  await page.route("**/api/day1/clusters/name-suggestion**", (r) =>
    json(r, { name: "ocp4-prod-rcs-site1-a", env: "prod", short_name: "rcs", sequence: "a", problems: [] })
  );
  await page.route("**/api/day1/clusters/preview", (r) => {
    calls.previews.push(r.request().postDataJSON());
    return json(r, PREVIEW);
  });
  const form = new ClusterNewPage(page);
  await form.goto();
  await form.chooseSpec("rcs");
  await form.place({ site: SITE, env: "prod", version: "4.16.27" });
  await expect(form.nameInput).toHaveValue("ocp4-prod-rcs-site1-a");
  for (const owner of ["1234", "56", "7"]) await form.templateInput(owner).fill(owner);
  await page.getByTestId("infra-env-select-nodepools[0].infra_env").click();
  await form.option(DELL).click();
  return { form, calls };
}

const drawsFrom = (page: Page, index = 0) => page.getByTestId(`nodepool-${index}-infra-envs`);

test.describe("A nodepool's other InfraEnvs on the create form", () => {
  test("are picked from the MCE's InfraEnvs, sent with the nodepool, and placed as one node type", async ({ page }) => {
    const { form, calls } = await openCreate(page, true);
    const field = page.locator('[data-field-path="nodepools[0].additional_infra_envs"]');
    await expect(field).toContainText("Also draws from");
    await expect(drawsFrom(page)).toContainText(`Beside ${DELL}, which names the NodePool`);

    // The nodepool's own InfraEnv is not offered again
    await drawsFrom(page).getByTestId("nodepool-0-infra-envs-add").click();
    await expect(form.option(DELL)).toHaveCount(0);
    await form.option(HP).click();
    await expect(drawsFrom(page).getByTestId(`nodepool-0-infra-envs-${HP}`)).toBeVisible();
    await expect.poll(() => calls.needs.at(-1)).toEqual([`${DELL},${HP}:2`]);

    // Removed and added back: the chip's button says what it does
    await drawsFrom(page).getByRole("button", { name: `Stop drawing from ${HP}` }).click();
    await expect(drawsFrom(page)).toContainText("Only its own InfraEnv.");
    await expect.poll(() => calls.needs.at(-1)).toEqual([`${DELL}:2`]);
    await drawsFrom(page).getByTestId("nodepool-0-infra-envs-add").click();
    await form.option(DELL7).click();

    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    const pools = calls.previews[0].variables.nodepools as Record<string, unknown>[];
    expect([pools[0].infra_env, pools[0].additional_infra_envs]).toEqual([DELL, [DELL7]]);
  });

  test("are not offered when day1 does not (the setting off, or a template that does not read them)", async ({ page }) => {
    const { form, calls } = await openCreate(page, false);
    await expect(page.locator('[data-field-path="nodepools[0].additional_infra_envs"]')).toHaveCount(0);
    await expect(page.getByText("Also draws from")).toHaveCount(0);
    await form.review();
    await expect(form.reviewDialog).toBeVisible();
    expect(calls.previews[0].variables.nodepools as Record<string, unknown>[]).toEqual([
      expect.not.objectContaining({ additional_infra_envs: expect.anything() }),
    ]);
  });
});

// ── The flavor editor ────────────────────────────────────────────────────────

test.describe("A nodepool's other InfraEnvs in the flavor editor", () => {
  test("are a typed preset, checked as typed and saved with the nodepool", async ({ page }) => {
    const writes: ClusterSpec[] = [];
    await base(page, true);
    await page.route("**/api/day1/specs/template", (r) => json(r, "# cluster-template.j2"));
    await page.route("**/api/day1/specs", (r) => {
      if (r.request().method() !== "POST") return json(r, []);
      writes.push(r.request().postDataJSON());
      return json(r, mockMR({ repo: "specs", iid: 64 }), 201);
    });
    await go(page, "/specs/new");
    await expect(page.getByRole("heading", { name: "New Flavor" })).toBeVisible();
    await page.getByTestId("spec-name-input").fill("agent-wide");
    await page.getByTestId("nodepool-0-configs").getByRole("combobox", { name: /entry 1 hardware type$/ }).click();
    await page.getByRole("option").filter({ has: page.getByText("dell", { exact: true }) }).click();
    await page.getByTestId("nodepool-0").getByRole("button", { name: /Other inputs/ }).click();

    const preset = drawsFrom(page);
    await expect(preset).toContainText("Only its own InfraEnv.");
    const typed = preset.getByTestId("nodepool-0-infra-envs-type");
    await typed.fill("Not An InfraEnv");
    await expect(preset).toContainText("An InfraEnv name is lowercase letters, digits and '-'");
    await typed.fill(HP);
    await typed.press("Enter");
    await expect(preset.getByTestId(`nodepool-0-infra-envs-${HP}`)).toBeVisible();
    await expect(typed).toHaveValue("");

    await page.getByRole("button", { name: /review & create/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
    await expect.poll(() => writes.length).toBe(1);
    const pool = (writes[0].spec.day1.values?.nodepools as Record<string, unknown>[])[0];
    expect(pool.additional_infra_envs).toEqual([HP]);
  });
});

// ── Edit cluster and the cluster page ────────────────────────────────────────

const NAME = "ocp4-prod-lark-site1";
const YAML = `owner:
  merkaz: "1"
mastertag: 4.16.27-x86_64
nodepool:
- infraEnvName: ${DELL}
  replicas: 2
- infraEnvName: ${DELL7}
  additionalInfraEnvNames: [${HP}]
  upgradeType: Replace
  replicas: 1
`;
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
    nodepools: [
      { name: null, infra_env_name: DELL, additional_infra_env_names: [], replicas: 2, allow_deletion: false, configs: [], node_labels: {}, tuning_config: null },
      { name: null, infra_env_name: DELL7, additional_infra_env_names: [HP], replicas: 1, allow_deletion: false, configs: [], node_labels: {}, tuning_config: null },
    ],
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

async function openCluster(page: Page, on: boolean) {
  await base(page, on);
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r) => json(r, {}, 501));
  await page.route(`**/api/day1/clusters/${NAME}?**`, (r) =>
    r.request().method() === "PATCH" ? json(r, mockMR({ iid: 64, title: `[Wingman/Day1] Modify cluster ${NAME}` })) : json(r, DETAIL)
  );
  await page.route(`**/api/day1/clusters/${NAME}/drift?**`, (r) => json(r, { cluster: NAME, site: SITE, mce: MCE, state: "not_linked", is_drifted: false, spec_name: null, spec_version: null, current_spec_version: null, value_drift: [], addon_drift: [], version_differences: [], error: null, update: null }));
  await page.route(`**/api/day2/clusters/${NAME}/**`, (r) => json(r, r.request().url().includes("/history") ? [] : { cluster: NAME, mce: MCE, id: `hosted:${SITE}:prod:${MCE}:${NAME}`, kind: "hosted", site: SITE, env: "prod", ocp_version: "4.16.27", installed: [], excluded: [], warnings: [], argocd_note: "" }));
  await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);
}

test.describe("A nodepool's other InfraEnvs on the cluster page", () => {
  test("are named beside its own on the Overview", async ({ page }) => {
    await openCluster(page, false);
    await expect(page.getByTestId("nodepool-row-1-infra-envs")).toHaveText(`also draws from ${HP}`);
    await expect(page.getByTestId("nodepool-row-0-infra-envs")).toHaveCount(0);
  });

  test("Edit cluster picks them per nodepool, edits the file's text, and leaves a Replace NodePool's", async ({ page }) => {
    await openCluster(page, true);
    await page.getByRole("button", { name: "Edit" }).click();
    const panel = page.getByTestId("edit-infra-envs");
    await expect(panel).toContainText("InfraEnvs per nodepool");
    await expect(panel.getByTestId("edit-nodepool-0")).toContainText("its own InfraEnv: names the NodePool");

    await panel.getByTestId("edit-nodepool-0-infra-envs-add").click();
    await page.getByRole("option", { name: HP }).click();
    await expect(page.getByLabel("Cluster file")).toHaveValue(
      YAML.replace(`- infraEnvName: ${DELL}\n`, `- infraEnvName: ${DELL}\n  additionalInfraEnvNames: ["${HP}"]\n`)
    );
    // A Replace NodePool would roll every node: shown, not editable
    const replace = panel.getByTestId("edit-nodepool-1-infra-envs");
    await expect(replace).toContainText("upgradeType Replace");
    await expect(replace.getByRole("button", { name: `Stop drawing from ${HP}` })).toHaveCount(0);

    const patch = page.waitForRequest((req: Request) => req.method() === "PATCH");
    await page.getByRole("button", { name: /review & submit/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
    expect((await patch).postDataJSON().updated_yaml).toContain(`additionalInfraEnvNames: ["${HP}"]\n  replicas: 2`);
  });

  test("Edit cluster is the file alone when day1 does not offer them", async ({ page }) => {
    await openCluster(page, false);
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel("Cluster file")).toBeVisible();
    await expect(page.getByTestId("edit-infra-envs")).toHaveCount(0);
  });
});
