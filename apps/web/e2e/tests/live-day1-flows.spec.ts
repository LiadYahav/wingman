/**
 * The main day1 flows against a running stack: dev login with the secret,
 * create a cluster from a spec, approve it as a second admin with the sha
 * they reviewed (a commit pushed after the review is refused, reload,
 * approve), edit and delete it with last_commit_id. Every change is a real
 * MR, so run it only against a disposable GitLab (the in-memory fake, or
 * the seeded local GitLab CE).
 *
 *   WINGMAN_DEV_AUTH_SECRET=<DEV_AUTH_SECRET> PLAYWRIGHT_BASE_URL=http://localhost:3000 \
 *     npx playwright test live-day1-flows --project=live
 *
 * The web must reach the services at /api/* (nginx, or `next dev` with
 * WINGMAN_DEV_DAY1_URL/WINGMAN_DEV_DAY2_URL, see README.md). The fixtures'
 * spec agent-standard and MCE ocp4-prod-mce-site1-a are assumed.
 */

import { test, expect, type Browser, type Page } from "@playwright/test";

const SECRET = process.env.WINGMAN_DEV_AUTH_SECRET ?? "";
const SPEC = "agent-standard";
const NAME = `ocp4-prod-e2e${Date.now().toString(36).slice(-5)}-site1`;

test.describe.configure({ mode: "serial" });
test.skip(!SECRET, "set WINGMAN_DEV_AUTH_SECRET to the day1 service's DEV_AUTH_SECRET");

async function loginAs(browser: Browser, username: string): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Dev login secret").fill(SECRET);
  await page.getByRole("combobox").selectOption("admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => url.pathname === "/");
  return page;
}

async function token(page: Page): Promise<string> {
  return (await page.context().cookies()).find((c) => c.name === "wingman-token")?.value ?? "";
}

async function approveAndMerge(page: Page, url: string) {
  await page.goto(url);
  await page.getByRole("button", { name: /review & approve/i }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();
  await expect(page.getByText("merged", { exact: true })).toBeVisible({ timeout: 15_000 });
}

/** Open the MR a write's toast announces. */
async function followToast(page: Page, toast: RegExp): Promise<string> {
  await expect(page.getByText(toast)).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Review" }).click();
  await page.waitForURL(/\/approvals\/day1-\d+$/);
  return page.url();
}

let alice: Page;
let bob: Page;
let createUrl: string;

test.beforeAll(async ({ browser }) => {
  alice = await loginAs(browser, "alice");
  bob = await loginAs(browser, "bob");
});

test.afterAll(async () => {
  await alice?.context().close();
  await bob?.context().close();
});

test("create a cluster from a spec opens an MR its requester cannot approve", async () => {
  await alice.goto("/clusters/new");
  await alice.getByTestId(`spec-card-${SPEC}`).click();
  await alice.getByTestId("cluster-name-input").fill(NAME);
  await expect(alice.getByTestId("naming-hint")).toContainText("Follows the naming convention");
  await alice.getByPlaceholder("e.g. 1234").fill("1234");
  await alice.getByPlaceholder("e.g. 56").fill("56");
  await alice.getByPlaceholder("e.g. 7").fill("7");
  const infraEnvs = alice.getByPlaceholder("e.g. dell-r660-site1-128c-1024gb-5tb");
  for (let i = 0; i < (await infraEnvs.count()); i++) await infraEnvs.nth(i).fill(`dell-r660-site1-pool${i + 1}`);
  const configs = alice.getByPlaceholder("e.g. worker-kubeletconfig-reserved");
  for (let i = 0; i < (await configs.count()); i++) await configs.nth(i).fill("worker-chrony-configuration");

  await alice.getByTestId("review-button").click();
  const dialog = alice.getByRole("dialog");
  await expect(dialog).toContainText(`hostedClusters/${NAME}.yaml`);
  await dialog.getByRole("button", { name: /confirm/i }).click();
  await alice.waitForURL(/\/approvals\/day1-\d+$/, { timeout: 15_000 });
  createUrl = alice.url();

  await expect(alice.getByRole("button", { name: /review & approve/i })).toBeDisabled();
});

test("an approval of a head that moved is refused; after a reload it merges", async () => {
  await bob.goto(createUrl);
  await bob.getByRole("button", { name: /review & approve/i }).waitFor();

  // Stand in for CI or the allocate-segment workflow: a commit after bob's review.
  const iid = createUrl.split("-").pop();
  const auth = { Authorization: `Bearer ${await token(alice)}` };
  const detail = await (await alice.request.get(`/api/day1/approvals/${iid}`, { headers: auth })).json();
  const file = detail.diffs[0];
  const content = file.diff.split("\n")
    .filter((l: string) => l.startsWith("+") && !l.startsWith("+++"))
    .map((l: string) => l.slice(1))
    .join("\n");
  const pushed = await alice.request.put(`/api/day1/approvals/${iid}`, {
    headers: auth,
    data: { files: [{ path: file.new_path, content: `${content}\n# pushed after the review\n` }], message: "after review", sha: detail.mr.sha },
  });
  expect(pushed.ok()).toBeTruthy();

  await bob.getByRole("button", { name: /review & approve/i }).click();
  await bob.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();
  const moved = bob.getByRole("alert").filter({ hasText: "The branch moved" });
  await expect(moved).toBeVisible({ timeout: 15_000 });
  await moved.getByRole("button", { name: "Reload" }).click();
  await expect(bob.getByText("pushed after the review").first()).toBeVisible();

  await approveAndMerge(bob, createUrl);
});

test("the new cluster shows its HostedCluster and a pending VLAN", async () => {
  await alice.goto(`/clusters/${NAME}`);
  await expect(alice.getByText(`hcp-${NAME.replace(/^ocp4-/, "")}`)).toBeVisible();
  await expect(alice.getByText("pending", { exact: true }).first()).toBeVisible();
});

test("an edit (with last_commit_id) merges", async () => {
  await alice.goto(`/clusters/${NAME}`);
  await alice.getByRole("button", { name: "Edit" }).click();
  const editor = alice.getByLabel("Cluster file");
  await editor.fill((await editor.inputValue()).replace("replicas: 2", "replicas: 3"));
  await alice.getByRole("button", { name: /review & submit/i }).click();
  await alice.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
  await approveAndMerge(bob, await followToast(alice, /Modify MR !\d+ opened/));
});

test("a delete (with last_commit_id) merges and the cluster is gone", async () => {
  await alice.goto(`/clusters/${NAME}`);
  await alice.getByRole("button", { name: "Delete" }).click();
  await alice.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
  await approveAndMerge(bob, await followToast(alice, /Delete MR !\d+ opened/));

  await alice.goto("/clusters");
  await expect(alice.getByTestId("cluster-row-ocp4-prod-herzi-site1")).toBeVisible();
  await expect(alice.getByTestId(`cluster-row-${NAME}`)).toHaveCount(0);
});

test("the audit log shows the merged MRs and expands one", async () => {
  await alice.goto("/audit");
  await alice.getByRole("button", { name: /merge requests/i }).click();
  await alice.getByText(`Delete cluster ${NAME}`).click();
  await expect(alice.getByText(`hostedClusters/${NAME}.yaml`)).toBeVisible();
});
