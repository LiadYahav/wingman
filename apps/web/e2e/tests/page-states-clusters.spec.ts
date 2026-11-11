/**
 * What the cluster detail page and the create form show when a read fails or
 * comes back empty (mocked): a failed read is the service's RFC 9457 problem
 * (detail and request id) where the data would be, never an empty list, a
 * missing section or a placeholder that claims there is nothing; an empty list
 * says what would be there and offers the next step. Live status that is off
 * (501 FEATURE_DISABLED) is still "off", not an error.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import type { ClusterDetail, ClusterDrift, ClusterLiveStatus, DestinationCharts, Mce, SpecEntry, TemplateField } from "../../types";

const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const NAME = "ocp4-prod-herzi-site1";

// ── Cluster detail ──────────────────────────────────────────────────────────

const DETAIL: ClusterDetail = {
  name: NAME,
  site: SITE,
  mce: MCE,
  yaml: "owner:\n  merkaz: \"1\"\nmastertag: 4.16.27-x86_64\n",
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${NAME}.yaml`,
  last_commit_id: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
  metadata: {
    spec_name: null, spec_version: null, created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { merkaz: "1", anaf: "2", mador: "3" },
    mastertag: "4.16.27-x86_64",
    platform: "agent",
    nodepools: [],
    network: { vlan_id: null, dhcp_network: null },
    cluster_name: null,
    automation_keys: [],
  },
  hosted_cluster: { cluster_name: "prod-herzi-site1", name: "openshift-prod-herzi-site1", namespace: "hcp-prod-herzi-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "herzi", sequence: null, problems: [] },
  mce_default_mastertag: "4.16.27-x86_64",
  problems: [],
  segments_manager: null,
};

const DRIFT: ClusterDrift = {
  cluster: NAME, site: SITE, mce: MCE, state: "not_linked", is_drifted: false,
  spec_name: null, spec_version: null, current_spec_version: null,
  value_drift: [], addon_drift: [], version_differences: [], error: null,
};

const CHARTS: DestinationCharts = {
  cluster: NAME, mce: MCE, id: `hosted:${SITE}:prod:${MCE}:${NAME}`, kind: "hosted", site: SITE, env: "prod",
  ocp_version: "4.16.27", installed: [], excluded: [], warnings: [], argocd_note: "",
};

const STATUS_OFF = "Live cluster status is disabled in this deployment (CLUSTER_STATUS_ENABLED=false).";

/**
 * Every read of the detail page answered; `status` answers the live status
 * read (off by default), and the history routes can be overridden after.
 */
async function mockDetail(page: Page, status: (route: Route) => Promise<void> = (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", STATUS_OFF)) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route(`**/api/day1/clusters/${NAME}?**`, (r) => json(r, DETAIL));
  await page.route(`**/api/day1/clusters/${NAME}/drift?**`, (r) => json(r, DRIFT));
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, status);
  await page.route(`**/api/day1/clusters/${NAME}/status/stream**`, (r) =>
    r.fulfill({ status: 200, contentType: "text/event-stream", body: "" })
  );
  await page.route(`**/api/day1/clusters/${NAME}/history?**`, (r) => json(r, []));
  await page.route(`**/api/day2/clusters/${NAME}/history?**`, (r) => json(r, []));
  await page.route(`**/api/day2/clusters/${NAME}/addons?**`, (r) => json(r, CHARTS));
  await page.route("**/api/day2/addons", (r) => json(r, []));
}

const liveStatusCard = (page: Page) => page.locator("[data-slot=card-title]", { hasText: "Live Status" });

/** The page's problems (Next's route announcer is an alert too, so match by wording). */
const problems = (page: Page) => page.getByRole("alert").filter({ hasText: /could not be/ });

