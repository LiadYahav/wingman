/**
 * Creating a cluster through the platform's provision-cluster workflow
 * (docs/notes/2026-11-12-provision-cluster-workflow-api.md, ADR-0042). With
 * the mode on, Create starts the workflow and the page shows its run: the
 * workflow's own phase, its merge request once opened, and its error. With it
 * off, nothing changes. Every API is mocked.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
import { ClusterNewPage } from "../pages/cluster-new.page";
import type { ClusterPreview, Mce, ProvisionRun, SpecEntry, TemplateField } from "../../types";

const NAME = "ocp4-prod-rcs-site1-a";
const WORKFLOW_ID = `provision-cluster-${NAME}`;

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

const MCES: Mce[] = [
  {
    name: "ocp4-prod-mce-site1-a", site: "site1", env: "prod", letter: "a", follows_convention: true, naming_problems: [],
    default_mastertag: "4.16.27-x86_64", hub_version: "4.16.27-x86_64", cluster_count: 4, stray_files: [], problems: [],
  },
];

const PREVIEW: ClusterPreview = {
  yaml: '# specName: "rcs"\nmastertag: 4.16.27-x86_64\n',
  path: `sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/${NAME}.yaml`,
};

const run = (overrides: Partial<ProvisionRun> = {}): ProvisionRun => ({
  workflow_id: WORKFLOW_ID,
  cluster: NAME,
  status: "running",
  phase: null,
  error: null,
  merge_request_url: null,
  merge_request_state: null,
  ...overrides,
});

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: status >= 400 ? "application/problem+json" : "application/json",
    body: JSON.stringify(body),
  });

const problem = (status: number, code: string, detail: string, details: Record<string, unknown> = {}) => ({
  type: `/problems/${code.toLowerCase().replace(/_/g, "-")}`, title: code, status, code, detail,
  instance: "/api/day1/clusters", request_id: "req_1", details,
});

/** The create form's reads, with Create in `mode`. */
async function setup(page: Page, mode: "merge-request" | "workflow") {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters/provisioner", (r) => json(r, { mode }));
  await page.route("**/api/day1/specs", (r) => json(r, [RCS]));
  await page.route("**/api/day1/specs/template/schema", (r) => json(r, SCHEMA));
  await page.route("**/api/day1/sites", (r) => json(r, ["site1"]));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
  await page.route("**/api/day1/mces/*/openshift-versions", (r) =>
    json(r, { mce: "ocp4-prod-mce-site1-a", versions: ["4.16.27"], problems: [] })
  );
  await page.route("**/api/day1/mces/*/infraenvs", (r) =>
    json(r, problem(501, "FEATURE_DISABLED", "Live cluster status is disabled"), 501)
  );
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/clusters/name-suggestion**", (r) =>
    json(r, { name: NAME, env: "prod", short_name: "rcs", sequence: "a", problems: [] })
  );
  await page.route("**/api/day1/clusters/preview", (r) => json(r, PREVIEW));
}

/** Fill the form, open Review, and return the dialog. */
async function review(page: Page) {
  const form = new ClusterNewPage(page);
  await form.goto();
  await form.chooseSpec("rcs");
  await form.selectSite("site1");
  await form.selectMce("ocp4-prod-mce-site1-a");
  await expect(form.nameInput).toHaveValue(NAME);
  await form.templateInput("1234").fill("1234");
  await form.templateInput("56").fill("56");
  await form.templateInput("7").fill("7");
  await page.getByPlaceholder("e.g. dell-r660-site1-128c-1024gb-5tb").fill("dell-r660-site1-128c-1024gb-5tb");
  await form.review();
  await expect(form.reviewDialog).toBeVisible();
  return form.reviewDialog;
}

