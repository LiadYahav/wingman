/**
 * E2E tests for new features:
 *  F7 — Conflicted badge on approvals list and detail page
 *  F3 — The review part of the flavor editor on /specs/new
 *  F4 — Spec history tab on /specs/[name]
 *
 * Auth pattern:
 *   injectAdminAuth() must be called first (registers addInitScript + auth/config mock).
 *   Then register feature-specific route mocks.
 *   Then navigate to "/" to establish Zustand auth state.
 *   Then navigate to the target page.
 */

import { test, expect, Page } from "@playwright/test";
import { injectAdminAuth, mockDashboardApis, mockMR } from "../fixtures/api-handlers";

// ── Shared mock data ──────────────────────────────────────────────────────────

const mockMRConflicted = mockMR({
  iid: 42,
  title: "Add cluster east-prod",
  description: "Provisioning cluster east-prod",
  author: { username: "alice", name: "alice", avatar_url: "" },
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-01-15T10:00:00Z",
  source_branch: "add-cluster-east-prod",
  labels: [],
  has_conflicts: true,
});

const mockMRNoConflict = mockMR({
  iid: 99,
  title: "Update grafana addon",
  description: "",
  author: { username: "bob", name: "", avatar_url: null },
  created_at: "2026-01-14T09:00:00Z",
  updated_at: "2026-01-14T09:00:00Z",
  source_branch: "update-grafana",
  labels: [],
  repo: "day2",
  team: "observability",
  has_conflicts: false,
});

const mockSpecHistory = [
  {
    sha: "abc123def456abc123def456abc123de",
    short_sha: "abc123de",
    message: "Add cert-manager addon to standard spec",
    author: "alice",
    date: "2026-01-10T12:00:00Z",
    web_url: "https://gitlab.example.com/commit/abc123",
  },
  {
    sha: "def456abc123def456abc123def456ab",
    short_sha: "def456ab",
    message: "Initial spec creation",
    author: "bob",
    date: "2026-01-05T08:00:00Z",
    web_url: "https://gitlab.example.com/commit/def456",
  },
];

// `GET /api/day1/specs/{name}` (SpecOut): the template is filled on read.
const mockSpec = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name: "some-spec", description: "", version: "1.0.0", labels: {} },
  spec: {
    day1: { variables: [], structure: {}, locked_paths: [], template: "", values: {} },
    day2: { addons: [] },
  },
  load_error: null,
  load_problems: [],
};

// ── Shared setup helpers ──────────────────────────────────────────────────────

/**
 * Establish auth + mock page-specific routes, then land on the target page.
 * The two-step navigation (/ then target) is required because Zustand's persist
 * hydration is asynchronous — a direct goto to the target can fire API requests
 * before auth is set, causing 401 → redirect to /login → redirect back to /.
 */
async function setupAndNavigate(
  page: Page,
  targetPath: string,
  mockRouteFn: (page: Page) => Promise<void>
) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await mockRouteFn(page);
  await page.goto("/");
  await page.waitForTimeout(500);
  await page.goto(targetPath);
}

// ─────────────────────────────────────────────────────────────────────────────
// F7 — Conflicted badge
// ─────────────────────────────────────────────────────────────────────────────