test.describe("Cluster detail", () => {
  test("a failed history read shows its problem, never an empty history", async ({ page }) => {
    await mockDetail(page);
    await page.route(`**/api/day1/clusters/${NAME}/history?**`, (r) =>
      fulfillProblem(r, 503, "GIT_UNAVAILABLE", "GitLab could not be reached")
    );
    await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);
    await page.getByRole("tab", { name: "History" }).click();

    // The default query retries twice (1s, 2s) before the error shows
    const problem = page.getByRole("alert").filter({ hasText: "The cluster file's history could not be loaded" });
    await expect(problem).toContainText("GitLab could not be reached", { timeout: 10_000 });
    await expect(problem).toContainText("request req_e2e0000000000001");
    await expect(page.getByTestId("history-day1-empty")).toHaveCount(0);
    // The other source read fine and is empty: it says so on its own
    await expect(page.getByTestId("history-day2-empty")).toContainText("No addon value changes yet");
  });

  test("an empty history is an empty state for each source", async ({ page }) => {
    await mockDetail(page);
    await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);
    await page.getByRole("tab", { name: "History" }).click();

    await expect(page.getByTestId("history-day1-empty")).toContainText("No history yet");
    await expect(page.getByTestId("history-day2-empty")).toContainText("No addon value changes yet");
    await expect(problems(page)).toHaveCount(0);
  });

  test.describe("in an en-US browser", () => {
    test.use({ locale: "en-US" });

    test("a commit's date is en-GB like every other date, not the browser's format", async ({ page }) => {
      await mockDetail(page);
      await page.route(`**/api/day1/clusters/${NAME}/history?**`, (r) =>
        json(r, [{
          sha: "0c904bfafde4c4ed24416190ea224ee25cdcf738", short_sha: "0c904bfa", message: "Create cluster",
          author: "alice", date: "2026-11-07T10:00:00+00:00", web_url: "https://gitlab.example.com/c/0c904bfa",
        }])
      );
      await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);
      await page.getByRole("tab", { name: "History" }).click();

      await expect(page.getByText("0c904bfa")).toBeVisible();
      await expect(page.getByText("07/11/2026", { exact: true })).toBeVisible();
      await expect(page.getByText("11/7/2026")).toHaveCount(0);
    });
  });

  test("a failed live status read shows the problem in place of the card", async ({ page }) => {
    await mockDetail(page, (r) => fulfillProblem(r, 503, "DEPENDENCY_UNAVAILABLE", "The MCE hub did not answer"));
    await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);

    const problem = page.getByTestId("live-status-error");
    await expect(problem).toContainText("Live status could not be read from the MCE hub");
    await expect(problem).toContainText("The MCE hub did not answer");
    await expect(problem).toContainText("request req_e2e0000000000001");
    await expect(liveStatusCard(page)).toHaveCount(0);
  });

  test("live status off (501 FEATURE_DISABLED) is neither a card nor an error", async ({ page }) => {
    await mockDetail(page);
    const status = page.waitForResponse(/\/api\/day1\/clusters\/[^/]+\/status\?/);
    await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);
    expect((await status).status()).toBe(501);

    await expect(page.getByRole("heading", { name: NAME })).toBeVisible();
    // The card is up while the read is out; once it answered 501 it is gone, and no problem replaced it
    await expect(liveStatusCard(page)).toHaveCount(0);
    await expect(page.getByTestId("live-status-error")).toHaveCount(0);
    await expect(problems(page)).toHaveCount(0);
  });

  test("a hub that reports no node pools says so", async ({ page }) => {
    const live: ClusterLiveStatus = {
      cluster_name: NAME, hosted_cluster: "openshift-prod-herzi-site1", namespace: "hcp-prod-herzi-site1",
      hc_phase: "Running", ocp_version: "4.16.27", hc_problems: [], node_pools: [], error: null,
    };
    await mockDetail(page, (r) => json(r, live));
    await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);

    await expect(liveStatusCard(page)).toBeVisible();
    await expect(page.getByTestId("live-status-node-pools-note")).toHaveText("No node pools reported");
  });

  test("a delete GitLab did not confirm says it may have happened, not that it was refused", async ({ page }) => {
    await mockDetail(page);
    await page.route(`**/api/day1/clusters/${NAME}?**`, (r) =>
      r.request().method() === "DELETE"
        ? fulfillProblem(r, 504, "AMBIGUOUS_WRITE", "GitLab did not answer the commit request")
        : r.fallback()
    );
    await go(page, `/clusters/${NAME}?site=${SITE}&mce=${MCE}`);
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: /Delete Cluster MR/ }).click();

    const alert = page.getByRole("alert").filter({ hasText: "GitLab did not answer the commit request" });
    await expect(alert).toContainText("GitLab did not confirm the change, so it may or may not have been made");
    await expect(alert).toContainText("request req_e2e0000000000001");
    await expect(page.getByText("The change was refused")).toHaveCount(0);
    await expect(page.getByText("Delete failed")).toHaveCount(0);
  });
});

