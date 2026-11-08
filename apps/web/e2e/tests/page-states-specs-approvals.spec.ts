/**
 * What the spec, approval and audit pages show while they load, when a list
 * is empty and when a read fails (mocked): skeletons shaped like what will be
 * there; an empty list says what would be there and offers the next step; a
 * failed read is the service's RFC 9457 problem (detail and request id), never
 * an empty list or a section that silently goes missing.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, go, held, injectAdminAuth, json, mockDashboardApis, mockMR } from "../fixtures/api-handlers";
import type { ApprovalDetail, CommitRecord, SpecCommit, SpecEntry } from "../../types";

const UNREACHABLE = "GitLab could not be reached";
const REQUEST_ID = "request req_e2e0000000000001";

const SPEC: SpecEntry = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name: "agent-standard", description: "Bare-metal workers on the Agent platform", version: "1.0.0", labels: {} },
  spec: {
    day1: { variables: [], structure: {}, immutable_paths: [], template: "", values: {} },
    day2: { addons: [] },
  },
  load_error: null,
  load_problems: [],
};

const unreachable = (route: Route) => fulfillProblem(route, 503, "GIT_UNAVAILABLE", UNREACHABLE);

/** The problem panel with `title`; filtered because Next's route announcer is also `role="alert"`. */
const problem = (page: Page, title: string) => page.getByRole("alert").filter({ hasText: title });

/** Auth, the dashboard's reads and the routes a test adds; land on "/" so the session hydrates, then open `path`. */
async function open(page: Page, path: string, routes: (page: Page) => Promise<unknown> = async () => {}) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await routes(page);
  await go(page, path);
}

// ── Spec list ────────────────────────────────────────────────────────────────

test.describe("Spec list", () => {
  test("while the specs load, the cards and the count are skeletons", async ({ page }) => {
    await open(page, "/");
    const specs = held();
    await page.route("**/api/day1/specs", specs.answer([SPEC]));
    await page.goto("/specs");

    const skeletons = page.getByRole("main").locator("[data-slot=skeleton]");
    await expect(skeletons.first()).toBeVisible();
    // Not yet known to be empty: neither the empty state nor a count of zero
    await expect(page.getByTestId("specs-empty")).toHaveCount(0);
    await expect(page.getByText("0 specs")).toHaveCount(0);
    specs.release();
    await expect(page.getByTestId("spec-card-agent-standard")).toBeVisible();
    await expect(page.getByText("1 spec", { exact: true })).toBeVisible();
    await expect(skeletons).toHaveCount(0);
  });

  test("a failed read shows the problem, never an empty list", async ({ page }) => {
    await open(page, "/specs", (p) => p.route("**/api/day1/specs", unreachable));

    // The default query retries twice (1s, 2s) before the error shows
    const alert = problem(page, "The specs could not be loaded");
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
    await expect(page.getByTestId("specs-empty")).toHaveCount(0);
    await expect(page.getByText("0 specs")).toHaveCount(0);
  });

  test("with no specs it says so and offers to create one", async ({ page }) => {
    await open(page, "/specs");

    const empty = page.getByTestId("specs-empty");
    await expect(empty).toContainText("No specs yet");
    await expect(empty.getByRole("link", { name: "New spec" })).toHaveAttribute("href", "/specs/new");
  });

  test("a search that matches nothing says so and clears in one click", async ({ page }) => {
    await open(page, "/specs", (p) => p.route("**/api/day1/specs", (r) => json(r, [SPEC])));

    await page.getByPlaceholder("Search specs...").fill("no-such-spec");
    await expect(page.getByText("No specs match")).toBeVisible();
    await page.getByRole("button", { name: "Clear search" }).click();
    await expect(page.getByTestId("spec-card-agent-standard")).toBeVisible();
  });
});

// ── Spec detail ──────────────────────────────────────────────────────────────

