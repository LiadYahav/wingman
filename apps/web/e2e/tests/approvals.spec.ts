/**
 * Approvals and audit against the rewritten services (mocked):
 * - an approval names the head the reviewer saw (`{sha}`); a moved branch is 409
 *   REVISION_CONFLICT and nothing merges; your own change is 403 SELF_APPROVAL;
 * - day1 serves the day1 and specs repos (`?repo=`), day2 addresses MRs by team + iid;
 * - the audit page keeps each item's repo and expands MRs through the right route.
 */

import { test, expect, type Page, type Route, type Request } from "@playwright/test";
import { fulfillProblem, injectAdminAuth, mockDashboardApis, mockMR } from "../fixtures/api-handlers";
import type { ApprovalDetail, CommitRecord, MRDetail } from "../../types";

const DAY1_MR = mockMR({ iid: 42, title: "[Wingman/Day1] Create cluster ocp4-prod-nova-site1", author: { username: "alice", name: "alice", avatar_url: "" } });
const SPECS_MR = mockMR({
  iid: 5, repo: "specs", project_id: 8, title: "[Wingman/Specs] Update spec agent-standard",
  author: { username: "bob", name: "bob", avatar_url: "" }, sha: "5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a",
});
const DAY2_MR = mockMR({
  iid: 7, repo: "day2", team: "redbull", project_id: 21, gitlab_author: "wingman-bot",
  title: "[Wingman/Day2] Install addon redbull/kyverno on ocp4-prod-herzi-site1",
  author: { username: "carol", name: "", avatar_url: null }, sha: "7d7d7d7d7d7d7d7d7d7d7d7d7d7d7d7d7d7d7d7d",
});

const NEW_FILE_DIFF = {
  old_path: "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-nova-site1.yaml",
  new_path: "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-nova-site1.yaml",
  diff: "@@ -0,0 +1,2 @@\n+mastertag: 4.16.27-x86_64\n+nodepool: []\n",
  new_file: true,
  renamed_file: false,
  deleted_file: false,
};

function detail(mr: MRDetail): ApprovalDetail {
  return { mr, diffs: [NEW_FILE_DIFF] };
}

async function open(page: Page, username = "test-admin") {
  await injectAdminAuth(page, username);
  await mockDashboardApis(page);
  await page.route("**/api/day1/approvals", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([DAY1_MR, SPECS_MR]) })
  );
  await page.route("**/api/day2/approvals", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([DAY2_MR]) })
  );
}

async function go(page: Page, path: string) {
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
  await page.goto(path);
  await page.waitForLoadState("domcontentloaded");
}

test.describe("Approvals list", () => {
  test("lists day1, specs and day2 MRs and links each to its own address", async ({ page }) => {
    await open(page);
    await go(page, "/approvals");

    await expect(page.getByRole("link", { name: DAY1_MR.title })).toHaveAttribute("href", "/approvals/day1-42");
    await expect(page.getByRole("link", { name: SPECS_MR.title })).toHaveAttribute("href", "/approvals/specs-5");
    await expect(page.getByRole("link", { name: DAY2_MR.title })).toHaveAttribute("href", "/approvals/day2-redbull-7");
    await expect(page.getByText("day2 · redbull")).toBeVisible();
  });

  test("a failing service is reported, not shown as 'all caught up'", async ({ page }) => {
    await open(page);
    await page.route("**/api/day2/approvals", (r: Route) => fulfillProblem(r, 503, "GIT_UNAVAILABLE", "GitLab could not be reached"));
    await go(page, "/approvals");

    await expect(page.getByText("Day2 team MRs could not be loaded")).toBeVisible();
    await expect(page.getByText(DAY1_MR.title)).toBeVisible();
  });
});