// ── Create form ─────────────────────────────────────────────────────────────

const SPEC: SpecEntry = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name: "agent-standard", description: "Bare-metal workers on the Agent platform", version: "1.0.0", labels: {} },
  spec: {
    day1: { variables: [], structure: { nodepools: [{}] }, locked_paths: [], template: "# template", values: {} },
    day2: { addons: [] },
  },
  load_error: null,
  load_problems: [],
};

const SCHEMA: TemplateField[] = [
  { name: "owner_merkaz", type: "string", required: true, example: "1234" },
  {
    name: "nodepools",
    type: "list",
    required: true,
    fields: [{ name: "infra_env", type: "string", required: true, example: "dell-r660-site1" }],
  },
];

const MCES: Mce[] = [
  {
    name: MCE, site: SITE, env: "prod", letter: "a", follows_convention: true, naming_problems: [],
    default_mastertag: "4.16.27-x86_64", hub_version: "4.16.27-x86_64", cluster_count: 1, stray_files: [], problems: [],
  },
];

/** Every read of the create form answered; register an override after this to fail one. */
async function mockCreateForm(page: Page) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/specs", (r) => json(r, [SPEC]));
  await page.route("**/api/day1/specs/template/schema", (r) => json(r, SCHEMA));
  await page.route("**/api/day1/mces/*/openshift-versions", (r) =>
    json(r, { mce: MCE, versions: ["4.16.27"], problems: [] })
  );
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/sites", (r) => json(r, [SITE]));
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => json(r, MCES));
  await page.route("**/api/day1/mces/*/infraenvs", (r) =>
    fulfillProblem(r, 501, "FEATURE_DISABLED", STATUS_OFF)
  );
}

async function openForm(page: Page) {
  await go(page, "/clusters/new");
  await page.getByTestId("spec-card-agent-standard").click();
  await expect(page.getByText(/step 2 of 2/i)).toBeVisible();
}

