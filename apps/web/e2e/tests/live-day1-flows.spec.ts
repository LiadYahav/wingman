/**
 * The main day1 flows against a running stack: dev login with the secret,
 * the dashboard, create a cluster from a spec, find it among the pending
 * approvals, approve it as a second admin with the sha they reviewed (a
 * commit pushed after the review is refused, reload, approve), edit and
 * delete it with last_commit_id; live status off (or streaming when on);
 * a spec built from the catalog, its history, an edit and a delete; and the
 * audit log. Every change is a real MR, so run it only against a disposable
 * GitLab (the in-memory fake, or the seeded local GitLab CE).
 *
 *   WINGMAN_DEV_AUTH_SECRET=<DEV_AUTH_SECRET> PLAYWRIGHT_BASE_URL=http://localhost:3000 \
 *     npx playwright test live-day1-flows --project=live
 *
 * The web must reach the services at /api/* (nginx, or `next dev` with
 * WINGMAN_DEV_DAY1_URL/WINGMAN_DEV_DAY2_URL, see README.md). The fixtures'
 * spec agent-standard, MCE ocp4-prod-mce-site1-a, cluster
 * ocp4-prod-herzi-site1 and day2 chart redbull/bmhgen are assumed.
 */

import { test, expect, type Browser, type Page, type Request } from "@playwright/test";

const SECRET = process.env.WINGMAN_DEV_AUTH_SECRET ?? "";
const SPEC = "agent-standard";
const MCE = "ocp4-prod-mce-site1-a";
const HERZI = "ocp4-prod-herzi-site1";
const RUN = Date.now().toString(36).slice(-5);
const NAME = `ocp4-prod-e2e${RUN}-site1`;
const NEW_SPEC = `e2e-spec-${RUN}`;

test.describe.configure({ mode: "serial" });
test.skip(!SECRET, "set WINGMAN_DEV_AUTH_SECRET to the day1 service's DEV_AUTH_SECRET");

async function loginAs(browser: Browser, username: string): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Dev login secret").fill(SECRET);
  await page.getByRole("combobox", { name: "Role" }).click();
  await page.getByRole("option", { name: "Admin" }).click();
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => url.pathname === "/");
  return page;
}

async function token(page: Page): Promise<string> {
  return (await page.context().cookies()).find((c) => c.name === "wingman-token")?.value ?? "";
}

async function auth(page: Page) {
  return { Authorization: `Bearer ${await token(page)}` };
}