test.describe("F7 — Conflicted badge", () => {
  test("shows Conflicted badge in approvals list for MR with has_conflicts: true", async ({ page }) => {
    await setupAndNavigate(page, "/approvals", async (p) => {
      await p.route("**/api/day1/approvals", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([mockMRConflicted]),
        });
      });
      await p.route("**/api/day2/approvals", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([mockMRNoConflict]),
        });
      });
    });

    // The conflicted MR title should appear
    await expect(page.getByText("Add cluster east-prod")).toBeVisible();

    // There should be exactly one "Conflicted" badge (for the conflicted MR only)
    await expect(page.getByText("Conflicted")).toBeVisible();
    await expect(page.getByText("Conflicted")).toHaveCount(1);
  });

  test("does not show Conflicted badge for MR without conflicts", async ({ page }) => {
    await setupAndNavigate(page, "/approvals", async (p) => {
      await p.route("**/api/day1/approvals", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([mockMRConflicted]),
        });
      });
      await p.route("**/api/day2/approvals", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([mockMRNoConflict]),
        });
      });
    });

    // Both MRs appear
    await expect(page.getByRole("link", { name: "Add cluster east-prod" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Update grafana addon" })).toBeVisible();

    // Only ONE Conflicted badge (only the conflicted MR gets it)
    await expect(page.getByText("Conflicted")).toHaveCount(1);
  });

  test("shows Conflicted badge on MR detail page when has_conflicts: true", async ({ page }) => {
    await setupAndNavigate(page, "/approvals/day1-42", async (p) => {
      await p.route("**/api/day1/approvals/42**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            mr: mockMRConflicted,
            diffs: [],
          }),
        });
      });
    });

    // Should see the MR title
    await expect(page.getByText("Add cluster east-prod")).toBeVisible();
    // Should see the Conflicted badge in the meta card
    await expect(page.getByText("Conflicted")).toBeVisible();
  });

  test("does not show Conflicted badge on detail page when has_conflicts: false", async ({ page }) => {
    const mrNoConflict = {
      ...mockMRConflicted,
      iid: 55,
      title: "Clean MR",
      has_conflicts: false,
    };
    await setupAndNavigate(page, "/approvals/day1-55", async (p) => {
      await p.route("**/api/day1/approvals/55**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            mr: { ...mrNoConflict, repo: "day1" },
            diffs: [],
          }),
        });
      });
    });

    await expect(page.getByText("Clean MR")).toBeVisible();
    await expect(page.getByText("Conflicted")).not.toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// F3 — The review part of the flavor editor (it replaced the "Preview variables" dialog)
// ─────────────────────────────────────────────────────────────────────────────