test.describe("Spec detail", () => {
  const CLUSTERS = "**/api/day1/specs/agent-standard/clusters";
  const HISTORY = "**/api/day1/specs/agent-standard/history";

  /** The spec itself, then the routes a test adds. */
  const withSpec = (more: (p: Page) => Promise<unknown> = async () => {}) => async (p: Page) => {
    await p.route("**/api/day1/specs/agent-standard", (r) => json(r, SPEC));
    await more(p);
  };

  test("a failed clusters read is a problem on the tab and in the delete review", async ({ page }) => {
    await open(page, "/specs/agent-standard", withSpec((p) => p.route(CLUSTERS, unreachable)));
    await page.getByRole("button", { name: /^Clusters/ }).click();

    const alert = problem(page, "The clusters using this spec could not be loaded");
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
    await expect(page.getByRole("main").locator("table")).toHaveCount(0);
    await expect(page.getByTestId("spec-clusters-empty")).toHaveCount(0);

    // The delete review cannot say how many clusters lose their spec: it says it does not know
    await page.getByRole("main").getByRole("button", { name: "Delete", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByTestId("spec-delete-clusters-unknown")).toContainText("Could not be checked");
    await expect(dialog.getByRole("alert").filter({ hasText: "could not be loaded" })).toContainText(REQUEST_ID);
  });

  test("a spec no cluster uses says so and offers to create one", async ({ page }) => {
    await open(page, "/specs/agent-standard", withSpec((p) => p.route(CLUSTERS, (r) => json(r, []))));
    await page.getByRole("button", { name: /^Clusters/ }).click();

    const empty = page.getByTestId("spec-clusters-empty");
    await expect(empty).toContainText("No clusters created from this spec yet");
    await expect(empty.getByRole("link", { name: "New cluster" })).toHaveAttribute("href", "/clusters/new");
  });

  test("while drift is computed, the summary and the rows are skeletons", async ({ page }) => {
    const drift = held();
    await open(page, "/specs/agent-standard", withSpec(async (p) => {
      await p.route(CLUSTERS, (r) => json(r, []));
      await p.route("**/api/day1/specs/agent-standard/drift", drift.answer([]));
    }));
    await page.getByRole("button", { name: "Drift", exact: true }).click();

    const skeletons = page.getByRole("main").locator("[data-slot=skeleton]");
    await expect(skeletons.first()).toBeVisible();
    expect(await skeletons.count()).toBeGreaterThan(3); // a summary bar and several rows, not one block
    drift.release();
    await expect(page.getByTestId("spec-drift-empty")).toContainText("No clusters use this spec");
    await expect(skeletons).toHaveCount(0);
  });

  test("a failed history read is a problem, never a blank list", async ({ page }) => {
    await open(page, "/specs/agent-standard", withSpec((p) => p.route(HISTORY, unreachable)));
    await page.getByRole("button", { name: "History" }).click();

    const alert = problem(page, "The spec's history could not be loaded");
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
    await expect(page.getByTestId("spec-history-empty")).toHaveCount(0);
  });

  test("a spec at a commit that cannot be read is a problem, never an empty file", async ({ page }) => {
    const commit: SpecCommit = {
      sha: "abc123de00000000000000000000000000000000", short_sha: "abc123de",
      message: "Update spec agent-standard", author: "alice", date: "2026-11-07T10:00:00+00:00",
      web_url: "https://gitlab.example.com/wingman/cluster-specs/-/commit/abc123de",
    };
    await open(page, "/specs/agent-standard", withSpec(async (p) => {
      await p.route(HISTORY, (r) => json(r, [commit]));
      await p.route("**/api/day1/specs/agent-standard/at/*", unreachable);
    }));
    await page.getByRole("button", { name: "History" }).click();
    await page.getByRole("button", { name: /Update spec agent-standard/ }).click();

    const alert = problem(page, "The spec at this commit could not be loaded");
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
    await expect(page.getByRole("main").locator("pre")).toHaveCount(0);
  });
});

// ── Audit ────────────────────────────────────────────────────────────────────

test.describe("Audit", () => {
  const COMMIT: CommitRecord = {
    id: "a1a1a1a1a1a1a1a1", short_id: "a1a1a1a1", title: "Update spec agent-standard", author_name: "bob",
    author_email: "bob@openshift.local", authored_date: "2026-11-07T09:00:00+00:00",
    message: "Update spec agent-standard", web_url: "https://gitlab.example.com/c/a1", repo: "specs",
  };
  const SPECS_MR = mockMR({
    iid: 5, repo: "specs", project_id: 8, state: "merged", title: "[Wingman/Specs] Update spec agent-standard",
  });

  /** Every audit source answers an empty list, then the routes a test adds (matched first). */
  const withAudit = (more: (p: Page) => Promise<unknown> = async () => {}) => async (p: Page) => {
    for (const source of ["day1/audit/commits", "day2/audit/commits", "day1/audit/merge-requests", "day2/audit/merge-requests"]) {
      await p.route(`**/api/${source}`, (r) => json(r, []));
    }
    await more(p);
  };

  test("a failed source is a problem, and the list does not also say it is empty", async ({ page }) => {
    await open(page, "/audit", withAudit(async (p) => {
      await p.route("**/api/day1/audit/commits", unreachable);
      await p.route("**/api/day1/audit/merge-requests", unreachable);
    }));

    const commits = problem(page, "Day1 and spec commits could not be loaded");
    await expect(commits).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(commits).toContainText(REQUEST_ID);
    await expect(page.getByText("No commits yet")).toHaveCount(0);

    await page.getByRole("button", { name: /merge requests/i }).click();
    await expect(problem(page, "Day1 and spec MRs could not be loaded")).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(page.getByText("No merge requests yet")).toHaveCount(0);
  });

  test("with every source loaded and nothing in them, it says so", async ({ page }) => {
    await open(page, "/audit", withAudit());

    await expect(page.getByTestId("audit-commits-empty")).toContainText("No commits yet");
    await page.getByRole("button", { name: /merge requests/i }).click();
    await expect(page.getByTestId("audit-mrs-empty")).toContainText("No merge requests yet");
  });

  test("filters that match nothing say so and clear in one click", async ({ page }) => {
    await open(page, "/audit", withAudit((p) => p.route("**/api/day1/audit/commits", (r) => json(r, [COMMIT]))));

    await page.getByPlaceholder("Search commits...").fill("no-such-commit");
    const none = page.getByTestId("audit-commits-no-matches");
    await expect(none).toContainText("No commits match");
    await none.getByRole("button", { name: "Clear filters" }).click();
    await expect(page.getByText(COMMIT.title)).toBeVisible();
  });

  test("a commit diff that cannot be read is a problem with its request id", async ({ page }) => {
    await open(page, "/audit", withAudit(async (p) => {
      await p.route("**/api/day1/audit/commits", (r) => json(r, [COMMIT]));
      await p.route("**/api/day1/audit/commits/specs/*/diff", unreachable);
    }));
    await page.getByRole("button", { name: /Update spec agent-standard/ }).click();

    const alert = problem(page, "The commit's diff could not be loaded");
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
  });

  test("an MR diff that cannot be read is a problem", async ({ page }) => {
    await open(page, "/audit", withAudit(async (p) => {
      await p.route("**/api/day1/audit/merge-requests", (r) => json(r, [SPECS_MR]));
      await p.route("**/api/day1/approvals/5?repo=specs", unreachable);
    }));
    await page.getByRole("button", { name: /merge requests/i }).click();
    await page.getByText(SPECS_MR.title).click();

    const alert = problem(page, "The merge request's diff could not be loaded");
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
  });
});

// ── Approvals ────────────────────────────────────────────────────────────────

test.describe("Approvals", () => {
  const MR = mockMR({ iid: 42, title: "[Wingman/Day1] Create cluster ocp4-prod-nova-site1" });

  test("with nothing to approve it says all caught up", async ({ page }) => {
    await open(page, "/approvals");

    await expect(page.getByTestId("approvals-empty")).toContainText("All caught up");
    // Both sources answered: nothing is still a skeleton beside the empty state
    await expect(page.getByRole("main").locator("[data-slot=skeleton]")).toHaveCount(0);
  });

  test("filters that match nothing say so and clear in one click", async ({ page }) => {
    await open(page, "/approvals", (p) => p.route("**/api/day1/approvals", (r) => json(r, [MR])));

    await page.getByPlaceholder("Search by title or author...").fill("no-such-mr");
    const none = page.getByTestId("approvals-no-matches");
    await expect(none).toContainText("No merge requests match");
    await none.getByRole("button", { name: "Clear filters" }).click();
    await expect(page.getByRole("link", { name: MR.title })).toBeVisible();
  });

  test("when every source fails there is no empty table and no count of zero", async ({ page }) => {
    await open(page, "/approvals", async (p) => {
      await p.route("**/api/day1/approvals", unreachable);
      await p.route("**/api/day2/approvals", unreachable);
    });

    await expect(problem(page, "Day1 and spec MRs could not be loaded")).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(problem(page, "Day2 team MRs could not be loaded")).toContainText(REQUEST_ID, { timeout: 10_000 });
    await expect(page.getByTestId("approvals-table")).toHaveCount(0);
    await expect(page.getByTestId("approvals-empty")).toHaveCount(0);
    await expect(page.getByText(/^0 merge requests/)).toHaveCount(0);
  });

  test("while an MR loads its card and files are skeletons; an MR without files says so", async ({ page }) => {
    await open(page, "/");
    const detail: ApprovalDetail = { mr: MR, diffs: [] };
    const read = held();
    await page.route("**/api/day1/approvals/42?repo=day1", read.answer(detail));
    await page.goto("/approvals/day1-42");

    const loading = page.getByTestId("approval-loading");
    await expect(loading.locator("[data-slot=skeleton]").first()).toBeVisible();
    read.release();
    await expect(page.getByRole("heading", { name: MR.title })).toBeVisible();
    await expect(loading).toHaveCount(0);
    await expect(page.getByTestId("approval-no-files")).toContainText("No changed files");
  });

  test("an unknown id is an error that says what an id looks like and links back", async ({ page }) => {
    await open(page, "/approvals/nope");

    const invalid = page.getByTestId("approval-invalid-id");
    const alert = invalid.getByRole("alert");
    await expect(alert).toContainText("Invalid MR ID");
    await expect(alert).toContainText('"nope" names no merge request');
    await expect(alert).toContainText("day2-<team>-67");
    await expect(invalid.locator("[data-slot=empty-state]")).toHaveCount(0);
    await expect(invalid.getByRole("link", { name: "Back to approvals" })).toHaveAttribute("href", "/approvals");
  });
});
