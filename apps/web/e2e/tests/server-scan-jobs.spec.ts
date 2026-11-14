/**
 * The Server Scan area's Jobs page (mocked;
 * docs/notes/2026-11-13-server-scan-area-api.md §14, ADR-0048's 3.32.0
 * amendment): server-scan's CronJobs in its cards and words, their runs and
 * a pod's log; the feature off, no CronJob, no admin token, and the page's
 * other states.
 */

import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go, held } from "../fixtures/api-handlers";
import { failing, forbidden, off } from "../fixtures/server-scan";
import { JOBS, LOG_TEXT, OPENMANAGE, overview, REDFISH, setUpJobs, UCS } from "../fixtures/server-scan-jobs";

const PAGE = "/server-scan/jobs";
const NO_ADMIN_TOKEN =
  "Jobs needs server-scan's admin token: add the key admin-token to the server-scan Secret and restart day1 (SERVER_SCAN_ADMIN_TOKEN).";
const scanNav = (page: Page) => page.getByRole("navigation", { name: "Server Scan" });
const card = (page: Page, name: string) => page.getByRole("region", { name, exact: true });
const logs = (page: Page) => page.getByTestId("ss-job-logs");

test.describe("The Jobs page", () => {
  test("the sidebar's Jobs, in Activity after Events, opens the page", async ({ page }) => {
    await setUpJobs(page);
    await go(page, "/server-scan");
    await expect(scanNav(page).getByRole("link")).toHaveText(["Sites", "Servers", "Confs", "Events", "Jobs", "Rules & Policies", "Claude", "Architecture"]);
    await expect(scanNav(page)).toContainText("Activity");
    await scanNav(page).getByRole("link", { name: "Jobs" }).click();
    await expect(page).toHaveURL(/\/server-scan\/jobs$/);
    await expect(scanNav(page).getByTestId("area-nav-jobs")).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 1, name: "Jobs" })).toBeVisible();
    const about = page.getByTestId("ss-jobs-about");
    await about.hover();
    await expect(page.locator("[data-slot=tooltip-content][data-open]")).toContainText("like oc create job --from, and read its logs");
  });

  test("a card per CronJob: its schedule, values.yaml flag and runs, newest first, in server-scan's words", async ({ page }) => {
    await setUpJobs(page);
    await go(page, PAGE);
    await expect(page.getByTestId("ss-cronjob").getByRole("heading", { level: 2 })).toHaveText([OPENMANAGE, UCS, REDFISH]);
    const openmanage = card(page, OPENMANAGE);
    await expect(openmanage.getByTestId("ss-cronjob-schedule")).toHaveText("0 6 * * *");
    await expect(openmanage.getByTestId("ss-cronjob-schedule")).toHaveAttribute("title", /^Last scheduled .*\nLast succeeded /);
    await expect(openmanage.getByTestId("ss-cronjob-enabled")).toHaveText("enabled: true");
    await expect(openmanage.getByTestId("ss-cronjob-enabled")).toHaveAttribute("title", "The `enabled` flag for this job in the deployment's values.yaml");
    await expect(openmanage.getByTestId("ss-job-state")).toHaveText(["succeeded", "failed", "succeeded"]);
    await expect(openmanage.getByTestId("ss-job-time").first()).toHaveText("2 hours ago");
    await expect(openmanage.getByTestId("ss-job-time").first()).toHaveAttribute("title", /^Created .*\nStarted .*\nFinished /);
    // A run started by hand says so, and who server-scan says started it
    const ucs = card(page, UCS);
    await expect(ucs.getByTestId("ss-job-state")).toHaveText("active");
    await expect(ucs.getByTestId("ss-job")).toContainText("by hand (api-token-admin)");
    await expect(openmanage).not.toContainText("by hand");
    // Switched off in values.yaml: not deployed, dimmed
    const redfish = card(page, REDFISH);
    await expect(redfish.getByTestId("ss-cronjob-enabled")).toHaveText("enabled: false");
    await expect(redfish.getByTestId("ss-cronjob-empty")).toHaveText("Not deployed: it is switched off in values.yaml.");
    await expect(redfish).toHaveClass(/opacity-70/);
    await expect(page.getByTestId("ss-jobs-intro")).not.toContainText("simulated");
  });

  test("a pod's log: its last 500 lines, Refresh, Close and Escape", async ({ page }) => {
    const { logReads } = await setUpJobs(page);
    await go(page, PAGE);
    const button = card(page, OPENMANAGE).getByRole("button", { name: "Logs · x7k2p · Failed" });
    await button.click();
    await expect(logs(page)).toBeVisible();
    await expect(logs(page).getByRole("heading")).toHaveText(`${OPENMANAGE}-29385720-x7k2p`);
    await expect(logs(page)).toContainText(`${OPENMANAGE}-29385720`);
    await expect(page.getByTestId("ss-job-logs-caption")).toHaveText("Last 500 lines.");
    await expect(page.getByTestId("ss-job-logs-text")).toHaveText(LOG_TEXT);
    // The open log's button is marked pressed (behind the modal, so by CSS, not by role)
    await expect(page.locator('[data-testid="ss-job"] button[aria-pressed="true"]')).toHaveText("Logs · x7k2p · Failed");
    const before = logReads();
    await logs(page).getByRole("button", { name: "Refresh" }).click();
    await expect.poll(logReads).toBe(before + 1);
    await logs(page).getByRole("button", { name: "Close" }).click();
    await expect(logs(page)).toHaveCount(0);
    await expect(card(page, OPENMANAGE)).toBeVisible();
    await button.click();
    await expect(logs(page)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(logs(page)).toHaveCount(0);
  });

  test("a running Job's log says it refreshes, and asks for 500 lines", async ({ page }) => {
    await setUpJobs(page);
    await go(page, PAGE);
    const asked = page.waitForRequest(/\/logs\?tail=500$/);
    await card(page, UCS).getByRole("button", { name: "Logs · x7k2p · Running" }).click();
    await asked;
    await expect(page.getByTestId("ss-job-logs-caption")).toHaveText("Last 500 lines, refreshing every 3 s while the job runs.");
  });

  test("a log that is empty, or cannot be read", async ({ page }) => {
    await setUpJobs(page, { logs: { pod: "", tail: 500, text: "" } });
    await go(page, PAGE);
    await card(page, OPENMANAGE).getByRole("button", { name: "Logs · x7k2p · Failed" }).click();
    await expect(page.getByTestId("ss-job-logs-text")).toHaveText("(no output yet)");
    await page.keyboard.press("Escape");
    await page.route(/\/logs\?/, (route) => fulfillProblem(route, 404, "NOT_FOUND", "server-scan: No such Job or pod for that CronJob."));
    await card(page, UCS).getByRole("button", { name: "Logs · x7k2p · Running" }).click();
    await expect(page.getByTestId("ss-job-logs-error")).toHaveText("server-scan: No such Job or pod for that CronJob.");
  });

  test("server-scan's simulated jobs say so", async ({ page }) => {
    await setUpJobs(page, { jobs: overview(JOBS.cronjobs, { backend: "fake" }) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-jobs-intro")).toContainText("This deployment uses simulated jobs.");
  });
});

test.describe("The Jobs page's states", () => {
  test("skeleton cards until the answer comes", async ({ page }) => {
    const answer = held();
    await setUpJobs(page, { jobs: answer.answer(JOBS) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-jobs-loading")).toBeVisible();
    answer.release();
    await expect(page.getByTestId("ss-cronjob")).toHaveCount(3);
    await expect(page.getByTestId("ss-jobs-loading")).toHaveCount(0);
  });

  test("the feature off in server-scan: its words", async ({ page }) => {
    await setUpJobs(page, { jobs: { enabled: false, backend: "off", namespace: null, cronjobs: [] } });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-jobs-feature-off")).toContainText("Running jobs from the UI is not enabled on this deployment.");
    await expect(page.getByTestId("ss-cronjob")).toHaveCount(0);
  });

  test("no CronJob: server-scan's words", async ({ page }) => {
    await setUpJobs(page, { jobs: overview([]) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-jobs-empty")).toHaveText("No triggerable CronJobs found.");
  });

  test("without server-scan's admin token the page says which key to add", async ({ page }) => {
    await setUpJobs(page, { jobs: (route) => fulfillProblem(route, 501, "FEATURE_DISABLED", NO_ADMIN_TOKEN, { setting: "SERVER_SCAN_ADMIN_TOKEN" }) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-jobs-off")).toContainText("Jobs is not set up");
    await expect(page.getByTestId("ss-jobs-off")).toContainText(NO_ADMIN_TOKEN);
    await expect(page.getByTestId("ss-cronjob")).toHaveCount(0);
  });

  test("without server-scan the page says how to set it up", async ({ page }) => {
    await setUpJobs(page, { jobs: off, sites: off });
    await page.goto(PAGE);
    await expect(page.getByTestId("ss-off")).toContainText("serverScan.url");
  });

  test("a viewer is told it is for admins", async ({ page }) => {
    await setUpJobs(page, { jobs: forbidden, sites: forbidden, viewer: true });
    await page.goto(PAGE);
    await expect(page.getByTestId("ss-forbidden")).toBeVisible();
  });

  test("server-scan failing: its problem", async ({ page }) => {
    await setUpJobs(page, { jobs: failing });
    await go(page, PAGE);
    await expect(page.getByRole("alert").filter({ hasText: "The jobs could not be loaded from server-scan" })).toContainText("server-scan unreachable");
  });
});
