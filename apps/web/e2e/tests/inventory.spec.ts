/**
 * Inventory Management (mocked; docs/notes/2026-11-13-inventory-management-api.md,
 * ADR-0057): each MCE's available Agents by pool, as server-scan counts them;
 * a pool's servers with their locks; the add-server runs, whose author is
 * never guessed; adding servers by count or by name, sent once and never
 * retried. Everyone signed in reads it from the sidebar; only admins add.
 */

import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go, held } from "../fixtures/api-handlers";
import { DONOR, FREE, LOCKED, OVERVIEW, R650, SITE1_A, STARTED, off, setUpInventory } from "../fixtures/inventory";

const nav = (page: Page) => page.getByRole("navigation", { name: "Main" });
const card = (page: Page, mce: string) => page.locator(`section[data-mce="${mce}"]`);
const pool = (page: Page, infraEnv: string) => card(page, SITE1_A).locator(`tr[data-pool="${infraEnv}"]`);
const dialog = (page: Page) => page.getByTestId("add-servers-dialog");

async function openAdd(page: Page) {
  await pool(page, R650).getByRole("button", { name: `Add servers to ${R650}` }).click();
  await expect(dialog(page)).toBeVisible();
}

test.describe("Who sees it", () => {
  test("an admin opens it from the sidebar", async ({ page }) => {
    await setUpInventory(page);
    await go(page, "/");
    await nav(page).getByRole("link", { name: "Inventory Management" }).click();
    await expect(page).toHaveURL(/\/inventory$/);
    await expect(page.getByRole("heading", { level: 1, name: "Inventory Management" })).toBeVisible();
  });

  test("a viewer sees the pools and the runs from the sidebar, with no Add", async ({ page }) => {
    const calls = await setUpInventory(page, { viewer: true });
    await go(page, "/");
    await nav(page).getByRole("link", { name: "Inventory Management" }).click();
    await expect(card(page, SITE1_A).getByTestId("mce-available")).toHaveText("6 available");
    await expect(page.getByTestId("run-row")).toHaveCount(2);
    await expect(page.getByRole("button", { name: /Add servers to/ })).toHaveCount(0);
    await expect(page.getByTestId("add-servers-off")).toHaveCount(0);
    await pool(page, R650).getByRole("button", { name: `1 free in server-scan for ${R650}` }).click();
    await expect(page.getByTestId("candidate")).toHaveCount(3);
    expect(calls.starts).toEqual([]);
  });

  test("without server-scan the page says it is not set up", async ({ page }) => {
    await setUpInventory(page, { overview: off });
    await go(page, "/inventory");
    await expect(page.getByTestId("inventory-off")).toContainText("SERVER_SCAN_URL");
  });
});

test.describe("The pools", () => {
  test("each MCE shows its available Agents by pool and hardware, as server-scan counts them", async ({ page }) => {
    await setUpInventory(page);
    await go(page, "/inventory");
    await expect(page.getByTestId("inventory-total")).toContainText("10 available");
    await expect(card(page, SITE1_A).getByTestId("mce-available")).toHaveText("6 available");
    const r650 = pool(page, R650);
    await expect(r650.getByTestId("pool-available")).toContainText("2");
    await expect(r650.getByTestId("pool-available")).toContainText("1 not usable");
    await expect(r650).toContainText("dell PowerEdge R650 ×2");
    await expect(pool(page, "")).toContainText("No InfraEnv");
    await expect(pool(page, "").getByRole("button", { name: /Add servers/ })).toHaveCount(0);
    await expect(card(page, "ocp4-prod-mce-site1-b").getByTestId("mce-infra-envs-error")).toContainText("InfraEnvs unknown");
    await expect(page.getByTestId("quiet-mces")).toContainText("ocp4-prod-mce-site1-c");
  });

  test("a pool's servers show the lock and maintenance, and are read only when opened", async ({ page }) => {
    let reads = 0;
    await setUpInventory(page);
    page.on("request", (r) => { if (r.url().includes("/candidates")) reads += 1; });
    await go(page, "/inventory");
    expect(reads).toBe(0);
    await pool(page, R650).getByRole("button", { name: `1 free in server-scan for ${R650}` }).click();
    const servers = page.getByTestId("candidate");
    await expect(servers).toHaveCount(3);
    await expect(page.locator(`[data-server="${LOCKED}"]`)).toHaveAttribute("data-offered", "false");
    await expect(page.locator(`[data-server="${LOCKED}"]`).getByRole("button", { name: /Not offered: locked by add-server-to-mce/ })).toBeVisible();
    await expect(page.locator(`[data-server="${DONOR}"]`).getByRole("button", { name: "Not offered: in maintenance" })).toBeVisible();
    await expect(servers.getByRole("checkbox")).toHaveCount(0);
  });
});