test.describe("F3 — Flavor review part", () => {
  async function setupSpecNewPage(page: Page) {
    await setupAndNavigate(page, "/specs/new", async (p) => {
      await p.route("**/api/day2/addons", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      });
      await p.route("**/api/day1/specs**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      });
      // Registered after "specs**" so they win (Playwright matches LIFO)
      await p.route("**/api/day1/specs/template", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify("mastertag: {{ openshift_release_version }}"),
        });
      });
      await p.route("**/api/day1/specs/template/schema**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      });
    });
    await expect(page.getByRole("heading", { name: "New Flavor" })).toBeVisible();
  }

  test("the parts bar jumps to the review part", async ({ page }) => {
    await setupSpecNewPage(page);
    await page.getByRole("navigation", { name: "Flavor parts" }).getByRole("button", { name: /Review$/ }).click();
    await expect(page.getByRole("heading", { name: "Review", level: 2 })).toBeInViewport();
  });

  test("the review shows the flavor file a save proposes, as YAML", async ({ page }) => {
    await setupSpecNewPage(page);
    const review = page.locator("section#review");
    await review.getByRole("tab", { name: "Flavor file" }).click();
    const yaml = review.getByTestId("flavor-yaml");
    await expect(yaml).toContainText("kind: ClusterSpec");
    // The values that flow into the cluster template, here the nodepool defaults
    await expect(yaml).toContainText("nodepools:");
    await expect(yaml).toContainText("name: workers-chrony-configuration");
  });

  test("the flavor file follows the form as it is typed", async ({ page }) => {
    await setupSpecNewPage(page);
    await page.getByTestId("spec-name-input").fill("qa-flavor");
    await page.getByLabel("Merkaz", { exact: true }).fill("1234");
    const yaml = page.locator("section#review").getByTestId("flavor-yaml");
    await expect(yaml).toContainText("name: qa-flavor");
    await expect(yaml).toContainText('owner_merkaz: "1234"');
  });

  test("the review lists the presets every cluster starts with", async ({ page }) => {
    await setupSpecNewPage(page);
    await page.getByLabel("Merkaz", { exact: true }).fill("1234");
    const presets = page.getByTestId("review-presets");
    await expect(presets).toContainText("Owner · Merkaz");
    await expect(presets).toContainText("1234");
    await expect(page.getByTestId("review-locked")).toContainText("Nothing is locked");
  });

  test("the template tab shows the shared cluster template", async ({ page }) => {
    await setupSpecNewPage(page);
    const review = page.locator("section#review");
    await review.getByRole("tab", { name: "Template" }).click();
    await expect(review.getByText("mastertag: {{ openshift_release_version }}")).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// F4 — Spec history tab
// ─────────────────────────────────────────────────────────────────────────────

test.describe("F4 — Spec history tab", () => {
  async function setupSpecDetailPage(page: Page) {
    await setupAndNavigate(page, "/specs/some-spec", async (p) => {
      // Register catch-all FIRST so specific handlers registered AFTER take priority
      // (Playwright matches in reverse registration order — last registered wins)
      await p.route("**/api/day1/specs**", async (route) => {
        const url = route.request().url();
        if (url.includes("/some-spec/history")) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(mockSpecHistory),
          });
        } else if (url.includes("/some-spec/clusters")) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        } else if (url.includes("/some-spec/drift")) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        } else if (url.includes("/some-spec/at/")) {
          await route.fulfill({
            status: 200,
            contentType: "text/plain",
            body: "apiVersion: wingman.io/v1\nkind: ClusterSpec\n",
          });
        } else if (url.match(/\/api\/day1\/specs\/some-spec$/)) {
          const method = route.request().method();
          if (method === "GET") {
            await route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify(mockSpec),
            });
          } else {
            await route.fulfill({ status: 404 });
          }
        } else {
          // List or other specs endpoints
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        }
      });
    });
  }

  test("History tab button is visible on spec detail page", async ({ page }) => {
    await setupSpecDetailPage(page);

    // The tab is rendered as a button
    await expect(page.getByRole("button", { name: "History" })).toBeVisible();
  });

  test("clicking History tab shows commit list", async ({ page }) => {
    await setupSpecDetailPage(page);

    await page.getByRole("button", { name: "History" }).click();

    // Both commits should appear
    await expect(page.getByText("Add cert-manager addon to standard spec")).toBeVisible();
    await expect(page.getByText("Initial spec creation")).toBeVisible();
  });

  test("history tab shows commit short SHAs", async ({ page }) => {
    await setupSpecDetailPage(page);

    await page.getByRole("button", { name: "History" }).click();

    await expect(page.getByText("abc123de")).toBeVisible();
    await expect(page.getByText("def456ab")).toBeVisible();
  });

  test("history tab shows commit authors", async ({ page }) => {
    await setupSpecDetailPage(page);

    await page.getByRole("button", { name: "History" }).click();

    // Authors shown in commit items
    await expect(page.getByText("alice")).toBeVisible();
    await expect(page.getByText("bob")).toBeVisible();
  });

  test("history tab shows placeholder when no commit selected", async ({ page }) => {
    await setupSpecDetailPage(page);

    await page.getByRole("button", { name: "History" }).click();

    // Before selecting a commit, the content panel shows a prompt
    await expect(page.getByText(/Select a commit to view/i)).toBeVisible();
  });

  test("history tab shows exactly 2 commits from mock data", async ({ page }) => {
    await setupSpecDetailPage(page);

    await page.getByRole("button", { name: "History" }).click();

    // Assert both short SHAs (one per commit)
    await expect(page.getByText("abc123de")).toBeVisible();
    await expect(page.getByText("def456ab")).toBeVisible();

    // The commit messages are both visible
    await expect(page.getByText("Add cert-manager addon to standard spec")).toBeVisible();
    await expect(page.getByText("Initial spec creation")).toBeVisible();
  });
});
