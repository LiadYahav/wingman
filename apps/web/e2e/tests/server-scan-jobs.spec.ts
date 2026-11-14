/**
 * The Server Scan area's Jobs page (mocked;
 * docs/notes/2026-11-13-server-scan-area-api.md §15, ADR-0048's 3.32.0
 * amendment): server-scan's CronJobs in its cards and words, their runs and
 * a pod's log; Run job, the area's second write (asked first, sent once,
 * server-scan's 409 and 404, unanswered, refused); the feature off, no
 * CronJob, no admin token, and the page's other states.
 */

import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go, held } from "../fixtures/api-handlers";
import { failing, forbidden, off } from "../fixtures/server-scan";
import { IDRAC_WARNING, JOBS, LOG_TEXT, mockRun, OPENMANAGE, overview, REDFISH, setUpJobs, STARTED, UCS } from "../fixtures/server-scan-jobs";

const PAGE = "/server-scan/jobs";
const NO_ADMIN_TOKEN =
  "Jobs needs server-scan's admin token: add the key admin-token to the server-scan Secret and restart day1 (SERVER_SCAN_ADMIN_TOKEN).";
const scanNav = (page: Page) => page.getByRole("navigation", { name: "Server Scan" });
const card = (page: Page, name: string) => page.getByRole("region", { name, exact: true });
const logs = (page: Page) => page.getByTestId("ss-job-logs");
const dialog = (page: Page) => page.getByTestId("ss-run-dialog");
const runJob = (page: Page, name: string) => card(page, name).getByTestId("ss-run-job");
const confirm = (page: Page) => dialog(page).getByRole("button", { name: "Run job" });

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
    await expect(logs(page)).toHaveAccessibleName(`${OPENMANAGE}-29385720-x7k2p`);
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

test.describe("Run job", () => {
  test("asks first, in server-scan's words and with the CronJob's warning, then sends once and opens the new run's log", async ({ page }) => {
    const { reads } = await setUpJobs(page);
    const sent = await mockRun(page);
    await go(page, PAGE);
    await expect(page.getByTestId("ss-cronjob")).toHaveCount(3);
    await runJob(page, OPENMANAGE).click();
    await expect(dialog(page)).toHaveAccessibleName("Run this job now?");
    await expect(dialog(page).getByRole("heading")).toHaveText("Run this job now?");
    await expect(dialog(page)).toContainText(OPENMANAGE);
    await expect(dialog(page)).toContainText("It starts a real Job from the CronJob's template and runs exactly as scheduled.");
    await expect(dialog(page).getByRole("note")).toHaveText(IDRAC_WARNING);
    expect(sent()).toBe(0);
    const before = reads();
    const posted = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/api/day1/server-scan/jobs/${OPENMANAGE}/run`));
    await confirm(page).click();
    await posted;
    await expect(dialog(page)).toHaveCount(0);
    expect(sent()).toBe(1);
    await expect.poll(reads).toBeGreaterThan(before);
    await expect(logs(page).getByRole("heading")).toHaveText(STARTED.pods[0]!.name);
  });

  test("Cancel sends nothing; a CronJob without a warning has none", async ({ page }) => {
    await setUpJobs(page, { jobs: overview([{ ...JOBS.cronjobs[0]!, warning: null }]) });
    const sent = await mockRun(page);
    await go(page, PAGE);
    await runJob(page, OPENMANAGE).click();
    await expect(dialog(page).getByRole("note")).toHaveCount(0);
    await dialog(page).getByRole("button", { name: "Cancel" }).click();
    await expect(dialog(page)).toHaveCount(0);
    expect(sent()).toBe(0);
  });

  test("is off, with why as its tooltip, while a Job runs and for a CronJob not deployed", async ({ page }) => {
    await setUpJobs(page);
    const sent = await mockRun(page);
    await go(page, PAGE);
    await expect(runJob(page, OPENMANAGE)).toBeEnabled();
    await expect(runJob(page, UCS)).toBeDisabled();
    await expect(runJob(page, UCS)).toHaveAttribute("title", "A Job of this CronJob is already running");
    await expect(runJob(page, REDFISH)).toBeDisabled();
    await expect(runJob(page, REDFISH)).toHaveAttribute("title", "Not deployed: turn it on in values.yaml first");
    await runJob(page, UCS).click({ force: true });
    await expect(dialog(page)).toHaveCount(0);
    expect(sent()).toBe(0);
  });

  test("is sent once: the submit is off while sending, and the dialog stays until the answer", async ({ page }) => {
    await setUpJobs(page);
    const answer = held();
    const sent = await mockRun(page, answer.answer(STARTED));
    await go(page, PAGE);
    await runJob(page, OPENMANAGE).click();
    await confirm(page).dblclick();
    await expect(dialog(page).getByRole("button", { name: "Starting…" })).toBeDisabled();
    await expect(dialog(page).getByRole("button", { name: "Cancel" })).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toBeVisible();
    answer.release();
    await expect(dialog(page)).toHaveCount(0);
    expect(sent()).toBe(1);
  });

  test("server-scan's 409 and 404, in its words", async ({ page }) => {
    await setUpJobs(page);
    const words = `server-scan: ${OPENMANAGE} already has an unfinished Job (${OPENMANAGE}-manual-a1b2c3).`;
    await mockRun(page, (route) => fulfillProblem(route, 409, "JOB_ALREADY_RUNNING", words));
    await go(page, PAGE);
    await runJob(page, OPENMANAGE).click();
    await confirm(page).click();
    await expect(page.getByTestId("ss-run-error")).toHaveText(words);
    await expect(confirm(page)).toBeEnabled();
    await page.route("**/api/day1/server-scan/jobs/*/run", (route) =>
      fulfillProblem(route, 404, "NOT_FOUND", "server-scan: Running jobs from the UI is not enabled on this deployment.")
    );
    await confirm(page).click();
    await expect(page.getByTestId("ss-run-error")).toHaveText("server-scan: Running jobs from the UI is not enabled on this deployment.");
  });

  test("unanswered: it says to look at the runs, Run job stays off, and the card keeps the line", async ({ page }) => {
    await setUpJobs(page);
    const detail = `starting a run of ${OPENMANAGE} was sent to server-scan but no answer came back (ReadTimeout): it may have changed. Look at the runs of ${OPENMANAGE} before starting it again.`;
    const sent = await mockRun(page, (route) => fulfillProblem(route, 504, "AMBIGUOUS_WRITE", detail));
    await go(page, PAGE);
    await runJob(page, OPENMANAGE).click();
    await confirm(page).click();
    await expect(page.getByTestId("ss-run-error")).toHaveText(detail);
    await expect(confirm(page)).toBeDisabled();
    await dialog(page).getByRole("button", { name: "Cancel" }).click();
    await expect(card(page, OPENMANAGE).getByTestId("ss-run-unconfirmed")).toContainText("Look at the runs below before starting it again.");
    await expect(card(page, UCS).getByTestId("ss-run-unconfirmed")).toHaveCount(0);
    expect(sent()).toBe(1);
  });

  test("server-scan refusing the admin token: day1's words", async ({ page }) => {
    await setUpJobs(page);
    const detail = `server-scan refused Wingman's admin token (403) starting a run of ${OPENMANAGE}: check SERVER_SCAN_ADMIN_TOKEN`;
    await mockRun(page, (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", detail));
    await go(page, PAGE);
    await runJob(page, OPENMANAGE).click();
    await confirm(page).click();
    await expect(page.getByTestId("ss-run-error")).toHaveText(detail);
    await expect(card(page, OPENMANAGE).getByTestId("ss-run-unconfirmed")).toHaveCount(0);
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
