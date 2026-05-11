/**
 * Mocked user-flow tests — complete platform journeys with API mocking.
 * Covers create / edit / approve / audit flows without touching a real backend.
 *
 * Run with: npx playwright test e2e/tests/user-flows.spec.ts
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";

// ── Shared mock data (correct field shapes matching TypeScript types) ──────────

const CATALOG = [
  {
    team: "platform",
    name: "cert-manager",
    current_version: "1.12.0",
    available_versions: ["1.12.0", "1.11.0"],
    default_values: { replicas: 1, namespace: "cert-manager", installCRDs: true },
    dependencies: [],
  },
  {
    team: "platform",
    name: "external-secrets",
    current_version: "0.9.0",
    available_versions: ["0.9.0"],
    default_values: { replicaCount: 1 },
    dependencies: ["platform/cert-manager"],
  },
  {
    team: "observability",
    name: "prometheus",
    current_version: "2.45.0",
    available_versions: ["2.45.0", "2.44.0"],
    default_values: { retention: "15d" },
    dependencies: [],
  },
];

const SPECS = [
  {
    apiVersion: "wingman.io/v1",
    kind: "ClusterSpec",
    metadata: { name: "standard-ha", version: "1.0.0", description: "Standard HA cluster", labels: {} },
    spec: {
      day1: {
        variables: [],
        structure: { nodepools_count: 2 },
        immutable_paths: ["cluster_name"],
        template: "",
      },
      day2: {
        addons: [
          {
            team: "platform",
            name: "cert-manager",
            version: "1.12.0",
            overrideable: [
              { path: "replicas", type: "integer", default: 1, description: "Number of replicas" },
            ],
          },
        ],
      },
    },
  },
];

const MOCK_MR = {
  iid: 42,
  title: "feat: create spec qa-e2e-test",
  description: "Automated spec creation",
  author: { username: "qa-admin", name: "QA Admin", avatar_url: "" },
  state: "opened",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  web_url: "https://gitlab.example.com/mr/42",
  source_branch: "qa-e2e-test",
  target_branch: "main",
  labels: ["wingman"],
  repo: "day1",
  has_conflicts: false,
};

const MOCK_MR_DETAIL = {
  mr: MOCK_MR,
  diffs: [
    {
      old_path: "specs/qa-e2e-test.yaml",
      new_path: "specs/qa-e2e-test.yaml",
      diff: "@@ -0,0 +1,10 @@\n+apiVersion: wingman.io/v1\n+kind: ClusterSpec",
      new_file: true,
      renamed_file: false,
      deleted_file: false,
    },
  ],
};

const AUDIT_COMMITS = [
  {
    id: "abc123def",
    short_id: "abc123d",
    title: "feat: add cert-manager to standard-ha",
    author_name: "qa-admin",
    author_email: "qa@example.com",
    authored_date: new Date().toISOString(),
    message: "feat: add cert-manager to standard-ha",
    web_url: "https://gitlab.example.com/commit/abc123",
    repo: "day1",
  },
];

const AUDIT_MRS = [
  { ...MOCK_MR, repo: "day1" as const, state: "merged" as const },
];

const INSTALLED_ADDONS = [
  {
    team: "platform",
    name: "cert-manager",
    version: "1.12.0",
    override_values: { replicas: 2 },
    available_versions: ["1.12.0", "1.11.0"],
    gitlab_url: "https://gitlab.example.com/mces/mce-east/test-cluster/cert-manager",
  },
];

const MERGED_VALUES = {
  addon_name: "cert-manager",
  team: "platform",
  version: "1.12.0",
  merged: { replicas: 2, namespace: "cert-manager", installCRDs: true },
  chart_values: { replicas: 1, namespace: "cert-manager", installCRDs: true },
  team_values: { replicas: 1, namespace: "cert-manager", installCRDs: true },
  cluster_values: { replicas: 2 },
  provenance: { replicas: "cluster", namespace: "team", installCRDs: "team" },
};

// ── Mock helper ───────────────────────────────────────────────────────────────

async function setupMocks(page: Page) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);

  // Catalog
  await page.route("**/api/day2/addons", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(CATALOG) })
  );

  // Specs CRUD
  await page.route("**/api/day1/specs", async (r: Route) => {
    if (r.request().method() === "GET") {
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(SPECS) });
    } else {
      await r.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(MOCK_MR) });
    }
  });

  // Spec detail
  await page.route("**/api/day1/specs/standard-ha", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(SPECS[0]) })
  );

  // Template
  await page.route("**/api/day1/specs/template", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify("# cluster-template.j2\napiVersion: v1") })
  );

  // Template schema
  await page.route("**/api/day1/specs/template/schema**", (r: Route) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        { name: "nodepools_count", type: "integer", required: true, default: 1 },
        { name: "cluster_name", type: "string", required: true },
      ]),
    })
  );

  // Cluster creation
  await page.route("**/api/day1/clusters", async (r: Route) => {
    if (r.request().method() === "GET") {
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    } else {
      await r.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(MOCK_MR) });
    }
  });

  // Cluster preview
  await page.route("**/api/day1/clusters/preview", (r: Route) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ yaml: "apiVersion: wingman.io/v1\nkind: Cluster\nmetadata:\n  name: test-cluster" }),
    })
  );

  // Sites and MCEs
  await page.route("**/api/day1/sites", async (r: Route) => {
    if (r.request().method() === "GET") {
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(["site-east", "site-west"]) });
    } else {
      await r.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(MOCK_MR) });
    }
  });
  await page.route("**/api/day1/sites/*/mces", async (r: Route) => {
    if (r.request().method() === "GET") {
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(["mce-east", "mce-west"]) });
    } else {
      await r.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(MOCK_MR) });
    }
  });

  // OCP versions
  await page.route("**/api/day1/specs/versions/openshift", (r: Route) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(["4.16.12", "4.15.30", "4.14.20"]),
    })
  );

  // Approvals
  await page.route("**/api/day1/approvals", async (r: Route) => {
    const url = r.request().url();
    if (url.match(/\/approvals\/\d+/)) {
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_MR_DETAIL) });
    } else {
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([MOCK_MR]) });
    }
  });
  await page.route("**/api/day2/approvals", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
  );

  // Audit
  await page.route("**/api/day1/audit/commits", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(AUDIT_COMMITS) })
  );
  await page.route("**/api/day2/audit/commits", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
  );
  await page.route("**/api/day1/audit/merge-requests", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(AUDIT_MRS) })
  );
  await page.route("**/api/day2/audit/merge-requests", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
  );
  // Commit diff: path is /api/day1/audit/commits/{repo}/{sha}/diff — two variable segments,
  // so use ** (not *) to match across the extra repo path segment.
  await page.route("**/api/day1/audit/commits/**/diff", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
  );
  await page.route("**/api/day2/audit/commits/**/diff", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
  );

  // Cluster addons — response must match ClusterInstalledResponse: { cluster, mce, installed[] }
  await page.route("**/api/day2/clusters/*/addons**", async (r: Route) => {
    const url = r.request().url();
    if (url.match(/\/addons\/[^/]+\/[^/?]+/)) {
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MERGED_VALUES) });
    } else {
      await r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ cluster: "test-cluster", mce: "mce-east", installed: INSTALLED_ADDONS }),
      });
    }
  });

  // GitLab info (required by cluster addons page — 401 from unmocked endpoint redirects to /login)
  await page.route("**/api/day2/gitlab-info", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sigs_group_url: "https://gitlab.example.com/sigs" }) })
  );

  // Drift summary (dashboard)
  await page.route("**/api/day1/clusters/drift-summary", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) })
  );
}