async function approveAndMerge(page: Page, url: string) {
  await page.goto(url);
  await page.getByRole("button", { name: /review & approve/i }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();
  await expect(page.getByText("merged", { exact: true })).toBeVisible({ timeout: 15_000 });
}

/** Open the MR a write's toast announces (a day1 or specs MR). */
async function followToast(page: Page, toast: RegExp): Promise<string> {
  // Earlier writes' toasts may still be up, each with its own Review button.
  const announced = page.locator("[data-sonner-toast]").filter({ hasText: toast });
  await expect(announced).toBeVisible({ timeout: 15_000 });
  await announced.getByRole("button", { name: "Review" }).click();
  await page.waitForURL(/\/approvals\/(day1|specs)-\d+$/);
  return page.url();
}

/** The `last_commit_id` the spec is read at now; `null` from a day1 that does not send it. */
async function specReadAt(page: Page, name: string): Promise<string | null> {
  const res = await page.request.get(`/api/day1/specs/${name}`, { headers: await auth(page) });
  expect(res.ok()).toBeTruthy();
  return (await res.json()).last_commit_id ?? null;
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

test("the dashboard counts the clusters and specs; the sidebar and the docs are there", async () => {
  await alice.goto("/");
  await expect(alice.getByRole("heading", { name: "Overview" })).toBeVisible();
  const clusters = alice.getByRole("link", { name: /Total Clusters/ });
  await expect(clusters).toContainText(/\d+/);
  await expect(clusters).toContainText(/\d+ specs?/);
  const nav = alice.getByLabel("Main");
  for (const page of ["Clusters", "Specs", "Addons", "Approvals", "Audit", "Documentation"]) {
    await expect(nav.getByRole("link", { name: new RegExp(`^${page}`) })).toBeVisible();
  }

  await alice.goto("/docs");
  await expect(alice.locator("h1").first()).toBeVisible();
  await expect(alice.getByRole("heading", { name: "Day2 Addons" })).toBeVisible();
});

test("create a cluster from a spec opens an MR its requester cannot approve", async () => {
  await alice.goto("/clusters/new");
  await alice.getByTestId(`spec-card-${SPEC}`).click();
  await alice.getByTestId("cluster-name-input").fill(NAME);
  await expect(alice.getByTestId("naming-hint")).toContainText("Follows the naming convention");
  // The fixture prod MCE offers the ladder's 4.16-4.18 rungs, not its 4.16.27 default (ADR-0034)
  await alice.getByTestId("ocp-version-select").click();
  await alice.getByRole("option", { name: "4.18.56" }).click();
  await alice.getByPlaceholder("e.g. 1234").fill("1234");
  await alice.getByPlaceholder("e.g. 56").fill("56");
  await alice.getByPlaceholder("e.g. 7").fill("7");
  const infraEnvs = alice.getByPlaceholder("e.g. dell-r660-site1-128c-1024gb-5tb");
  for (let i = 0; i < (await infraEnvs.count()); i++) await infraEnvs.nth(i).fill(`dell-r660-site1-pool${i + 1}`);
  // Each nodepool starts with the nodepool defaults (nm-conf, workers-chrony-configuration,
  // nic-ring-buffer); its nm-conf needs the nodepool's hardware type
  const hardwareTypes = alice.getByRole("combobox", { name: /configs: entry \d+ hardware type$/ });
  await expect(hardwareTypes.first()).toBeVisible();
  for (let i = 0; i < (await hardwareTypes.count()); i++) {
    await hardwareTypes.nth(i).click();
    await alice.getByRole("option").filter({ has: alice.getByText("dell", { exact: true }) }).click();
    await expect(alice.getByRole("option")).toHaveCount(0);
  }
  // The spec's addon is found in the day2 catalog, so its full values can be edited
  await expect(alice.getByTestId("addon-redbull-cluster-roles").getByRole("button", { name: "Full Values" })).toBeVisible();

  await alice.getByTestId("review-button").click();
  const dialog = alice.getByRole("dialog");
  await expect(dialog).toContainText(`hostedClusters/${NAME}.yaml`);
  await dialog.getByRole("button", { name: /confirm/i }).click();
  await alice.waitForURL(/\/approvals\/day1-\d+$/, { timeout: 15_000 });
  createUrl = alice.url();

  await expect(alice.getByRole("button", { name: /review & approve/i })).toBeDisabled();
});

test("the pending approvals list the MR under its repo", async () => {
  await bob.goto("/approvals");
  const mr = bob.getByRole("link", { name: new RegExp(`Create cluster ${NAME}`) });
  await expect(mr).toBeVisible();
  await bob.getByRole("button", { name: "specs", exact: true }).click();
  await expect(mr).toHaveCount(0);
  await bob.getByRole("button", { name: "day1", exact: true }).click();
  await expect(mr).toBeVisible();
  await expect(mr).toHaveAttribute("href", new URL(createUrl).pathname);
});

test("an approval of a head that moved is refused; after a reload it merges", async () => {
  await bob.goto(createUrl);
  await bob.getByRole("button", { name: /review & approve/i }).waitFor();

  // Stand in for CI or the allocate-segment workflow: a commit after bob's review.
  const iid = createUrl.split("-").pop();
  const headers = await auth(alice);
  const detail = await (await alice.request.get(`/api/day1/approvals/${iid}`, { headers })).json();
  const file = detail.diffs[0];
  const content = file.diff.split("\n")
    .filter((l: string) => l.startsWith("+") && !l.startsWith("+++"))
    .map((l: string) => l.slice(1))
    .join("\n");
  const pushed = await alice.request.put(`/api/day1/approvals/${iid}`, {
    headers,
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
  await expect(alice.getByTestId(`cluster-row-${HERZI}`)).toBeVisible();
  await expect(alice.getByTestId(`cluster-row-${NAME}`)).toHaveCount(0);
});

test("live status that is off is not an error; on, it streams frames", async () => {
  const headers = await auth(alice);
  const res = await alice.request.get(`/api/day1/clusters/${HERZI}/status?mce=${MCE}`, { headers });
  await alice.goto(`/clusters/${HERZI}`);
  await expect(alice.getByRole("heading", { name: HERZI })).toBeVisible();

  if (res.status() === 501) {
    expect((await res.json()).code).toBe("FEATURE_DISABLED");
    await expect(alice.getByText("Live Status")).toHaveCount(0);
    await alice.goto("/clusters");
    await expect(alice.getByTestId(`cluster-row-${HERZI}`).locator("td").nth(1)).toHaveText("—");
    return;
  }
  expect(res.ok()).toBeTruthy();
  const status = await res.json();
  expect(status).toHaveProperty("hc_phase");
  expect(status).toHaveProperty("ocp_version");
  await expect(alice.getByText("Live Status")).toBeVisible();
  // The page streams with fetch() and the session's bearer token; so does this.
  const framed = await alice.evaluate(
    async ({ path, bearer }) => {
      const stream = await fetch(path, { headers: { Authorization: `Bearer ${bearer}` }, signal: AbortSignal.timeout(8_000) });
      if (!stream.ok || !stream.body) return false;
      const reader = stream.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) return false;
        buffer += decoder.decode(value, { stream: true });
        if (buffer.includes("data: ")) return true;
      }
    },
    { path: `/api/day1/clusters/${HERZI}/status/stream?mce=${MCE}`, bearer: await token(alice) },
  );
  expect(framed).toBe(true);
});

test("a spec built from the catalog opens a specs MR that merges", async () => {
  await alice.goto("/specs/new");
  await alice.getByTestId("spec-name-input").fill(NEW_SPEC);
  // A chart whose team sets no revision is added at HEAD, the chart repo's default branch
  const bmhgen = alice.getByTestId("addon-card-redbull-bmhgen");
  await expect(bmhgen.getByRole("combobox")).toContainText("HEAD");
  await bmhgen.getByRole("button", { name: "Add", exact: true }).click();
  await expect(alice.getByTestId("selected-addon-redbull-bmhgen")).toBeVisible();

  await alice.getByRole("button", { name: /preview variables/i }).click();
  const preview = alice.getByRole("dialog");
  await expect(preview.getByRole("heading", { name: "Preview variables" })).toBeVisible();
  await expect(preview.locator("pre")).toBeVisible();
  await alice.keyboard.press("Escape");
  await expect(preview).toHaveCount(0);

  await alice.getByRole("button", { name: /review & create/i }).click();
  const dialog = alice.getByRole("dialog");
  await expect(dialog).toContainText(NEW_SPEC);
  await expect(dialog).toContainText("bmhgen");
  await dialog.getByRole("button", { name: /confirm/i }).click();
  await approveAndMerge(bob, await followToast(alice, /Spec MR !\d+ opened/));
});

test("the spec is listed, and its history shows the file at a commit", async () => {
  await alice.goto("/specs");
  await expect(alice.getByTestId(`spec-card-${NEW_SPEC}`)).toBeVisible();

  const history = await alice.request.get(`/api/day1/specs/${NEW_SPEC}/history`, { headers: await auth(alice) });
  expect(history.ok()).toBeTruthy();
  const [latest] = (await history.json()) as { sha: string; short_sha: string }[];
  expect(latest).toBeTruthy();

  await alice.goto(`/specs/${NEW_SPEC}`);
  await expect(alice.getByText("bmhgen")).toBeVisible();
  await alice.getByRole("button", { name: "History", exact: true }).click();
  await alice.getByRole("button").filter({ hasText: latest.short_sha }).click();
  const file = alice.locator("pre").filter({ hasText: "apiVersion" });
  await expect(file).toContainText(`name: ${NEW_SPEC}`);
  await expect(file).toContainText("bmhgen");
});

test("a spec edit carries the read's last_commit_id (once day1 sends it) and merges", async () => {
  const readAt = await specReadAt(alice, NEW_SPEC);
  await alice.goto(`/specs/${NEW_SPEC}/edit`);
  await alice.getByTestId("spec-description-input").fill("Edited by the live day1 flows");
  const put = alice.waitForRequest((r: Request) => r.method() === "PUT");
  await alice.getByRole("button", { name: /review & update/i }).click();
  await alice.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();

  expect(new URL((await put).url()).searchParams.get("last_commit_id")).toBe(readAt);
  await approveAndMerge(bob, await followToast(alice, /Update MR !\d+ opened/));
  await alice.goto(`/specs/${NEW_SPEC}`);
  await expect(alice.getByText("Edited by the live day1 flows")).toBeVisible();
});

test("a spec delete carries the read's last_commit_id (once day1 sends it), merges, and the spec is gone", async () => {
  const readAt = await specReadAt(alice, NEW_SPEC);
  await alice.goto(`/specs/${NEW_SPEC}`);
  const del = alice.waitForRequest((r: Request) => r.method() === "DELETE");
  await alice.getByRole("main").getByRole("button", { name: "Delete", exact: true }).click();
  await alice.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();

  expect(new URL((await del).url()).searchParams.get("last_commit_id")).toBe(readAt);
  await approveAndMerge(bob, await followToast(alice, /Delete MR !\d+ opened/));
  await alice.goto("/specs");
  await expect(alice.getByTestId(`spec-card-${SPEC}`)).toBeVisible();
  await expect(alice.getByTestId(`spec-card-${NEW_SPEC}`)).toHaveCount(0);
});

test("the audit log shows the merged MRs and commits, and expands them", async () => {
  await alice.goto("/audit");
  await alice.getByRole("button", { name: /merge requests/i }).click();
  await alice.getByText(`Delete cluster ${NAME}`).click();
  await expect(alice.getByText(`hostedClusters/${NAME}.yaml`)).toBeVisible();

  await alice.getByRole("button", { name: /^commits/i }).click();
  await alice.getByPlaceholder("Search commits...").fill(NEW_SPEC);
  const commits = alice.getByRole("button").filter({ hasText: NEW_SPEC });
  await expect(commits.first()).toBeVisible();
  // The spec's commits are in the specs repo, not the day1 one
  await alice.getByRole("button", { name: "day1", exact: true }).click();
  await expect(commits).toHaveCount(0);
  await alice.getByRole("button", { name: "specs", exact: true }).click();
  await commits.first().click();
  await expect(alice.getByText(`specs/${NEW_SPEC}.yaml`).first()).toBeVisible();
});
