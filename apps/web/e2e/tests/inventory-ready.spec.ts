/**
 * Inventory Management's Ready, Needs fix and Total, collapsing an MCE, and
 * installing a server that needs a fix (mocked; ADR-0057's 3.38.0 amendment,
 * docs/notes/2026-11-13-inventory-management-api.md). A pool draw never
 * sends the workflow's `allow_unhealthy`; a named server that needs a fix is
 * sent with it only after the confirmation step, and Back sends nothing.
 */

import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go } from "../fixtures/api-handlers";
import { FREE, LOCKED, OVERVIEW, R650, SICK, SITE1_A, SITE1_B, setUpInventory } from "../fixtures/inventory";

const card = (page: Page, mce: string) => page.locator(`section[data-mce="${mce}"]`);
const pool = (page: Page, infraEnv: string) => card(page, SITE1_A).locator(`tr[data-pool="${infraEnv}"]`);
const dialog = (page: Page) => page.getByTestId("add-servers-dialog");
const tooltip = (page: Page) => page.locator("[data-slot=tooltip-content][data-open]");

async function chooseServers(page: Page, ...names: string[]) {
  await pool(page, R650).getByRole("button", { name: `Install servers into ${R650}` }).click();
  await dialog(page).getByRole("tab", { name: "Choose servers" }).click();
  for (const name of names) await dialog(page).getByRole("checkbox", { name: `Install ${name}` }).click();
}

test.describe("Each MCE collapses", () => {
  test("its title hides its pools, keeps its counts, and the browser remembers it", async ({ page }) => {
    await setUpInventory(page);
    await go(page, "/inventory");
    const toggle = card(page, SITE1_A).getByRole("button", { name: SITE1_A, exact: true });
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(card(page, SITE1_A).getByRole("table")).toBeHidden();
    await expect(card(page, SITE1_A).getByTestId("mce-available")).toHaveText("6 available");
    await expect(card(page, SITE1_A).getByTestId("mce-total")).toContainText("8 total");
    await expect(card(page, SITE1_B).getByRole("table")).toBeVisible();

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(card(page, SITE1_A).getByTestId("mce-toggle")).toHaveAttribute("aria-expanded", "false");
    await expect(card(page, SITE1_A).getByRole("table")).toBeHidden();
    await expect(card(page, SITE1_B).getByTestId("mce-toggle")).toHaveAttribute("aria-expanded", "true");
  });

  test("by keyboard: Enter and Space toggle it", async ({ page }) => {
    await setUpInventory(page);
    await go(page, "/inventory");
    const toggle = card(page, SITE1_B).getByTestId("mce-toggle");
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("Space");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(card(page, SITE1_B).getByRole("table")).toBeVisible();
  });
});

test.describe("Ready, Needs fix and Total", () => {
  test("each pool shows them, the MCE its total, and each column says what it means", async ({ page }) => {
    await setUpInventory(page);
    await go(page, "/inventory");
    const r650 = pool(page, R650);
    await expect(r650.getByTestId("pool-ready")).toHaveText("1");
    await expect(r650.getByTestId("pool-needs-fix")).toHaveText("1");
    await expect(r650.getByTestId("pool-total")).toHaveText("4");
    const none = pool(page, "");
    await expect(none.getByTestId("pool-ready")).toHaveText("—");
    await expect(none.getByTestId("pool-needs-fix")).toHaveText("—");
    await expect(none.getByTestId("pool-total")).toHaveText("4");
    await card(page, SITE1_A).getByRole("button", { name: "About Total" }).hover();
    await expect(tooltip(page)).toContainText("Available + Ready + Needs fix");
    await expect(tooltip(page)).toContainText("Locked, in-maintenance and contested servers are not counted");
    await card(page, SITE1_A).getByRole("button", { name: "About the total" }).hover();
    await expect(tooltip(page)).toContainText("6 available + 1 ready + 1 needs a fix");
    await card(page, SITE1_A).getByRole("button", { name: "About Ready" }).hover();
    await expect(tooltip(page)).toContainText("a run may still refuse one");
  });

  test("either count opens the pool's servers in their groups, a server that needs a fix with why", async ({ page }) => {
    await setUpInventory(page);
    await go(page, "/inventory");
    const needsFix = pool(page, R650).getByRole("button", { name: `1 needs a fix for ${R650}` });
    await needsFix.click();
    await expect(needsFix).toHaveAttribute("aria-expanded", "true");
    await expect(pool(page, R650).getByRole("button", { name: `1 ready in server-scan for ${R650}` })).toHaveAttribute("aria-expanded", "true");
    const groups = page.getByTestId("candidate-group");
    // The headings are set in capitals: compare what is read, ignoring case
    await expect(groups).toHaveText([/^ready · 1$/i, /^needs fix · 1$/i, /^not offered · 2$/i], { useInnerText: true });
    await expect(page.locator(`[data-server="${SICK}"]`).getByTestId("candidate-problems")).toHaveText("health CRITICAL · BMC unreachable");
    await expect(page.locator(`[data-server="${FREE}"]`).getByTestId("candidate-problems")).toHaveCount(0);
    await needsFix.click();
    await expect(page.getByTestId("candidate")).toHaveCount(0);
  });
});