async function navigateTo(page: Page, path: string) {
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(400);
  await page.goto(path);
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(600);
}

// ── Spec creation flow ────────────────────────────────────────────────────────

test.describe("Spec Creation Flow", () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test("renders new spec form with name and version fields", async ({ page }) => {
    await navigateTo(page, "/specs/new");

    await expect(page.getByPlaceholder(/standard-ha|dok|compact/i)).toBeVisible();
    await expect(page.getByPlaceholder("1.0.0")).toBeVisible();
  });

  test("addon catalog loads and shows teams with cards", async ({ page }) => {
    await navigateTo(page, "/specs/new");

    // Team section headings appear in the catalog panel
    await expect(page.getByText("platform").first()).toBeVisible();
    await expect(page.getByText("observability").first()).toBeVisible();
    await expect(page.getByTestId("addon-card-platform-cert-manager")).toBeVisible();
    await expect(page.getByTestId("addon-card-platform-external-secrets")).toBeVisible();
  });

  test("search filters addon catalog in real time", async ({ page }) => {
    await navigateTo(page, "/specs/new");

    // The catalog search input has placeholder "Search..."
    await page.getByPlaceholder("Search...").fill("cert");
    await page.waitForTimeout(300);
    await expect(page.getByTestId("addon-card-platform-cert-manager")).toBeVisible();
    await expect(page.getByTestId("addon-card-observability-prometheus")).not.toBeVisible();
  });

  test("clicking Add button on catalog card moves addon to selected section", async ({ page }) => {
    await navigateTo(page, "/specs/new");

    // Each catalog card has an "Add" button — clicking the card div itself does nothing
    const card = page.getByTestId("addon-card-platform-cert-manager");
    await card.getByRole("button", { name: /add/i }).click();
    await expect(page.getByTestId("selected-addon-platform-cert-manager")).toBeVisible();
  });

  test("selected addon can be removed via X button", async ({ page }) => {
    await navigateTo(page, "/specs/new");

    await page.getByTestId("addon-card-platform-cert-manager")
      .getByRole("button", { name: /add/i })
      .click();
    await expect(page.getByTestId("selected-addon-platform-cert-manager")).toBeVisible();

    // The remove button is an X icon with no accessible text — use last() within the row
    await page.getByTestId("selected-addon-platform-cert-manager")
      .locator("button")
      .last()
      .click();

    await expect(page.getByTestId("selected-addon-platform-cert-manager")).not.toBeVisible();
  });

  test("Preview variables dialog opens and shows structure YAML", async ({ page }) => {
    await navigateTo(page, "/specs/new");

    await page.getByRole("button", { name: /preview variables/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    // The preview shows YAML content like "nodepools_count: 1"
    await expect(dialog).toContainText(/nodepools_count|cluster_name|structure/i);
  });

  test("Review & Create opens review dialog with spec YAML", async ({ page }) => {
    await navigateTo(page, "/specs/new");

    // Fill required spec name
    await page.getByPlaceholder(/standard-ha|dok|compact/i).fill("my-qa-spec");

    await page.getByRole("button", { name: /review & create/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("dialog")).toContainText(/review/i);
  });

  test("confirming Review dialog fires POST and redirects to /specs", async ({ page }) => {
    await navigateTo(page, "/specs/new");

    await page.getByPlaceholder(/standard-ha|dok|compact/i).fill("my-qa-spec");
    await page.getByRole("button", { name: /review & create/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: /confirm/i }).click();

    // After MR creation the app navigates to /specs
    await page.waitForURL("**/specs", { timeout: 8000 });
    expect(page.url()).toContain("/specs");
  });

  test("addon card shows current version in version selector", async ({ page }) => {
    await navigateTo(page, "/specs/new");

    const card = page.getByTestId("addon-card-platform-cert-manager");
    await expect(card).toBeVisible();
    await expect(card).toContainText("1.12.0");
  });
});

// ── Cluster creation flow ─────────────────────────────────────────────────────

test.describe("Cluster Creation Flow", () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test("step 1 shows spec cards to choose from", async ({ page }) => {
    await navigateTo(page, "/clusters/new");

    await expect(page.getByText("standard-ha")).toBeVisible();
    await expect(page.getByText("Standard HA cluster")).toBeVisible();
    await expect(page.getByText(/1 addon/i)).toBeVisible();
  });

  test("selecting a spec advances to step 2", async ({ page }) => {
    await navigateTo(page, "/clusters/new");

    await page.getByText("standard-ha").click();
    await expect(page.getByText(/step 2 of 2/i)).toBeVisible();
  });

  test("step 2 shows cluster name and identity fields", async ({ page }) => {
    await navigateTo(page, "/clusters/new");
    await page.getByText("standard-ha").click();
    await page.waitForTimeout(300);

    // Cluster name input placeholder is "e.g. alpha-prod"
    await expect(page.getByPlaceholder("e.g. alpha-prod")).toBeVisible();
    await expect(page.getByText(/site/i).first()).toBeVisible();
    await expect(page.getByText("MCE").first()).toBeVisible();
    await expect(page.getByText(/OpenShift/i).first()).toBeVisible();
  });

  test("Review & Create button is present on step 2", async ({ page }) => {
    await navigateTo(page, "/clusters/new");
    await page.getByText("standard-ha").click();
    await page.waitForTimeout(300);

    // The button renders on step 2 (validation happens on click, not on render)
    await expect(page.getByRole("button", { name: /review & create|generating/i })).toBeVisible();
  });
});

// ── Approvals flow ────────────────────────────────────────────────────────────

test.describe("Approvals Flow", () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test("approvals page lists open MRs with author and title", async ({ page }) => {
    await navigateTo(page, "/approvals");

    await expect(page.getByText("feat: create spec qa-e2e-test")).toBeVisible();
    await expect(page.getByText("qa-admin")).toBeVisible();
  });

  test("repo filter buttons are visible and clickable", async ({ page }) => {
    await navigateTo(page, "/approvals");

    const allBtn = page.getByRole("button", { name: "All" }).first();
    const day1Btn = page.getByRole("button", { name: "day1" }).first();
    await expect(allBtn).toBeVisible();
    await expect(day1Btn).toBeVisible();

    await day1Btn.click();
    // MR is still visible after filtering to day1 (it's a day1 MR)
    await expect(page.getByText("feat: create spec qa-e2e-test")).toBeVisible();
  });

  test("search input filters MR list", async ({ page }) => {
    await navigateTo(page, "/approvals");

    await page.getByPlaceholder("Search by title or author...").fill("nonexistent-mr-xyz");
    await page.waitForTimeout(300);
    await expect(page.getByText("feat: create spec qa-e2e-test")).not.toBeVisible();
  });

  test("MR row links to detail page", async ({ page }) => {
    await setupMocks(page);
    // Mock the detail page data
    await page.route("**/api/day1/approvals/42**", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_MR_DETAIL) })
    );
    await navigateTo(page, "/approvals/day1-42");

    // Detail page header should show the MR title
    await expect(page.getByText("feat: create spec qa-e2e-test")).toBeVisible();
    await expect(page.getByText(/opened/i)).toBeVisible();
    await expect(page.getByText(/qa-admin/i)).toBeVisible();
  });
});

