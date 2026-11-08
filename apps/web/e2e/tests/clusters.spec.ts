/**
 * The cluster list and detail pages on the rewritten day1 service (mocked):
 * unlinked clusters have `spec_name: null`, off-convention and unparsable files
 * are flagged (never hidden), drift has four states and unknown is never shown
 * as in sync, live status off (501 FEATURE_DISABLED) is "status is off", and
 * every edit or delete carries the `last_commit_id` it started from.
 */

import { test, expect, type Page, type Route, type Request } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, mockDashboardApis, mockMR } from "../fixtures/api-handlers";
import type { ClusterDetail, ClusterDrift, ClusterStatus, DestinationCharts, DriftSummaryItem, InstalledChart } from "../../types";

const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";

function listItem(name: string, overrides: Partial<ClusterStatus> = {}): ClusterStatus {
  return {
    name,
    site: SITE,
    mce: MCE,
    phase: "Unknown",
    spec_name: "agent-standard",
    spec_version: "1.0.0",
    created_by: "alice",
    created_at: "2026-11-07T10:00:00+00:00",
    mastertag: "4.16.27-x86_64",
    path: `sites/${SITE}/mces/${MCE}/hostedClusters/${name}.yaml`,
    hosted_cluster: { cluster_name: name.replace(/^ocp4-/, ""), name: `openshift-${name.replace(/^ocp4-/, "")}`, namespace: `hcp-${name.replace(/^ocp4-/, "")}` },
    naming: { follows_convention: true, env: "prod", short_name: "x", sequence: null, problems: [] },
    owner: { merkaz: "1234", anaf: "56", mador: "7" },
    problems: [],
    ...overrides,
  };
}

const CLUSTERS: ClusterStatus[] = [
  listItem("ocp4-prod-alpha-site1"),
  listItem("ocp4-prod-bravo-site1"),
  listItem("ocp4-prod-charlie-site1"),
  listItem("ocp4-upgrade-demo", {
    spec_name: null, spec_version: null,
    naming: { follows_convention: false, env: null, short_name: null, sequence: null, problems: ["cluster 'ocp4-upgrade-demo' does not follow ocp4-<env>-<name>-site1[-<seq>]"] },
  }),
  listItem("ocp4-prod-broken-site1", { spec_name: null, spec_version: null, mastertag: null, problems: ["the file is not valid YAML: line 3"] }),
];

const DRIFT_SUMMARY: DriftSummaryItem[] = [
  { name: "ocp4-prod-alpha-site1", site: SITE, mce: MCE, state: "in_sync", is_drifted: false, error: null },
  { name: "ocp4-prod-bravo-site1", site: SITE, mce: MCE, state: "drifted", is_drifted: true, error: null },
  { name: "ocp4-prod-charlie-site1", site: SITE, mce: MCE, state: "unknown", is_drifted: null, error: "day2 did not answer" },
  { name: "ocp4-upgrade-demo", site: SITE, mce: "ocp4-mce-workflow-test", state: "not_linked", is_drifted: false, error: null },
  { name: "ocp4-prod-broken-site1", site: SITE, mce: MCE, state: "not_linked", is_drifted: false, error: null },
];