test.describe("Installing a server that needs a fix", () => {
  test("a pool draw never sends allow_unhealthy", async ({ page }) => {
    const calls = await setUpInventory(page);
    await go(page, "/inventory");
    await pool(page, R650).getByRole("button", { name: `Install servers into ${R650}` }).click();
    await expect(page.getByTestId("add-servers-ready")).toHaveText("1 ready in server-scan · 1 needs a fix: choose by name");
    await dialog(page).getByRole("spinbutton", { name: "How many servers" }).fill("2");
    await dialog(page).getByRole("button", { name: "Install 2", exact: true }).click();
    await expect(dialog(page)).toHaveCount(0);
    expect(calls.starts).toEqual([{ count: 2 }]);
  });

  test("a ready server is installed at once, without the waiver", async ({ page }) => {
    const calls = await setUpInventory(page);
    await go(page, "/inventory");
    await chooseServers(page, FREE);
    await dialog(page).getByRole("button", { name: "Install 1", exact: true }).click();
    await expect(dialog(page)).toHaveCount(0);
    expect(calls.starts).toEqual([{ server_names: [FREE] }]);
  });

  test("naming one asks first, says what is waived and what still applies, and sends the waiver once confirmed", async ({ page }) => {
    const calls = await setUpInventory(page);
    await go(page, "/inventory");
    await chooseServers(page, SICK);
    await expect(dialog(page).getByRole("checkbox", { name: `Install ${LOCKED}` })).toBeDisabled();
    await expect(page.getByTestId("add-servers-needs-fix")).toContainText("1 needs a fix: you confirm its health checks are waived next");
    await dialog(page).getByRole("button", { name: "Install 1…" }).click();
    const confirm = page.getByTestId("waiver-confirm");
    await expect(dialog(page).getByRole("heading", { name: "Install with health checks waived?" })).toBeVisible();
    await expect(confirm.getByTestId("waiver-server")).toHaveText([`${SICK}health CRITICAL · BMC unreachable`]);
    await expect(confirm).toContainText("The workflow waives its health checks for this server");
    await expect(confirm).toContainText("Its safety checks still apply");
    expect(calls.starts).toEqual([]);
    await dialog(page).getByRole("button", { name: "Install with checks waived" }).click();
    await expect(dialog(page)).toHaveCount(0);
    expect(calls.starts).toEqual([{ server_names: [SICK], allow_unhealthy: true }]);
  });

  test("with a ready server beside it, the confirmation says the waiver covers both", async ({ page }) => {
    const calls = await setUpInventory(page);
    await go(page, "/inventory");
    await chooseServers(page, FREE, SICK);
    await dialog(page).getByRole("button", { name: "Install 2…" }).click();
    await expect(page.getByTestId("waiver-confirm")).toContainText("all 2 servers of this request, the 1 ready too");
    await expect(page.getByTestId("waiver-server")).toHaveCount(1);
    await dialog(page).getByRole("button", { name: "Install with checks waived" }).click();
    await expect(dialog(page)).toHaveCount(0);
    expect(calls.starts).toEqual([{ server_names: [FREE, SICK], allow_unhealthy: true }]);
  });

  test("Back returns to the choice and Cancel closes: nothing is sent", async ({ page }) => {
    const calls = await setUpInventory(page);
    await go(page, "/inventory");
    await chooseServers(page, SICK);
    await dialog(page).getByRole("button", { name: "Install 1…" }).click();
    await dialog(page).getByRole("button", { name: "Back" }).click();
    await expect(page.getByTestId("waiver-confirm")).toHaveCount(0);
    await expect(dialog(page).getByRole("checkbox", { name: `Install ${SICK}` })).toBeChecked();
    await dialog(page).getByRole("button", { name: "Cancel" }).click();
    await expect(dialog(page)).toHaveCount(0);
    expect(calls.starts).toEqual([]);
  });

  test("day1's 422 is shown on the confirmation, which sends nothing more", async ({ page }) => {
    const calls = await setUpInventory(page, {
      start: (route) =>
        fulfillProblem(route, 422, "VALIDATION_ERROR", "the orchestrator refused adding 1 server(s)", {
          problems: ["allow_unhealthy: extra inputs are not permitted"],
        }),
    });
    await go(page, "/inventory");
    await chooseServers(page, SICK);
    await dialog(page).getByRole("button", { name: "Install 1…" }).click();
    await dialog(page).getByRole("button", { name: "Install with checks waived" }).click();
    await expect(page.getByTestId("add-servers-error")).toContainText("allow_unhealthy: extra inputs are not permitted");
    await expect(page.getByTestId("waiver-confirm")).toBeVisible();
    expect(calls.starts).toEqual([{ server_names: [SICK], allow_unhealthy: true }]);
  });

  test("a run that waived checks says so, and which", async ({ page }) => {
    const waived = {
      workflow_id: `add-server-to-mce-${SITE1_A}_${SICK.toLowerCase()}`, status: "running", started_at: "2026-11-13T12:00:00+00:00",
      closed_at: null, mce: SITE1_A, infra_env: null, slot: null, server_name: SICK, server_id: null, origin: "named" as const,
      phase: "waiting-for-agent", error: null, health_checks_waived: ["server-scan-health: overall CRITICAL", "bmc-reachable: server-scan cannot reach its BMC"],
    };
    await setUpInventory(page, { runs: { runs: [waived] }, overview: OVERVIEW });
    await go(page, "/inventory");
    const marker = page.getByTestId("run-row").getByTestId("run-waived");
    await expect(marker).toHaveText("checks waived");
    await marker.hover();
    await expect(tooltip(page)).toContainText("Installed with health checks waived: server-scan-health: overall CRITICAL; bmc-reachable");
  });
});