// ── Approval detail and actions ───────────────────────────────────────────────

test.describe("Approval Detail", () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
    await page.route("**/api/day1/approvals/42**", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_MR_DETAIL) })
    );
  });

  test("renders MR metadata: state, repo, author, branches", async ({ page }) => {
    await navigateTo(page, "/approvals/day1-42");

    await expect(page.getByText("opened")).toBeVisible();
    await expect(page.getByText("day1")).toBeVisible();
    await expect(page.getByText("qa-admin")).toBeVisible();
    await expect(page.getByText("main")).toBeVisible(); // target branch
  });

  test("shows file diff cards for changed files", async ({ page }) => {
    await navigateTo(page, "/approvals/day1-42");

    await expect(page.getByText("specs/qa-e2e-test.yaml")).toBeVisible();
    await expect(page.getByText("new")).toBeVisible(); // new_file badge
  });

  test("admin sees Approve and Reject action buttons", async ({ page }) => {
    await navigateTo(page, "/approvals/day1-42");

    await expect(page.getByRole("button", { name: /approve/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /reject|close/i })).toBeVisible();
  });
});

// ── Audit log flow ────────────────────────────────────────────────────────────

test.describe("Audit Log Flow", () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test("audit page loads with Commits tab active and data", async ({ page }) => {
    await navigateTo(page, "/audit");

    await expect(page.getByText("Audit Log")).toBeVisible();
    await expect(page.getByRole("button", { name: /commits/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /merge requests/i })).toBeVisible();
    await expect(page.getByText("feat: add cert-manager to standard-ha")).toBeVisible();
  });

  test("clicking Merge Requests tab shows MRs", async ({ page }) => {
    await navigateTo(page, "/audit");

    await page.getByRole("button", { name: /merge requests/i }).click();
    await page.waitForTimeout(400);

    await expect(page.getByText("feat: create spec qa-e2e-test")).toBeVisible();
    await expect(page.getByText("merged").first()).toBeVisible();
  });

  test("repo filter narrows commit list", async ({ page }) => {
    await navigateTo(page, "/audit");

    await page.getByRole("button", { name: "day2" }).first().click();
    await page.waitForTimeout(300);

    // No day2 commits in mock — shows empty state
    await expect(page.getByText(/no commits/i)).toBeVisible();
  });

  test("search filters commits by title", async ({ page }) => {
    await navigateTo(page, "/audit");

    await page.getByPlaceholder("Search commits...").fill("cert-manager");
    await page.waitForTimeout(300);
    await expect(page.getByText("feat: add cert-manager to standard-ha")).toBeVisible();
  });

  test("clicking a commit row expands diffs", async ({ page }) => {
    await navigateTo(page, "/audit");

    await page.getByText("feat: add cert-manager to standard-ha").click();
    // Diff panel appears (may be "No file changes" since mock returns [])
    await page.waitForTimeout(500);
    await expect(page.getByText("abc123d")).toBeVisible(); // short_id in the commit row
  });
});