test.describe("Approve with the reviewed sha", () => {
  test("approving a day1 MR posts the sha shown on the page", async ({ page }) => {
    await open(page);
    let reads = 0;
    await page.route("**/api/day1/approvals/42?repo=day1", (r: Route) => {
      reads++;
      return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(reads > 1 ? { ...DAY1_MR, state: "merged" } : DAY1_MR)) });
    });
    const approve = page.waitForRequest((req: Request) => req.url().includes("/api/day1/approvals/42/approve?repo=day1"));
    await page.route("**/api/day1/approvals/42/approve?repo=day1", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...DAY1_MR, state: "merged" }) })
    );
    await go(page, "/approvals/day1-42");

    await expect(page.getByText(DAY1_MR.sha.slice(0, 8))).toBeVisible();
    await page.getByRole("button", { name: /review & approve/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText(DAY1_MR.sha.slice(0, 12));
    await dialog.getByRole("button", { name: "Approve & Merge" }).click();

    expect((await approve).postDataJSON()).toEqual({ sha: DAY1_MR.sha });
    await expect(page.getByText("merged", { exact: true })).toBeVisible();
  });

  test("a branch that moved is a 409: nothing merges and the page asks to reload", async ({ page }) => {
    await open(page);
    let reads = 0;
    const moved = { ...DAY1_MR, sha: "9999999999999999999999999999999999999999" };
    await page.route("**/api/day1/approvals/42?repo=day1", (r: Route) => {
      reads++;
      return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(reads > 1 ? moved : DAY1_MR)) });
    });
    await page.route("**/api/day1/approvals/42/approve?repo=day1", (r: Route) =>
      fulfillProblem(r, 409, "REVISION_CONFLICT", "the MR head is 99999999, not the reviewed 0c904bfa")
    );
    await go(page, "/approvals/day1-42");

    await page.getByRole("button", { name: /review & approve/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();

    const alert = page.getByRole("alert").filter({ hasText: "The branch moved" });
    await expect(alert).toContainText("allocate-segment workflow");
    await alert.getByRole("button", { name: "Reload" }).click();
    await expect(page.getByText("99999999")).toBeVisible();
    await expect(alert).not.toBeVisible();
  });

  test("an approval page opened again shows the branch as it is now, not a cached head", async ({ page }) => {
    await open(page);
    const moved = { ...DAY1_MR, sha: "8888888888888888888888888888888888888888" };
    let head = DAY1_MR;
    await page.route("**/api/day1/approvals/42?repo=day1", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(head)) })
    );
    await go(page, "/approvals");
    await page.getByRole("link", { name: DAY1_MR.title }).click();
    await expect(page.getByText(DAY1_MR.sha.slice(0, 8))).toBeVisible();

    // CI pushes to the branch while the reviewer is elsewhere in the app.
    head = moved;
    await page.getByRole("link", { name: "Approvals" }).first().click();
    await page.getByRole("link", { name: DAY1_MR.title }).click();
    await expect(page.getByText(moved.sha.slice(0, 8))).toBeVisible();

    const approve = page.waitForRequest((req: Request) => req.url().includes("/api/day1/approvals/42/approve?repo=day1"));
    await page.route("**/api/day1/approvals/42/approve?repo=day1", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...moved, state: "merged" }) })
    );
    await page.getByRole("button", { name: /review & approve/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();
    expect((await approve).postDataJSON()).toEqual({ sha: moved.sha });
  });

  test("an approval's detail is never written to the persisted query cache", async ({ page }) => {
    await open(page);
    await page.route("**/api/day1/approvals/42?repo=day1", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(DAY1_MR)) })
    );
    await go(page, "/approvals/day1-42");
    await expect(page.getByText(DAY1_MR.sha.slice(0, 8))).toBeVisible();
    // The persister writes at most once a second; wait until it has written.
    await expect
      .poll(() => page.evaluate(() => window.localStorage.getItem("wingman-query-cache") ?? ""), { timeout: 5_000 })
      .toContain("clientState");
    const stored = await page.evaluate(() => window.localStorage.getItem("wingman-query-cache") ?? "");
    expect(stored).not.toContain(DAY1_MR.sha);
    expect(stored).not.toContain('"approvals"');
  });

  test("self-approval is refused with a clear message", async ({ page }) => {
    await open(page);
    await page.route("**/api/day1/approvals/42?repo=day1", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(DAY1_MR)) })
    );
    await page.route("**/api/day1/approvals/42/approve?repo=day1", (r: Route) =>
      fulfillProblem(r, 403, "SELF_APPROVAL", "alice requested this change and cannot approve it")
    );
    await go(page, "/approvals/day1-42");

    await page.getByRole("button", { name: /review & approve/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();
    await expect(page.getByText("You requested this change, so another admin must approve it.")).toBeVisible();
  });

  test("a merge GitLab did not confirm says it may have happened, not that it failed", async ({ page }) => {
    await open(page);
    await page.route("**/api/day1/approvals/42?repo=day1", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(DAY1_MR)) })
    );
    await page.route("**/api/day1/approvals/42/approve?repo=day1", (r: Route) =>
      fulfillProblem(r, 504, "AMBIGUOUS_WRITE", "GitLab did not answer the merge request")
    );
    await go(page, "/approvals/day1-42");

    await page.getByRole("button", { name: /review & approve/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();
    const alert = page.getByRole("alert").filter({ hasText: "GitLab did not answer the merge request" });
    await expect(alert).toContainText("GitLab did not confirm the change, so it may or may not have been made");
    await expect(alert).toContainText("request req_e2e0000000000001");
    await expect(page.getByText("The action failed")).toHaveCount(0);
  });

  test("your own MR cannot be approved from the page", async ({ page }) => {
    await open(page, "alice");
    await page.route("**/api/day1/approvals/42?repo=day1", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(DAY1_MR)) })
    );
    await go(page, "/approvals/day1-42");

    await expect(page.getByRole("button", { name: /review & approve/i })).toBeDisabled();
    await expect(page.getByText("You requested this change; another admin approves it.")).toBeVisible();
  });

  test("a specs MR is read and approved with ?repo=specs", async ({ page }) => {
    await open(page);
    await page.route("**/api/day1/approvals/5?repo=specs", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(SPECS_MR)) })
    );
    const approve = page.waitForRequest((req: Request) => req.url().endsWith("/api/day1/approvals/5/approve?repo=specs"));
    await page.route("**/api/day1/approvals/5/approve?repo=specs", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...SPECS_MR, state: "merged" }) })
    );
    await go(page, "/approvals/specs-5");

    await page.getByRole("button", { name: /review & approve/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();
    expect((await approve).postDataJSON()).toEqual({ sha: SPECS_MR.sha });
  });

  test("a day2 MR is addressed by team and iid", async ({ page }) => {
    await open(page);
    await page.route("**/api/day2/approvals/redbull/7", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(DAY2_MR)) })
    );
    const approve = page.waitForRequest((req: Request) => req.url().endsWith("/api/day2/approvals/redbull/7/approve"));
    await page.route("**/api/day2/approvals/redbull/7/approve", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...DAY2_MR, state: "merged" }) })
    );
    await go(page, "/approvals/day2-redbull-7");

    await expect(page.getByRole("heading", { name: DAY2_MR.title })).toBeVisible();
    await expect(page.getByText("day2 · redbull")).toBeVisible();
    await page.getByRole("button", { name: /review & approve/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();
    expect((await approve).postDataJSON()).toEqual({ sha: DAY2_MR.sha });
  });

  test("editing a new file commits it on the branch with the reviewed sha", async ({ page }) => {
    await open(page);
    let current = DAY1_MR;
    await page.route("**/api/day1/approvals/42?repo=day1", async (r: Route) => {
      if (r.request().method() === "PUT") current = { ...DAY1_MR, sha: "1111111111111111111111111111111111111111" };
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(current)) });
    });
    await go(page, "/approvals/day1-42");

    await page.getByRole("button", { name: /edit files/i }).click();
    const editor = page.getByLabel(NEW_FILE_DIFF.new_path);
    await expect(editor).toHaveValue("mastertag: 4.16.27-x86_64\nnodepool: []\n");
    await editor.fill("mastertag: 4.18.22-x86_64\nnodepool: []\n");
    await page.getByRole("button", { name: /review & submit changes/i }).click();
    const put = page.waitForRequest((req: Request) => req.method() === "PUT");
    await page.getByRole("dialog").getByRole("button", { name: "Submit Changes" }).click();

    expect((await put).postDataJSON()).toEqual({
      files: [{ path: NEW_FILE_DIFF.new_path, content: "mastertag: 4.18.22-x86_64\nnodepool: []\n" }],
      message: "",
      sha: DAY1_MR.sha,
    });
    await expect(page.getByText("11111111")).toBeVisible();
  });

  test("an MR that only changes files has nothing to edit here, and says so", async ({ page }) => {
    await open(page);
    const changed = { ...NEW_FILE_DIFF, diff: "@@ -1 +1 @@\n-mastertag: 4.16.27-x86_64\n+mastertag: 4.18.22-x86_64\n", new_file: false };
    await page.route("**/api/day1/approvals/42?repo=day1", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ mr: DAY1_MR, diffs: [changed] }) })
    );
    await go(page, "/approvals/day1-42");

    await page.getByRole("button", { name: /edit files/i }).click();
    await expect(page.getByTestId("approval-nothing-editable")).toContainText("No file in this MR can be edited here");
    await expect(page.getByText("1 changed file can only be edited")).toBeVisible();
    await expect(page.getByRole("button", { name: /review & submit changes/i })).toHaveCount(0);
  });

  test("an unknown id format is explained", async ({ page }) => {
    await open(page);
    await go(page, "/approvals/nope");
    await expect(page.getByText(/Expected/)).toContainText("day2-<team>-67");
  });
});

