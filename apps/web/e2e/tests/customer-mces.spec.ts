/**
 * Customer MCEs (mocked; ADR-0067, ADR-0018 and its 2026-11-24 amendment):
 * each site's Customer MCEs, no default mastertag, each row opening its MCE's
 * servers in Inventory Management; and Create MCE, a preview of the vision.
 * Its inputs work, the name, zones and steps follow them, and Create stays
 * disabled with its reason: nothing is sent or written.
 */

import { test, expect, type Page } from "@playwright/test";
import { go, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import { MCES, SITE1_A } from "../fixtures/overview";

const REASON = "Not available yet: a Customer MCE is installed by hand today (the platform's procedure 12); no workflow creates one.";

/** Sign in (as a viewer if asked) with day1's MCEs: site1's two Customer MCEs (a, b) and az1 seed, site2's one (a). */
async function openMces(page: Page, { viewer = false } = {}) {
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/") && request.method() !== "GET") writes.push(`${request.method()} ${request.url()}`);
  });
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/mces", (route) => json(route, MCES));
  await go(page, "/mces");
  return { writes };
}

async function chooseSite(page: Page, site: string) {
  await page.getByTestId("mce-preview-site").click();
  await page.getByRole("option", { name: site, exact: true }).click();
}

test.describe("Customer MCEs", () => {
  test("show each MCE's env, hub version and clusters, no default mastertag", async ({ page }) => {
    await openMces(page);

    const headers = page.getByTestId("mce-site").first().getByRole("columnheader");
    await expect(headers).toHaveText(["MCE", "Env", "Hub version", "Clusters", "Servers"]);
    await expect(page.getByText("Default mastertag")).toHaveCount(0);
  });

  test("each row opens its MCE's servers in Inventory Management", async ({ page }) => {
    await openMces(page);

    const row = page.locator(`[data-mce="${SITE1_A}"]`);
    const link = row.getByRole("link", { name: `${SITE1_A}: its servers in Inventory Management` });
    await expect(link).toHaveAttribute("href", `/inventory?mce=${SITE1_A}`);
    // Anywhere on the row: here by its clusters count, far from the name
    const box = (await row.boundingBox())!;
    await row.click({ position: { x: box.width - 80, y: box.height / 2 } });
    await expect(page).toHaveURL(new RegExp(`/inventory\\?mce=${SITE1_A}$`));
  });

  test("a viewer has no Create MCE", async ({ page }) => {
    await openMces(page, { viewer: true });

    await expect(page.getByTestId("admins-only")).toBeVisible();
    await expect(page.getByTestId("create-mce")).toHaveCount(0);
  });
});

test.describe("Create MCE, a preview", () => {
  test("names the next free letter and lays the VMs over the site's zones as the choices change", async ({ page }) => {
    const { writes } = await openMces(page);

    const open = page.getByTestId("create-mce");
    await expect(open).toHaveAccessibleName("Create MCE Preview");
    await open.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: /Create a Customer MCE/ })).toContainText("Preview");
    await expect(dialog).toContainText("nothing here is sent or written");

    // site1 holds a and b, and the az1 seed: one zone, a master and a worker in it
    const name = dialog.getByTestId("mce-preview-name");
    await expect(name).toHaveText("ocp4-prod-mce-site1-c");
    await expect(dialog.getByTestId("mce-preview-zone")).toHaveCount(1);
    await expect(dialog.getByTestId("mce-preview-zone")).toHaveAttribute("data-zone", "az1");
    await expect(dialog.getByTestId("mce-preview-totals")).toHaveText("2 VMs · 1 master, 1 worker · 64 vCPU · 256 GiB");
    await expect(dialog.getByTestId("mce-preview-few-zones")).toContainText("site1 has a seed in 1 zone so far");

    await dialog.getByRole("button", { name: "One worker more per zone" }).click();
    await expect(dialog.getByTestId("mce-preview-totals")).toHaveText("3 VMs · 1 master, 2 workers · 96 vCPU · 384 GiB");

    await dialog.getByRole("radio", { name: "test" }).click();
    await expect(name).toHaveText("ocp4-test-mce-site1-c");
    const steps = dialog.getByTestId("mce-preview-steps");
    await expect(steps).toContainText("redbull.io/mce=ocp4-test-mce-site1-c");
    await expect(steps).toContainText("sites/site1/mces/ocp4-test-mce-site1-c/");

    await dialog.getByTestId("mce-preview-version").fill("latest");
    await expect(dialog.getByTestId("mce-preview-problem")).toHaveText("An OpenShift version, such as 4.20 or 4.20.44.");
    await dialog.getByTestId("mce-preview-version").fill("4.20");
    await expect(dialog.getByTestId("mce-preview-problem")).toHaveCount(0);
    await expect(steps).toContainText("A standalone OpenShift 4.20 on those VMs");

    // site2 has no seed: no zone to put a VM in
    await chooseSite(page, "site2");
    await expect(name).toHaveText("ocp4-test-mce-site2-b");
    await expect(dialog.getByTestId("mce-preview-zone")).toHaveCount(0);
    await expect(dialog.getByTestId("mce-preview-no-zones")).toContainText("site2 has no seed yet");

    await expect(dialog.getByTestId("mce-preview-acceptance")).toContainText("No two of its VMs on one hypervisor");
    expect(writes).toEqual([]);
  });

  test("Create is disabled, with its reason, and Close leaves nothing behind", async ({ page }) => {
    const { writes } = await openMces(page);
    await page.getByTestId("create-mce").click();
    const dialog = page.getByRole("dialog");

    const create = dialog.getByTestId("mce-preview-create");
    await expect(create).toBeDisabled();
    await expect(create).toHaveAccessibleDescription(REASON);
    await expect(dialog.getByTestId("mce-preview-reason")).toHaveText(REASON);

    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(dialog).toHaveCount(0);
    expect(writes).toEqual([]);
  });
});
