/**
 * Seeds & KV Clusters: each zone's fill order and Create KV cluster (mocked;
 * ADR-0069). A seed's KV clusters are listed oldest first by id letter, each
 * Full, Filling or Next with its workers against 40; a zone with no Next is
 * warned, with a Create pre-filled with the standby size. The dialog is
 * day1's draft, read again as a choice changes; Create starts
 * provision-cluster with the name the draft showed and shows its run, then
 * what follows the merge.
 */

import { test, expect, type Page, type Request, type Route } from "@playwright/test";
import { go, injectAdminAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import { KV_CLUSTER, MCES, SEED, UPGRADES_OFF } from "../fixtures/overview";
import type { ClusterStatus, KvDraft, ProvisionRun } from "@/types";

const NEXT = "ocp4-prod-kv-site1-az1-d";

const kv = (id: string, workers: number, zoneProblems: string[] = []): ClusterStatus => ({
  ...KV_CLUSTER,
  name: `ocp4-prod-kv-site1-az1-${id}`,
  path: `sites/site1/mces/${SEED}/hostedClusters/ocp4-prod-kv-site1-az1-${id}.yaml`,
  naming: { ...KV_CLUSTER.naming, sequence: id },
  kv: { workers, max_workers: 40, zone_problems: zoneProblems },
});

/** -a is full, -b fills, -c names no zone: no KV cluster is next in line in az1. */
const CLUSTERS = [...UPGRADES_OFF, kv("b", 12), kv("a", 40), kv("c", 3, ["nodepool[0] (r760-mtl-az1) names no zone"])];

const YAML = (infraEnv: string, workers: number) =>
  `owner:\n  merkaz: "1000"\n\nmastertag: 4.18.56\n\nnodepool:\n  - infraEnvName: ${infraEnv}\n    replicas: ${workers}\n`;

function draft(query: URLSearchParams): KvDraft {
  const workers = Number(query.get("workers") ?? 3);
  const infraEnv = query.get("infra_env");
  return {
    seed: SEED, site: "site1", name: NEXT, zone: "az1", zones: ["az1"],
    mastertag: query.get("mastertag") ?? "4.18.56", versions: ["4.18.56", "4.17.58"],
    infra_env: infraEnv, infra_envs: ["c200-mtl-az1", "r760-mtl-az1"], infra_envs_from: "hub",
    workers, default_workers: 3, max_workers: 40, standby_workers: [1, 5],
    model: { name: "ocp4-prod-kv-site1-az1-b", site: "site1", seed: SEED, configs: ["workers-chrony-configuration"], tuning_config: null },
    owner: { merkaz: "1000", anaf: "10", mador: "1" },
    path: `sites/site1/mces/${SEED}/hostedClusters/${NEXT}.yaml`,
    yaml: infraEnv ? YAML(infraEnv, workers) : null,
    problems: infraEnv ? [] : ["choose the InfraEnv: c200-mtl-az1, r760-mtl-az1"],
  };
}

const RUN: ProvisionRun = {
  workflow_id: `provision-cluster-${NEXT}`, cluster: NEXT, status: "running", phase: "awaiting-merge", error: null,
  merge_request_url: "https://gitlab.example/gitops-day1/platform-config/-/merge_requests/7", merge_request_state: "open",
};

async function setUp(page: Page) {
  const drafts: URLSearchParams[] = [];
  const creates: unknown[] = [];
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters", (route) => json(route, CLUSTERS));
  await page.route("**/api/day1/mces", (route) => json(route, MCES));
  await page.route(`**/api/day1/seeds/${SEED}/kv-cluster-draft**`, (route: Route) => {
    const query = new URL(route.request().url()).searchParams;
    drafts.push(query);
    return json(route, draft(query));
  });
  await page.route(`**/api/day1/seeds/${SEED}/kv-clusters`, (route: Route) => {
    creates.push(route.request().postDataJSON());
    return json(route, RUN, 202);
  });
  await page.route(`**/api/day1/clusters/${NEXT}/provision-run`, (route) => json(route, RUN));
  return { drafts, creates };
}

const seed = (page: Page) => page.locator(`[data-testid="seed"][data-seed="${SEED}"]`);
const dialog = (page: Page) => page.getByTestId("kv-cluster-dialog");

/** Pick an option of a Combobox by its label. */
async function choose(page: Page, combobox: ReturnType<Page["getByRole"]>, option: string) {
  await combobox.click();
  await page.getByRole("option").filter({ has: page.getByText(option, { exact: true }) }).click();
  await expect(page.getByRole("option")).toHaveCount(0);
}

test.describe("A seed's KV clusters in their fill order", () => {
  test("oldest first by id letter, each Full, Filling or Next with its workers, and one that misses its zone apart", async ({ page }) => {
    await setUp(page);
    await go(page, "/seeds");

    const rows = seed(page).getByTestId("kv-cluster");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toHaveAttribute("data-cluster", "ocp4-prod-kv-site1-az1-a");
    await expect(rows.nth(0).getByTestId("kv-fill")).toHaveAttribute("data-state", "full");
    await expect(rows.nth(0).getByTestId("kv-fill")).toContainText("1st");
    await expect(rows.nth(0).getByTestId("kv-workers")).toContainText("40/40");
    await expect(rows.nth(1).getByTestId("kv-fill")).toHaveAttribute("data-state", "filling");
    await expect(rows.nth(1).getByTestId("kv-fill")).toContainText("2nd");
    await expect(rows.nth(1).getByRole("meter", { name: "Workers" })).toHaveAttribute("aria-valuenow", "12");
    // -c names no zone: listed after the order, with no place in it
    await expect(rows.nth(2)).toHaveAttribute("data-cluster", "ocp4-prod-kv-site1-az1-c");
    await expect(rows.nth(2).getByTestId("kv-fill")).toHaveCount(0);
    await expect(rows.nth(2).getByTestId("kv-zone-problems")).toBeVisible();

    await expect(seed(page).getByTestId("kv-no-standby")).toHaveText(
      /When ocp4-prod-kv-site1-az1-b fills up, create-vm has nowhere to put az1's VMs\./
    );
  });

  test("the warning's Create opens the draft at the standby size, in the zone", async ({ page }) => {
    const { drafts } = await setUp(page);
    await go(page, "/seeds");

    await seed(page).getByTestId("kv-no-standby-create").click();
    await expect(dialog(page).getByTestId("kv-draft-name")).toHaveText(NEXT);
    expect(drafts.at(-1)?.get("workers")).toBe("3");
    expect(drafts.at(-1)?.get("zone")).toBe("az1");
    await expect(dialog(page).getByTestId("kv-draft-workers")).toHaveValue("3");
  });
});

test.describe("Create KV cluster", () => {
  test("the draft is the whole file; a choice reads it again; Create starts the run and says what follows", async ({ page }) => {
    const { drafts, creates } = await setUp(page);
    await go(page, "/seeds");

    await seed(page).getByTestId("seed-create-kv").click();
    const box = dialog(page);
    await expect(box.getByTestId("kv-draft-name")).toHaveText(NEXT);
    await expect(box.getByTestId("kv-draft-zone")).toHaveText("az1");
    await expect(box.getByTestId("kv-draft-model")).toContainText("ocp4-prod-kv-site1-az1-b");
    // Two bare-metal pools: a choice, and Create waits for it
    await expect(box.getByText("choose the InfraEnv: c200-mtl-az1, r760-mtl-az1")).toBeVisible();
    await expect(box.getByTestId("kv-create")).toBeDisabled();

    await choose(page, box.getByRole("combobox", { name: "InfraEnv" }), "r760-mtl-az1");
    await box.getByTestId("kv-draft-workers").fill("5");
    await expect(box.getByTestId("kv-draft-yaml")).toContainText("infraEnvName: r760-mtl-az1");
    await expect(box.getByTestId("kv-draft-yaml")).toContainText("replicas: 5");
    expect(drafts.at(-1)?.get("infra_env")).toBe("r760-mtl-az1");

    const sent = page.waitForRequest((req: Request) => req.method() === "POST" && req.url().includes("/kv-clusters"));
    await box.getByTestId("kv-create").click();
    await sent;
    expect(creates).toEqual([
      { name: NEXT, zone: "az1", infra_env: "r760-mtl-az1", mastertag: "4.18.56", workers: 5, owner: null },
    ]);

    await expect(box.getByTestId("provision-run")).toBeVisible();
    await expect(box.getByTestId("provision-run-phase")).toHaveText("Awaiting merge");
    await expect(box.getByTestId("provision-run-merge-request")).toHaveAttribute("href", RUN.merge_request_url!);
    await expect(box.getByTestId("kv-after-addons")).toHaveAttribute("href", `/clusters/${NEXT}/addons`);
    await expect(box.getByText("HighNodeUtilization")).toBeVisible();
    await expect(box.getByTestId("kv-create")).toHaveCount(0);
  });

  test("a refused create shows day1's words and sends nothing more", async ({ page }) => {
    const { creates } = await setUp(page);
    await page.route(`**/api/day1/seeds/${SEED}/kv-clusters`, (route: Route) => {
      creates.push(route.request().postDataJSON());
      return json(route, {
        type: "/problems/revision-conflict", title: "Conflict", status: 409, code: "REVISION_CONFLICT",
        detail: `the next free KV cluster name on ${SEED} is now ocp4-prod-kv-site1-az1-e, not ${NEXT}; reload`,
      }, 409);
    });
    await go(page, "/seeds");

    await seed(page).getByTestId("seed-create-kv").click();
    await choose(page, dialog(page).getByRole("combobox", { name: "InfraEnv" }), "c200-mtl-az1");
    await dialog(page).getByTestId("kv-create").click();
    await expect(dialog(page).getByTestId("kv-create-error")).toContainText("is now ocp4-prod-kv-site1-az1-e");
    expect(creates).toHaveLength(1);
  });
});