test.describe("Audit", () => {
  const COMMITS: CommitRecord[] = [
    {
      id: "a1a1a1a1a1a1a1a1", short_id: "a1a1a1a1", title: "Update spec agent-standard", author_name: "bob",
      author_email: "bob@openshift.local", authored_date: "2026-11-07T09:00:00+00:00",
      message: "Update spec agent-standard", web_url: "https://gitlab.example.com/c/a1", repo: "specs",
    },
  ];
  const DAY2_COMMITS: CommitRecord[] = [
    {
      id: "d2d2d2d2d2d2d2d2", short_id: "d2d2d2d2", title: "Install kyverno", author_name: "carol",
      author_email: "carol@openshift.local", authored_date: "2026-11-07T08:00:00+00:00",
      message: "Install kyverno", web_url: "https://gitlab.example.com/c/d2", repo: "day2", team: "redbull",
    },
  ];

  async function openAudit(page: Page) {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/audit/commits", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(COMMITS) })
    );
    await page.route("**/api/day2/audit/commits", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(DAY2_COMMITS) })
    );
    await page.route("**/api/day1/audit/merge-requests", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ ...SPECS_MR, state: "merged" }]) })
    );
    await page.route("**/api/day2/audit/merge-requests", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([DAY2_MR]) })
    );
    await go(page, "/audit");
  }

  test("keeps each commit's repo and asks the right service for its diff", async ({ page }) => {
    await openAudit(page);
    const specsDiff = page.waitForRequest((req: Request) => req.url().includes("/api/day1/audit/commits/specs/a1a1a1a1a1a1a1a1/diff"));
    await page.route("**/api/day1/audit/commits/specs/*/diff", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
    );
    const day2Diff = page.waitForRequest((req: Request) => req.url().endsWith("/api/day2/audit/commits/d2d2d2d2d2d2d2d2/diff?team=redbull"));
    await page.route("**/api/day2/audit/commits/*/diff**", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
    );

    const specsCommit = page.getByRole("button", { name: /Update spec agent-standard/ });
    await expect(specsCommit).toContainText("specs");
    await specsCommit.click();
    await specsDiff;
    await page.getByText("Install kyverno").click();
    await day2Diff;
  });

  test("expands a specs MR with ?repo=specs and a day2 MR by team", async ({ page }) => {
    await openAudit(page);
    const specsDetail = page.waitForRequest((req: Request) => req.url().endsWith("/api/day1/approvals/5?repo=specs"));
    await page.route("**/api/day1/approvals/5?repo=specs", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(SPECS_MR)) })
    );
    const day2Detail = page.waitForRequest((req: Request) => req.url().endsWith("/api/day2/approvals/redbull/7"));
    await page.route("**/api/day2/approvals/redbull/7", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(DAY2_MR)) })
    );

    await page.getByRole("button", { name: /merge requests/i }).click();
    await page.getByText(SPECS_MR.title).click();
    await specsDetail;
    await expect(page.getByText(NEW_FILE_DIFF.new_path)).toBeVisible();
    await page.getByText(DAY2_MR.title).click();
    await day2Detail;
  });

  test("the specs repo filter shows only specs items", async ({ page }) => {
    await openAudit(page);
    await page.getByRole("button", { name: "specs", exact: true }).click();
    await expect(page.getByText("Update spec agent-standard")).toBeVisible();
    await expect(page.getByText("Install kyverno")).not.toBeVisible();
  });
});