test.describe("Cluster create form", () => {
  test("with no specs the first step says so and links to a new spec", async ({ page }) => {
    await mockCreateForm(page);
    await page.route("**/api/day1/specs", (r) => json(r, []));
    await go(page, "/clusters/new");

    const empty = page.getByTestId("specs-empty");
    await expect(empty).toContainText("No flavors yet");
    await expect(empty.getByRole("link", { name: "New spec" })).toHaveAttribute("href", "/specs/new");
  });

  test("the site, MCE and version controls are named by their visible labels", async ({ page }) => {
    await mockCreateForm(page);
    await openForm(page);

    await expect(page.getByRole("combobox", { name: /^site\b/i })).toHaveAttribute("data-testid", "site-select");
    await expect(page.getByRole("combobox", { name: /^mce\b/i })).toHaveAttribute("data-testid", "mce-select");
    await expect(page.getByRole("combobox", { name: /^openshift version\b/i })).toHaveAttribute("data-testid", "ocp-version-select");
  });

  test("a failed sites read shows the problem, not \"No sites in the day1 repo\"", async ({ page }) => {
    await mockCreateForm(page);
    await page.route("**/api/day1/sites", (r) => fulfillProblem(r, 503, "GIT_UNAVAILABLE", "GitLab could not be reached"));
    await openForm(page);

    const problem = page.getByRole("alert").filter({ hasText: "The sites could not be loaded" });
    await expect(problem).toContainText("GitLab could not be reached", { timeout: 10_000 });
    await expect(problem).toContainText("request req_e2e0000000000001");
    await expect(page.getByTestId("site-select")).toContainText("Sites could not be loaded");
    await expect(page.getByText("No sites in the day1 repo")).toHaveCount(0);
  });

  test("a failed MCE read says so, and the version waits for an MCE", async ({ page }) => {
    await mockCreateForm(page);
    await page.route(/\/api\/day1\/mces(\?.*)?$/, (r) => fulfillProblem(r, 503, "GIT_UNAVAILABLE", "GitLab could not be reached"));
    await openForm(page);
    await page.getByTestId("site-select").click();
    await page.getByRole("option", { name: SITE }).click();

    const mceProblem = page.getByRole("alert").filter({ hasText: `The MCEs of ${SITE} could not be loaded` });
    await expect(mceProblem).toContainText("GitLab could not be reached", { timeout: 10_000 });
    await expect(page.getByTestId("mce-select")).toContainText("MCEs could not be loaded");
    await expect(page.getByText("No MCEs on this site")).toHaveCount(0);
    await expect(page.getByTestId("ocp-version-select")).toBeDisabled();
    await expect(page.getByTestId("ocp-version-select")).toContainText("Choose an MCE first");
  });

  test("a failed version read says so; the version is then typed", async ({ page }) => {
    await mockCreateForm(page);
    await page.route("**/api/day1/mces/*/openshift-versions", (r) =>
      fulfillProblem(r, 503, "GIT_UNAVAILABLE", "The day1 repo could not be read")
    );
    await openForm(page);
    await page.getByTestId("site-select").click();
    await page.getByRole("option", { name: SITE }).click();
    await page.getByTestId("mce-select").click();
    await page.getByRole("option", { name: MCE }).click();

    const versionProblem = page.getByRole("alert").filter({ hasText: `The OpenShift versions of ${MCE} could not be listed` });
    await expect(versionProblem).toContainText("The day1 repo could not be read", { timeout: 10_000 });
    await expect(page.getByTestId("ocp-version-input")).toBeVisible();
  });

  test("a failed template read is a problem, not \"takes no inputs\"", async ({ page }) => {
    await mockCreateForm(page);
    await page.route("**/api/day1/specs/template/schema", (r) =>
      fulfillProblem(r, 503, "GIT_UNAVAILABLE", "The specs project could not be read")
    );
    await openForm(page);

    const problem = page.getByRole("alert").filter({ hasText: "The cluster template's inputs could not be loaded" });
    await expect(problem).toContainText("The specs project could not be read", { timeout: 10_000 });
    await expect(page.getByText(/takes no inputs/)).toHaveCount(0);
  });

  test("without the template's inputs Review refuses, and nothing is sent", async ({ page }) => {
    await mockCreateForm(page);
    await page.route("**/api/day1/specs/template/schema", (r) =>
      fulfillProblem(r, 503, "GIT_UNAVAILABLE", "The specs project could not be read")
    );
    let previews = 0;
    await page.route("**/api/day1/clusters/preview", (r) => {
      previews += 1;
      return json(r, { path: DETAIL.path, yaml: DETAIL.yaml });
    });
    await openForm(page);
    // Everything else is filled: the site, MCE and version follow from the name
    await page.getByTestId("cluster-name-input").fill(NAME);
    await expect(page.getByTestId("mce-select")).toContainText(MCE);
    await expect(page.getByRole("alert").filter({ hasText: "The cluster template's inputs could not be loaded" }))
      .toContainText("The specs project could not be read", { timeout: 10_000 });

    await page.getByTestId("review-button").click();
    const checks = page.getByTestId("form-problems");
    await expect(checks).toContainText("The cluster template's inputs could not be loaded: reload the page to try again");
    await expect(page.getByRole("dialog", { name: /^Review/ })).toHaveCount(0);
    expect(previews).toBe(0);
  });

  test("infra envs that could not be listed are a problem, and their names are typed", async ({ page }) => {
    await mockCreateForm(page);
    await page.route("**/api/day1/mces/*/infraenvs", (r) =>
      fulfillProblem(r, 503, "DEPENDENCY_UNAVAILABLE", "The MCE hub did not answer")
    );
    await openForm(page);
    await page.getByTestId("cluster-name-input").fill(NAME);
    await expect(page.getByTestId("mce-select")).toContainText(MCE);

    const hint = page.getByTestId("infraenv-hint");
    await expect(hint.getByRole("alert")).toContainText(`InfraEnvs could not be listed from ${MCE}; type their names below`);
    await expect(hint).toContainText("The MCE hub did not answer");
    await expect(hint).toContainText("request req_e2e0000000000001");
    await expect(page.getByPlaceholder("e.g. dell-r660-site1")).toBeVisible();
  });
});
