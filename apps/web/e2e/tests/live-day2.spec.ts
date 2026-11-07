/**
 * The day2 pages against a running day1 + day2 stack whose GitLab is the
 * in-memory fake seeded from dev/gitlab-fixtures (WINGMAN_GIT_BACKEND=fake):
 * no network, and nothing merges, so every run sees the same main branch.
 *
 * Run with the stack behind one origin (nginx, or any proxy with the chart's
 * routing) and the dev login secret:
 *   PLAYWRIGHT_BASE_URL=http://localhost:3200 DEV_AUTH_SECRET=... \
 *     npx playwright test --project=live live-day2.spec.ts
 */

import { test, expect, type Page, type Request } from "@playwright/test";

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:8080";
const SECRET = process.env.DEV_AUTH_SECRET ?? "";

const HAWK = "ocp4-prod-hawk-site1";
const MCE = "mce:site1:prod:ocp4-prod-mce-site1-a";
const UPI = "upi:site1:prod:ocp4-dok-site1";

test.skip(!SECRET, "needs DEV_AUTH_SECRET for the dev login");

async function login(page: Page) {
  const res = await page.request.post(`${BASE}/api/auth/dev-login`, {
    data: { username: "live-admin", role: "admin", secret: SECRET },
  });
  expect(res.ok()).toBeTruthy();
  const { access_token, user } = await res.json();
  await page.addInitScript(
    ({ token, user }) => {
      localStorage.setItem("wingman-auth", JSON.stringify({ state: { user, isAuthenticated: true }, version: 0 }));
      document.cookie = `wingman-token=${token}; path=/; SameSite=Strict`;
    },
    { token: access_token, user },
  );
}

async function open(page: Page, path: string) {
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
  await page.goto(path);
  await page.waitForLoadState("domcontentloaded");
}

const opened = (page: Page) => page.getByRole("region", { name: "Opened merge requests" });

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("the catalog flags the miscased repoUrl", async ({ page }) => {
  await open(page, "/addons");
  await expect(page.getByText(/charts? across \d+ teams/)).toBeVisible();
  await expect(page.getByRole("button", { name: /kyverno/ })).toContainText("No lowercase repourl");
});

test("a hosted cluster from a day1 link: provenance, then an update guarded by last_commit_id", async ({ page }) => {
  await open(page, `/clusters/${HAWK}/addons?site=site1&mce=ocp4-prod-mce-site1-a`);
  const card = page.getByTestId("installed-falcon-cluster-roles");
  await card.getByRole("button", { name: /^cluster-roles/ }).click();
  await expect(card.getByTestId("value-row-team")).toContainText("team");
  await expect(card.getByTestId("value-row-clusterName")).toContainText("cluster");

  await card.getByTestId("value-row-team").getByRole("textbox").fill("falcon-live");
  await expect(card.getByTestId("value-row-team")).toContainText("cluster");
  await card.getByRole("button", { name: "Review update" }).click();
  const put = page.waitForRequest((r: Request) => r.method() === "PUT");
  await page.getByRole("dialog").getByRole("button", { name: /Create MR/ }).click();
  const body = (await put).postDataJSON();
  expect(body.last_commit_id).toMatch(/^[0-9a-f]{40}$/);
  expect(body.override_values).toEqual({ clusterName: HAWK, team: "falcon-live" });
  await expect(opened(page)).toContainText(`Update addon falcon/cluster-roles on ${HAWK}`);
});

test("install, remove (orphans) and bulk install on a hosted cluster", async ({ page }) => {
  await open(page, `/clusters/${HAWK}/addons?mce=ocp4-prod-mce-site1-a`);

  const bmhgen = page.getByTestId("available-redbull-bmhgen");
  await bmhgen.getByRole("button", { name: "Install" }).click();
  await expect(bmhgen.getByTestId("value-row-replicas")).toContainText("chart");
  await bmhgen.getByRole("button", { name: "Review install" }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Create MR/ }).click();
  await expect(opened(page)).toContainText(`Install addon redbull/bmhgen on ${HAWK}`);
  await opened(page).getByRole("button", { name: "Dismiss" }).click();

  const metrics = page.getByTestId("installed-orca-metrics");
  await metrics.getByRole("button", { name: "Actions for metrics" }).click();
  await page.getByRole("button", { name: /Remove from this cluster/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("The workload keeps running.");
  await dialog.getByPlaceholder("metrics").fill("metrics");
  await dialog.getByRole("button", { name: "Open removal MR" }).click();
  await expect(opened(page)).toContainText("orphans the workload");
  await opened(page).getByRole("button", { name: "Dismiss" }).click();

  await page.getByTestId("available-falcon-log-forwarder").getByRole("checkbox").click();
  await page.getByTestId("available-lynx-cluster-roles").getByRole("checkbox").click();
  await page.getByRole("button", { name: "Install selected" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Open 2 MRs" }).click();
  await expect(opened(page)).toContainText("2 merge requests opened");
});

test("an MCE shows its fleet defaults and the chart with no repourl", async ({ page }) => {
  await open(page, `/clusters/${encodeURIComponent(MCE)}/addons`);
  await expect(page.getByText("MCE", { exact: true })).toBeVisible();
  await expect(page.getByTestId("installed-falcon-mce-agent")).toContainText("fleet default");
  const kyverno = page.getByTestId("installed-redbull-kyverno");
  await kyverno.getByRole("button", { name: /^kyverno/ }).click();
  await expect(kyverno).toContainText("repourl-missing");
  await expect(kyverno).toContainText("Chart defaults are missing");
});

test("a UPI fleet default edits its values-<cluster>.yaml", async ({ page }) => {
  await open(page, `/clusters/${encodeURIComponent(UPI)}/addons`);
  const metrics = page.getByTestId("installed-orca-metrics");
  await metrics.getByRole("button", { name: /^metrics/ }).click();
  await expect(metrics.getByText("defaults/upi/metrics/values-ocp4-dok-site1.yaml").first()).toBeVisible();
  await expect(metrics.getByTestId("value-row-clusterName")).toContainText("cluster-wide");
});

test("the hub, the destinations list and the lints", async ({ page }) => {
  await open(page, "/clusters/hub/addons");
  await expect(page.getByTestId("installed-falcon-hub-reporter")).toBeVisible();
  await expect(page.getByText("Upgrade check")).toHaveCount(0);

  await open(page, "/destinations");
  await page.getByRole("group", { name: "Kind" }).getByRole("button", { name: /UPI/ }).click();
  await expect(page.locator("tbody tr")).toHaveCount(2);

  await open(page, "/lints");
  await page.getByRole("group", { name: "Severity" }).getByRole("button", { name: /error/ }).click();
  await expect(page.locator("tbody tr").first()).toContainText("repourl-missing");
});