const NAME = "ocp4-prod-herzi-site1";
const YAML = 'owner:\n  merkaz: "1"\nmastertag: 4.16.27-x86_64\nnodepool:\n  - infraEnvName: dell\n    replicas: 2\n';
const DETAIL: ClusterDetail = {
  name: NAME,
  site: SITE,
  mce: MCE,
  yaml: YAML,
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${NAME}.yaml`,
  last_commit_id: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
  metadata: {
    spec_name: "agent-standard", spec_version: "1.0.0", created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [],
    requested_addons: [{ team: "redbull", name: "cluster-roles", version: "main", override_values: { replicas: 2 } }],
  },
  values: {
    owner: { merkaz: "1", anaf: "2", mador: "3" },
    mastertag: "4.16.27-x86_64",
    platform: "agent",
    nodepools: [{ name: null, infra_env_name: "dell", replicas: 2, allow_deletion: false, configs: ["worker-chrony"], node_labels: {}, tuning_config: null }],
    network: { vlan_id: null, dhcp_network: null },
    cluster_name: null,
    automation_keys: [],
  },
  hosted_cluster: { cluster_name: "prod-herzi-site1", name: "openshift-prod-herzi-site1", namespace: "hcp-prod-herzi-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "herzi", sequence: null, problems: [] },
  mce_default_mastertag: "4.16.27-x86_64",
  problems: [],
};

/** The id day2 resolves the bare name to; writes use it. */
const HOSTED_ID = `hosted:${SITE}:prod:${MCE}:${NAME}`;
const CLUSTER_ROLES: InstalledChart = {
  team: "redbull",
  name: "cluster-roles",
  version: "release-1",
  override_values: { replicas: 1 },
  parse_errors: [],
  gitlab_url: "https://gitlab.example.com/sigs/redbull/-/tree/main/x",
  source: "cluster",
  path: `sites/${SITE}/prod/mces/${MCE}/${NAME}/cluster-roles`,
  override_path: `sites/${SITE}/prod/mces/${MCE}/${NAME}/cluster-roles/values.yaml`,
  last_commit_id: "5ca1ab1e5ca1ab1e5ca1ab1e5ca1ab1e5ca1ab1e",
  pinned: false,
  deploy: {
    app_name: `redbull-${NAME}-cluster-roles-deploy`, argo: MCE, namespace: "gitops-redbull",
    repo_url: "https://gitlab.example.com/helm-charts/cluster-roles.git", target_revision: "release-1", path: ".",
    release_name: "cluster-roles", destination: NAME, destination_namespace: "cluster-roles", sync_policy: {}, auto_sync: false,
  },
  warnings: [],
};

/** `GET /api/day2/clusters/{name}/addons?mce=`, what the detail page prefetches. */
function charts(installed: InstalledChart[] = []): DestinationCharts {
  return {
    cluster: NAME, mce: MCE, id: HOSTED_ID, kind: "hosted", site: SITE, env: "prod", ocp_version: "4.16.27",
    installed, excluded: [], warnings: [], argocd_note: "",
  };
}

function drift(overrides: Partial<ClusterDrift> = {}): ClusterDrift {
  return {
    cluster: NAME, site: SITE, mce: MCE, state: "in_sync", is_drifted: false,
    spec_name: "agent-standard", spec_version: "1.0.0", current_spec_version: "1.0.0",
    value_drift: [], addon_drift: [], version_differences: [], error: null, ...overrides,
  };
}

async function statusOff(page: Page) {
  await page.route("**/api/day1/clusters/bulk-status", (r: Route) =>
    fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled in this deployment (CLUSTER_STATUS_ENABLED=false).")
  );
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r: Route) =>
    fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled in this deployment (CLUSTER_STATUS_ENABLED=false).")
  );
}

test.describe("Cluster list", () => {
  test.beforeEach(async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(CLUSTERS) })
    );
    await page.route("**/api/day1/clusters/drift-summary", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(DRIFT_SUMMARY) })
    );
    await statusOff(page);
  });

  test("shows every drift state, and unknown is never in sync", async ({ page }) => {
    await go(page, "/clusters");

    const row = (name: string) => page.getByTestId(`cluster-row-${name}`);
    await expect(row("ocp4-prod-alpha-site1")).toContainText("In sync");
    await expect(row("ocp4-prod-bravo-site1")).toContainText("Drifted");
    await expect(row("ocp4-prod-charlie-site1")).toContainText("Unknown");
    await expect(row("ocp4-prod-charlie-site1")).not.toContainText("In sync");
    await expect(row("ocp4-upgrade-demo")).toContainText("Not linked");
  });

  test("filters by drift state with separate counts", async ({ page }) => {
    await go(page, "/clusters");

    await page.getByRole("button", { name: /^Unknown\s*1$/ }).click();
    await expect(page.getByTestId("cluster-row-ocp4-prod-charlie-site1")).toBeVisible();
    await expect(page.getByTestId("cluster-row-ocp4-prod-alpha-site1")).not.toBeVisible();
    await expect(page.getByRole("button", { name: /^Not linked\s*2$/ })).toBeVisible();
  });

  test("flags off-convention names and unreadable files instead of hiding them", async ({ page }) => {
    await go(page, "/clusters");

    await expect(page.getByTestId("cluster-row-ocp4-upgrade-demo").getByTestId("cluster-off-convention")).toBeVisible();
    await expect(page.getByTestId("cluster-row-ocp4-prod-broken-site1").getByTestId("cluster-unreadable")).toBeVisible();
    await expect(page.getByText("2 flagged")).toBeVisible();
  });

  test("live status off shows a dash, not an error", async ({ page }) => {
    await go(page, "/clusters");

    const status = page.getByTestId("cluster-row-ocp4-prod-alpha-site1").locator("td").nth(1);
    await expect(status).toHaveText("—");
    await expect(page.getByText("Error")).toHaveCount(0);
  });
});

test.describe("Cluster detail", () => {
  async function openDetail(page: Page, clusterDrift: ClusterDrift = drift(), installed: InstalledChart[] = []) {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await statusOff(page);
    await page.route(`**/api/day1/clusters/${NAME}?**`, (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(DETAIL) })
    );
    await page.route(`**/api/day1/clusters/${NAME}/drift?**`, (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(clusterDrift) })
    );
    await page.route(`**/api/day2/clusters/${NAME}/history?**`, (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
    );
    await page.route(`**/api/day2/clusters/${NAME}/addons?**`, (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(charts(installed)) })
    );
    await page.route("**/api/day2/addons", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
    );
    await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);
  }

  test("shows the file's values, the HostedCluster, and a pending VLAN", async ({ page }) => {
    await openDetail(page);

    await expect(page.getByRole("heading", { name: NAME })).toBeVisible();
    await expect(page.getByText("openshift-prod-herzi-site1")).toBeVisible();
    await expect(page.getByText("hcp-prod-herzi-site1")).toBeVisible();
    await expect(page.getByText("1 / 2 / 3")).toBeVisible();
    // vlanId and dhcp_values are written later by the allocate-segment workflow
    await expect(page.getByText("pending")).toHaveCount(2);
    await expect(page.getByText(DETAIL.path)).toBeVisible();
    await expect(page.getByText("cluster-roles")).toBeVisible();
  });

  test("an edit is sent with the last_commit_id it started from", async ({ page }) => {
    await openDetail(page);
    const patch = page.waitForRequest((req: Request) => req.method() === "PATCH");
    await page.route(`**/api/day1/clusters/${NAME}?**`, async (r: Route) => {
      if (r.request().method() === "PATCH") {
        await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockMR({ iid: 51, title: `[Wingman/Day1] Modify cluster ${NAME}` })) });
      } else {
        await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(DETAIL) });
      }
    });

    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Cluster file").fill(YAML.replace("replicas: 2", "replicas: 3"));
    await page.getByRole("button", { name: /review & submit/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();

    const body = (await patch).postDataJSON();
    expect(body.last_commit_id).toBe(DETAIL.last_commit_id);
    expect(body.updated_yaml).toContain("replicas: 3");
    await expect(page.getByText("Modify MR !51 opened")).toBeVisible();
  });

  test("a stale edit (409) is not retried: the page offers a reload", async ({ page }) => {
    await openDetail(page);
    await page.route(`**/api/day1/clusters/${NAME}?**`, async (r: Route) => {
      if (r.request().method() === "PATCH") {
        await fulfillProblem(r, 409, "REVISION_CONFLICT", "the cluster file changed since 0c904bfa");
      } else {
        await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(DETAIL) });
      }
    });

    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Cluster file").fill(`${YAML}# changed\n`);
    await page.getByRole("button", { name: /review & submit/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();

    const alert = page.getByRole("alert").filter({ hasText: "changed since you opened it" });
    await expect(alert).toBeVisible();
    await alert.getByRole("button", { name: "Reload" }).click();
    await expect(alert).not.toBeVisible();
    await expect(page.getByLabel("Cluster file")).not.toBeVisible();
  });

  test("a delete carries last_commit_id", async ({ page }) => {
    await openDetail(page);
    const del = page.waitForRequest((req: Request) => req.method() === "DELETE");
    await page.route(`**/api/day1/clusters/${NAME}?**`, async (r: Route) => {
      if (r.request().method() === "DELETE") {
        await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockMR({ iid: 52 })) });
      } else {
        await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(DETAIL) });
      }
    });

    await page.getByRole("button", { name: "Delete" }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();

    const url = new URL((await del).url());
    expect(url.searchParams.get("last_commit_id")).toBe(DETAIL.last_commit_id);
    expect(url.searchParams.get("mce")).toBe(MCE);
  });

  test("the delete dialog shows the delete-cluster workflow as not available yet", async ({ page }) => {
    await openDetail(page);
    await page.getByRole("button", { name: "Delete" }).click();

    const panel = page.getByRole("dialog").getByTestId("delete-workflow");
    await expect(panel.getByText("Not available yet", { exact: true })).toBeVisible();
    await expect(panel.getByText("Release the network segment")).toBeVisible();
    await expect(panel.getByRole("button", { name: "Start delete workflow" })).toBeDisabled();
    // The MR delete still works meanwhile
    await expect(page.getByRole("dialog").getByRole("button", { name: /confirm/i })).toBeEnabled();
  });

  test("once the workflow exists, an admin starts it by typing the cluster name", async ({ page }) => {
    await openDetail(page);
    let run: unknown = null;
    await page.route(`**/api/day1/clusters/${NAME}/delete-workflow**`, async (r: Route) => {
      if (r.request().method() === "POST") {
        run = { workflow_id: `delete-hosted-cluster-${NAME}`, status: "running", phase: "draining", error: null };
        await r.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(run) });
      } else {
        await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ run }) });
      }
    });
    const started = page.waitForRequest((req: Request) => req.method() === "POST" && req.url().includes("/delete-workflow"));

    await page.getByRole("button", { name: "Delete" }).click();
    const panel = page.getByRole("dialog").getByTestId("delete-workflow");
    const start = panel.getByRole("button", { name: "Start delete workflow" });
    await expect(panel.getByText("Not available yet", { exact: true })).toHaveCount(0);
    await expect(start).toBeDisabled();
    await panel.getByRole("textbox", { name: /cluster name/i }).fill(NAME);
    await start.click();

    expect((await started).postDataJSON()).toEqual({ confirm: true });
    await expect(panel.getByTestId("delete-workflow-run")).toContainText("draining");
  });

  test("unknown drift says why and is not shown as in sync", async ({ page }) => {
    await openDetail(page, drift({ state: "unknown", is_drifted: null, error: "day2 did not answer: timeout" }));

    await page.getByRole("tab", { name: "Drift" }).click();
    await expect(page.getByText("could not be determined")).toBeVisible();
    await expect(page.getByText("day2 did not answer: timeout")).toBeVisible();
    await expect(page.getByText(/in sync/i)).toHaveCount(0);
  });

  test("a cluster of an older spec version is checked against the spec as it is now", async ({ page }) => {
    await openDetail(page, drift({ spec_version: "1.0.0", current_spec_version: "1.1.0" }));

    await page.getByRole("tab", { name: "Drift" }).click();
    await expect(page.getByText("The cluster holds every value agent-standard v1.1.0 locks and has every add-on it lists.")).toBeVisible();
    await expect(page.getByText(
      "The file's header names v1.0.0; drift compares against the flavor as it is now, v1.1.0. A sync moves the header to v1.1.0."
    )).toBeVisible();
  });

  test("drifted addons are fixed with the values requested at create; with no value drift there is no sync", async ({ page }) => {
    await openDetail(page, drift({
      state: "drifted", is_drifted: true,
      addon_drift: [{ addon_name: "cluster-roles", team: "redbull", reason: "missing", expected_version: "main", override_values: { replicas: 2 } }],
    }));
    const install = page.waitForRequest((req: Request) => req.method() === "POST" && req.url().includes("/addons/redbull/cluster-roles"));
    await page.route(`**/api/day2/clusters/${encodeURIComponent(HOSTED_ID)}/addons/redbull/cluster-roles`, (r: Route) =>
      r.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(mockMR({ iid: 9, repo: "day2", team: "redbull" })) })
    );

    await page.getByRole("tab", { name: "Drift" }).click();
    await expect(page.getByText("The cluster has drifted from agent-standard v1.0.0: 1 add-on is missing.")).toBeVisible();
    await expect(page.getByText(/sync yaml/i)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Sync to flavor" })).toHaveCount(0);
    await page.getByRole("button", { name: "Install" }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();

    // Addressed by the id day2 resolved the name to, not by name and ?mce=
    const request = await install;
    expect(new URL(request.url()).pathname).toBe(`/api/day2/clusters/${encodeURIComponent(HOSTED_ID)}/addons/redbull/cluster-roles`);
    // At the team default: day2 refuses another version unless it is an emergency pin (ADR-0025)
    expect(request.postDataJSON()).toEqual({ override_values: { replicas: 2 } });
    await expect(page.getByText("Fix MR !9 opened")).toBeVisible();
  });

  test("another version than the spec names is information, not drift, and has no fix", async ({ page }) => {
    let writes = 0;
    page.on("request", (req: Request) => {
      if (["POST", "PUT"].includes(req.method()) && req.url().includes("/addons/")) writes += 1;
    });
    await openDetail(page, drift({
      version_differences: [{ addon_name: "cluster-roles", team: "redbull", spec_version: "main", installed_version: "release-1" }],
    }), [CLUSTER_ROLES]);

    await page.getByRole("tab", { name: "Drift" }).click();
    await expect(page.getByText(/has every add-on it lists\./)).toBeVisible();
    await expect(page.getByText("release-1 installed · flavor names main")).toBeVisible();
    await expect(page.getByText(/not drift/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /^(install|update|fix)/i })).toHaveCount(0);
    expect(writes).toBe(0);
  });

  test("the Addons link opens the cluster's charts, narrowed by its MCE", async ({ page }) => {
    await openDetail(page);
    await expect(page.getByRole("main").getByRole("link", { name: "Addons" })).toHaveAttribute(
      "href", `/clusters/${NAME}/addons?mce=${MCE}`
    );
  });

  test("the charts page reads the listing the detail page prefetched", async ({ page }) => {
    let listings = 0;
    page.on("request", (req: Request) => {
      if (new URL(req.url()).pathname === `/api/day2/clusters/${NAME}/addons`) listings += 1;
    });
    await page.route(`**/api/day2/clusters/${NAME}?**`, (r: Route) =>
      r.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({
          id: HOSTED_ID, kind: "hosted", name: NAME, site: SITE, env: "prod", mce: MCE, ocp_version: "4.16.27",
          argo: MCE, teams: ["redbull"], in_day1: true, warnings: [],
        }),
      })
    );
    await page.route("**/api/day2/gitlab-info", (r: Route) =>
      r.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ gitlab_url: "https://gitlab.example.com", sigs_group_path: "sigs", sigs_group_url: "https://gitlab.example.com/groups/sigs" }),
      })
    );
    await openDetail(page, drift(), [CLUSTER_ROLES]);
    await expect.poll(() => listings).toBe(1);

    await page.getByRole("main").getByRole("link", { name: "Addons" }).click();
    await page.waitForURL(`**/clusters/${NAME}/addons?mce=${MCE}`);
    await expect(page.getByTestId("installed-redbull-cluster-roles")).toBeVisible();
    expect(listings).toBe(1);
  });

  test("a file that does not parse is shown with its problems", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await statusOff(page);
    const broken: ClusterDetail = { ...DETAIL, values: null, problems: ["the file is not valid YAML: line 3, column 1"] };
    await page.route(`**/api/day1/clusters/${NAME}?**`, (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(broken) })
    );
    await page.route(`**/api/day1/clusters/${NAME}/drift?**`, (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(drift()) })
    );
    await page.route(`**/api/day2/**`, (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ installed: [] }) })
    );
    await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);

    await expect(page.getByText("The cluster file does not parse")).toBeVisible();
    await expect(page.getByText("line 3, column 1")).toBeVisible();
  });

  test("an unknown cluster is a not-found page, not a blank one", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters/ocp4-prod-gone-site1**", (r: Route) =>
      fulfillProblem(r, 404, "NOT_FOUND", "cluster 'ocp4-prod-gone-site1' does not exist")
    );
    await go(page, "/clusters/ocp4-prod-gone-site1");

    await expect(page.getByText(/does not exist/).first()).toBeVisible();
  });
});
