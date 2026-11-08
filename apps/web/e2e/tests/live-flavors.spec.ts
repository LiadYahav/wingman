/**
 * Flavors v2 against a running stack (ADR-0037): an existing cluster written
 * by hand joins a flavor from the flavor's page, a second admin merges the
 * import, then the cluster is synced to the flavor from its Drift tab, every
 * removal confirmed, and that MR is merged too. Every step is a real MR, so
 * run it only against a disposable, freshly seeded GitLab (the in-memory fake,
 * or the local GitLab CE after `seed_gitlab.py --reset`): it needs the
 * fixture cluster ocp4-prod-lark-site1 to follow no flavor yet.
 *
 *   WINGMAN_DEV_AUTH_SECRET=<DEV_AUTH_SECRET> PLAYWRIGHT_BASE_URL=http://localhost:3000 \
 *     npx playwright test live-flavors --project=live
 */

import { test, expect, type Browser, type Page } from "@playwright/test";

const SECRET = process.env.WINGMAN_DEV_AUTH_SECRET ?? "";
const FLAVOR = "agent-baseline";
const LARK = "ocp4-prod-lark-site1";

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

async function auth(page: Page) {
  const token = (await page.context().cookies()).find((c) => c.name === "wingman-token")?.value ?? "";
  return { Authorization: `Bearer ${token}` };
}

/** Open the MR a write's toast announces. */
async function followToast(page: Page, toast: RegExp): Promise<string> {
  const announced = page.locator("[data-sonner-toast]").filter({ hasText: toast });
  await expect(announced).toBeVisible({ timeout: 15_000 });
  await announced.getByRole("button", { name: "Review" }).click();
  await page.waitForURL(/\/approvals\/day1-\d+$/);
  return page.url();
}

async function approveAndMerge(page: Page, url: string) {
  await page.goto(url);
  await page.getByRole("button", { name: /review & approve/i }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();
  await expect(page.getByText("merged", { exact: true })).toBeVisible({ timeout: 15_000 });
}

let alice: Page;
let bob: Page;

test.beforeAll(async ({ browser }) => {
  alice = await loginAs(browser, "alice");
  bob = await loginAs(browser, "bob");
  const lark = await alice.request.get(`/api/day1/clusters/${LARK}`, { headers: await auth(alice) });
  expect(lark.ok()).toBeTruthy();
  test.skip(
    (await lark.json()).metadata.spec_name !== null,
    `${LARK} already follows a flavor: reseed the GitLab (seed_gitlab.py --reset) and run again`
  );
});

test.afterAll(async () => {
  await alice?.context().close();
  await bob?.context().close();
});

test("a hand-written cluster joins a flavor from the flavor's page", async () => {
  await alice.goto(`/specs/${FLAVOR}`);
  await alice.getByRole("main").getByRole("button", { name: "Add existing clusters" }).first().click();
  const sheet = alice.getByTestId("import-sheet");
  await sheet.getByLabel("Search clusters by name").fill("lark");
  await sheet.getByTestId(`import-pick-${LARK}`).click();
  await sheet.getByRole("button", { name: "Preview 1 cluster" }).click();
  const card = sheet.getByTestId(`import-candidate-${LARK}`);
  await expect(card).toBeVisible({ timeout: 15_000 });
  await expect(card).toContainText("worker-kubeletconfig-reserved"); // a sync would remove it
  await sheet.getByRole("button", { name: "Import 1 cluster" }).click();
  const url = await followToast(alice, /Import MR !\d+ opened/);
  await approveAndMerge(bob, url);

  await alice.goto(`/clusters/${LARK}`);
  await alice.getByRole("tab", { name: "Drift" }).click();
  await expect(alice.getByTestId("value-drift")).toBeVisible({ timeout: 15_000 });
  await expect(alice.getByTestId("value-drift-nodepool[1].configs")).toContainText("restored-example-config");
});

test("the cluster syncs to the flavor, each removal confirmed", async () => {
  await alice.goto(`/clusters/${LARK}`);
  await alice.getByRole("tab", { name: "Drift" }).click();
  await alice.getByRole("button", { name: "Sync to flavor" }).click();
  const dialog = alice.getByRole("dialog");
  await expect(dialog.getByTestId("sync-diff")).toContainText("-  - name: worker-kubeletconfig-reserved", {
    timeout: 15_000,
  });
  const submit = dialog.getByRole("button", { name: "Open sync MR" });
  await expect(submit).toBeDisabled();
  const removals = dialog.getByTestId("sync-removals");
  await removals.getByRole("checkbox", { name: /worker-kubeletconfig-reserved/ }).check();
  await removals.getByRole("checkbox", { name: /restored-example-config/ }).check();
  await submit.click();
  const url = await followToast(alice, /Sync MR !\d+ opened/);
  await approveAndMerge(bob, url);

  const detail = await alice.request.get(`/api/day1/clusters/${LARK}`, { headers: await auth(alice) });
  const pools = (await detail.json()).values.nodepools as { configs: string[] }[];
  expect(pools.map((p) => [...p.configs].sort())).toEqual([
    ["nic-ring-buffer", "nm-conf-prod-lark-site1-dell", "workers-chrony-configuration"],
    ["nic-ring-buffer", "nm-conf-prod-lark-site1-dell-data", "workers-chrony-configuration"],
  ]);
  await alice.goto(`/clusters/${LARK}`);
  await alice.getByRole("tab", { name: "Drift" }).click();
  await expect(alice.getByText(/Missing addons|holds every value/).first()).toBeVisible({ timeout: 15_000 });
  await expect(alice.getByTestId("value-drift")).toHaveCount(0);
});