test.describe("The runs", () => {
  test("say who may have started them, never guessing a pool draw's author", async ({ page }) => {
    await setUpInventory(page);
    await go(page, "/inventory");
    const rows = page.getByTestId("run-row");
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0).getByTestId("run-origin")).toHaveText("herzi or a person");
    await expect(rows.nth(0)).toContainText("waiting for agent");
    await expect(rows.nth(1).getByTestId("run-origin")).toHaveText("Person");
    await expect(rows.nth(1)).toContainText("ServerReservedError");
    await expect(page.getByTestId("runs-running")).toHaveText("1 running");
  });

  test("without the orchestrator the page says why and reads none", async ({ page }) => {
    const overview = { ...OVERVIEW, runs: { available: false, detail: "The workflows orchestrator is not configured (WORKFLOWS_API_URL)." } };
    await setUpInventory(page, { overview });
    await go(page, "/inventory");
    await expect(page.getByTestId("runs-off")).toContainText("WORKFLOWS_API_URL");
    await expect(page.getByTestId("run-row")).toHaveCount(0);
  });
});

test.describe("Adding servers", () => {
  test("by count: the dialog says what it does, sends the count once and closes", async ({ page }) => {
    const calls = await setUpInventory(page);
    await go(page, "/inventory");
    await openAdd(page);
    await expect(dialog(page)).toContainText("Joins the MCE's pool, not one cluster.");
    await expect(dialog(page)).toContainText("One run per server.");
    await expect(dialog(page)).toContainText("Sending again installs more.");
    await expect(page.getByTestId("add-servers-drawable")).toHaveText("1 free in server-scan");
    await dialog(page).getByRole("spinbutton", { name: "How many servers" }).fill("2");
    await dialog(page).getByRole("button", { name: "Add 2" }).click();
    await expect(dialog(page)).toHaveCount(0);
    await expect(page.getByText("2 started")).toBeVisible();
    expect(calls.starts).toEqual([{ count: 2 }]);
  });

  test("by name: only an offered server can be picked", async ({ page }) => {
    const calls = await setUpInventory(page);
    await go(page, "/inventory");
    await openAdd(page);
    await dialog(page).getByRole("tab", { name: "Choose servers" }).click();
    await expect(dialog(page).getByRole("checkbox", { name: `Install ${LOCKED}` })).toBeDisabled();
    await expect(dialog(page).getByRole("button", { name: "Add", exact: true })).toBeDisabled();
    await dialog(page).getByRole("checkbox", { name: `Install ${FREE}` }).click();
    await dialog(page).getByRole("button", { name: "Add 1" }).click();
    await expect(dialog(page)).toHaveCount(0);
    expect(calls.starts).toEqual([{ server_names: [FREE] }]);
  });

  test("the submit is disabled while sending", async ({ page }) => {
    const hold = held();
    const calls = await setUpInventory(page, { start: hold.answer(STARTED) });
    await go(page, "/inventory");
    await openAdd(page);
    await dialog(page).getByRole("button", { name: "Add 1" }).click();
    await expect(dialog(page).getByRole("button", { name: "Starting…" })).toBeDisabled();
    hold.release();
    await expect(dialog(page)).toHaveCount(0);
    expect(calls.starts).toHaveLength(1);
  });

  test("an unanswered start says to look at the runs, and sends nothing more", async ({ page }) => {
    const calls = await setUpInventory(page, {
      start: (route) => fulfillProblem(route, 504, "AMBIGUOUS_WRITE", "sent, no answer: some may have started"),
    });
    await go(page, "/inventory");
    await openAdd(page);
    await dialog(page).getByRole("button", { name: "Add 1" }).click();
    await expect(page.getByTestId("add-servers-error")).toContainText("Look at the runs before sending again");
    await expect(dialog(page).getByRole("button", { name: "Add 1" })).toBeDisabled();
    await expect(dialog(page).getByRole("button", { name: "Close" })).toBeVisible();
    expect(calls.starts).toHaveLength(1);
  });

  test("a refused named server shows day1's reasons", async ({ page }) => {
    await setUpInventory(page, {
      start: (route) =>
        fulfillProblem(route, 422, "VALIDATION_ERROR", "these servers cannot be offered for a named install; reload the list", {
          problems: [`${FREE}: locked by add-server-to-mce`],
        }),
    });
    await go(page, "/inventory");
    await openAdd(page);
    await dialog(page).getByRole("tab", { name: "Choose servers" }).click();
    await dialog(page).getByRole("checkbox", { name: `Install ${FREE}` }).click();
    await dialog(page).getByRole("button", { name: "Add 1" }).click();
    await expect(page.getByTestId("add-servers-error")).toContainText(`${FREE}: locked by add-server-to-mce`);
  });

  test("with adding off there is no Add, and the header says why", async ({ page }) => {
    const overview = { ...OVERVIEW, add_servers: { available: false, detail: "Adding servers is off in this deployment (DAY1_ADD_SERVERS=false)." } };
    await setUpInventory(page, { overview });
    await go(page, "/inventory");
    await expect(pool(page, R650)).toBeVisible();
    await expect(page.getByRole("button", { name: /Add servers to/ })).toHaveCount(0);
    await expect(page.getByTestId("add-servers-off")).toBeVisible();
  });
});