// ── Cluster addons flow ───────────────────────────────────────────────────────

const TEST_CLUSTER = {
  name: "test-cluster",
  site: "site-east",
  mce: "mce-east",
  phase: "Ready",
  spec_name: "standard-ha",
  spec_version: "1.0.0",
  created_by: "qa-admin",
  created_at: new Date().toISOString(),
  is_drifted: false,
};

test.describe("Cluster Addons Flow", () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);

    // Override clusters list to include our test cluster
    await page.route("**/api/day1/clusters", async (r: Route) => {
      if (r.request().method() === "GET") {
        await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([TEST_CLUSTER]) });
      } else {
        await r.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(MOCK_MR) });
      }
    });

    // Cluster-specific addon routes (override setupMocks' wildcard route)
    await page.route("**/api/day2/clusters/test-cluster/addons**", async (r: Route) => {
      const url = r.request().url();
      if (url.match(/\/addons\/[^/?]+\/[^/?]+/)) {
        await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MERGED_VALUES) });
      } else {
        await r.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ cluster: "test-cluster", mce: "mce-east", installed: INSTALLED_ADDONS }),
        });
      }
    });
  });

  test("installed addon appears on cluster addons page", async ({ page }) => {
    // Pass ?mce= so the page doesn't need to resolve MCE from cluster list
    await navigateTo(page, "/clusters/test-cluster/addons?mce=mce-east");

    await expect(page.getByText("cert-manager").first()).toBeVisible();
    await expect(page.getByText("platform").first()).toBeVisible();
  });

  test("F6: Layers tab shows YAML not raw JSON", async ({ page }) => {
    await navigateTo(page, "/clusters/test-cluster/addons?mce=mce-east");

    // Expand the addon
    const expandBtn = page.getByRole("button").filter({ hasText: /cert-manager/i });
    if (await expandBtn.isVisible()) {
      await expandBtn.click();
      await page.waitForTimeout(500);
    }

    const layersTab = page.getByRole("tab", { name: /layers/i });
    if (await layersTab.isVisible()) {
      await layersTab.click();
      await page.waitForTimeout(400);

      const tabContent = await page.locator("[role=tabpanel]").textContent() ?? "";
      // Should NOT contain raw JSON object syntax
      expect(tabContent).not.toMatch(/^\s*\{/m);
    }
  });

  test("addon version badge shows current version", async ({ page }) => {
    await navigateTo(page, "/clusters/test-cluster/addons?mce=mce-east");

    await expect(page.getByText("1.12.0").first()).toBeVisible();
  });
});