test.describe("Create through the provision-cluster workflow", () => {
  test("Create starts the workflow and the page follows its run to the merge request", async ({ page }) => {
    await setup(page, "workflow");
    const creates: unknown[] = [];
    await page.route("**/api/day1/clusters", (r) => {
      if (r.request().method() !== "POST") return r.fallback();
      creates.push(r.request().postDataJSON());
      return json(r, run(), 202);
    });
    // The run moves on each read: its phase is the workflow's own word, the MR appears once opened
    const reads = [
      run({ phase: "allocating-segment" }),
      run({
        phase: "awaiting-merge",
        merge_request_url: "https://gitlab.example/gitops-day1/platform-config/-/merge_requests/42",
        merge_request_state: "opened",
      }),
    ];
    await page.route(`**/api/day1/clusters/${NAME}/provision-run`, (r) => json(r, reads.shift() ?? reads.at(-1) ?? run()));

    const dialog = await review(page);
    await expect(dialog).toContainText("This is the file the provision-cluster workflow receives");
    await dialog.getByRole("button", { name: "Confirm — Start provision-cluster" }).click();

    const panel = page.getByTestId("provision-run");
    await expect(panel).toBeVisible();
    await expect(panel).toContainText(`Provisioning ${NAME}`);
    expect(creates).toHaveLength(1);
    await expect(page.getByTestId("provision-run-phase")).toHaveText("Allocating segment");
    await expect(page.getByTestId("provision-run-merge-request")).toHaveCount(0);
    await expect(panel).toContainText(WORKFLOW_ID);

    // Read again while it runs
    await expect(page.getByTestId("provision-run-phase")).toHaveText("Awaiting merge", { timeout: 15_000 });
    const link = page.getByTestId("provision-run-merge-request");
    await expect(link).toHaveAttribute("href", "https://gitlab.example/gitops-day1/platform-config/-/merge_requests/42");
    await expect(link).toContainText("Review it (opened)");
  });

  test("a failed run shows the workflow's own error", async ({ page }) => {
    await setup(page, "workflow");
    await page.route("**/api/day1/clusters", (r) =>
      r.request().method() === "POST" ? json(r, run(), 202) : r.fallback()
    );
    await page.route(`**/api/day1/clusters/${NAME}/provision-run`, (r) =>
      json(
        r,
        run({
          status: "failed",
          phase: "inspecting-target",
          error: "ClusterAlreadyProvisionedError: the cluster's file is already on main",
        })
      )
    );
    const dialog = await review(page);
    await dialog.getByRole("button", { name: "Confirm — Start provision-cluster" }).click();
    await expect(page.getByTestId("provision-run")).toContainText(`Provisioning failed ${NAME}`);
    await expect(page.getByTestId("provision-run-error")).toHaveText(
      "ClusterAlreadyProvisionedError: the cluster's file is already on main"
    );
    await expect(page.getByTestId("provision-run-phase")).toHaveText("Inspecting target");
  });

  test("a run already going and a lost answer are said plainly, and nothing is shown as started", async ({ page }) => {
    await setup(page, "workflow");
    let call = 0;
    await page.route("**/api/day1/clusters", (r) => {
      if (r.request().method() !== "POST") return r.fallback();
      call += 1;
      return call === 1
        ? json(r, problem(409, "ALREADY_EXISTS", `a provision run for prod-rcs-site1-a is already going`), 409)
        : json(r, problem(504, "AMBIGUOUS_WRITE", "the provision of prod-rcs-site1-a was sent but no answer came back: it may have started"), 504);
    });
    let dialog = await review(page);
    await dialog.getByRole("button", { name: "Confirm — Start provision-cluster" }).click();
    await expect(page.getByText(/already going/).first()).toBeVisible();
    await expect(page.getByTestId("provision-run")).toHaveCount(0);

    dialog = await review(page);
    await dialog.getByRole("button", { name: "Confirm — Start provision-cluster" }).click();
    await expect(page.getByText(/may have started/).first()).toBeVisible();
    await expect(page.getByTestId("provision-run")).toHaveCount(0);
  });

  test("with the workflow off, Create still opens Wingman's merge request", async ({ page }) => {
    await setup(page, "merge-request");
    const dialog = await review(page);
    await expect(dialog).toContainText("This is the file the merge request adds");
    await expect(dialog.getByRole("button", { name: "Confirm — Create Cluster MR" })).toBeVisible();
  });
});