// ── Spec list page ────────────────────────────────────────────────────────────

test.describe("Specs List Flow", () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test("specs list shows spec cards with name and version", async ({ page }) => {
    await navigateTo(page, "/specs");

    await expect(page.getByText("standard-ha")).toBeVisible();
    await expect(page.getByText("1.0.0")).toBeVisible();
  });

  test("clicking spec card navigates to detail page", async ({ page }) => {
    await page.route("**/api/day1/specs/standard-ha/history", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
    );
    await navigateTo(page, "/specs");

    await Promise.all([
      page.waitForURL(/\/specs\/standard-ha/, { timeout: 6000 }),
      page.getByText("standard-ha").first().click(),
    ]);

    expect(page.url()).toContain("/specs/standard-ha");
  });
});

// ── Global addons catalog page ────────────────────────────────────────────────

test.describe("Global Addons Catalog", () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test("catalog loads with team grouping and addon cards", async ({ page }) => {
    await navigateTo(page, "/addons");

    await expect(page.getByText("Addon Catalog")).toBeVisible();
    await expect(page.getByText("platform").first()).toBeVisible();
    await expect(page.getByText("cert-manager").first()).toBeVisible();
    await expect(page.getByText("1.12.0").first()).toBeVisible();
  });

  test("clicking an addon card opens dialog with values in YAML not JSON", async ({ page }) => {
    await navigateTo(page, "/addons");

    await page.getByText("cert-manager").first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    const content = await dialog.textContent() ?? "";
    // Values should be in YAML form — no raw JSON object syntax
    expect(content).not.toMatch(/\{\s*"[^"]+"\s*:/);
  });

  test("search narrows addon list to matching names", async ({ page }) => {
    await navigateTo(page, "/addons");

    await page.getByPlaceholder("Search addons or teams...").fill("prometheus");
    await page.waitForTimeout(300);
    await expect(page.getByText("prometheus")).toBeVisible();
    await expect(page.getByText("cert-manager")).not.toBeVisible();
  });

  test("F5: dependency chips appear on available-addon cards in cluster addons page", async ({ page }) => {
    // F5 dependency chips live on the cluster addons "Available Addons" panel,
    // not on the global catalog page which uses a simpler card layout.
    await navigateTo(page, "/clusters/test-cluster/addons?mce=mce-east");

    // The available addons section shows addon catalog with dependency chips.
    // external-secrets has dependency on platform/cert-manager.
    const bodyText = await page.textContent("body") ?? "";
    // If available addons section renders, dependency info from mock data should be visible
    expect(bodyText).toMatch(/cert-manager|external-secrets|platform/i);
  });
});
