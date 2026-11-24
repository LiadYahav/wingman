/**
 * Inventory Management, one MCE at a time (mocked; ADR-0057's 2026-11-24
 * amendment): the MCE picker, by site, kept in the URL (`?mce=`) and per
 * viewer; the InfraEnvs picked, several at once, kept when the MCE changes
 * (a pool's name carries no hub), those an MCE lacks reported and kept; the
 * table's search, zone, size and "only with servers" filters, its order and
 * its sticky header; and the runs, every MCE's and every InfraEnv's, never
 * filtered by what is picked.
 */

import { test, expect, type Page } from "@playwright/test";
import { go } from "../fixtures/api-handlers";
import { OVERVIEW, SITE1_A, SITE1_B, SITE1_C, UNLABELLED, setUpInventory } from "../fixtures/inventory";
import type { InventoryOverview, MceInventory, PoolCount } from "../../types/inventory";

const FLAVORS = ["c200", "g12", "r760"];
const SIZES = ["mtl", "kv32"];
const ZONES = ["az1", "az2", "az3", "az4"];
/** Every flavor, size and zone: 24 InfraEnvs under the platform's convention. */
const CONVENTION = FLAVORS.flatMap((flavor) => SIZES.flatMap((size) => ZONES.map((zone) => `${flavor}-${size}-${zone}`)));
const SITE1_B_POOLS = ["c200-mtl-az1", "c200-mtl-az2", "r760-mtl-az1"];

const poolOf = (infra_env: string | null, available = 0, overrides: Partial<PoolCount> = {}): PoolCount => ({
  infra_env, available, usable: available, ready: 0, needs_fix: 0, total: available, hardware: [], server_prefix: null,
  label_problems: [], used: [], herzi: { ignored: false, paused: false, blocked_until: null, no_hardware_since: null }, ...overrides,
});

/** site1-a with 24 InfraEnvs on the convention, one before it and the servers no one InfraEnv names; site1-b with 3. */
function fleet(): InventoryOverview {
  const [a, b, c] = OVERVIEW.mces;
  const available = (name: string) => (name === "r760-mtl-az3" ? 9 : name.startsWith("g12-") ? 1 : 0);
  const siteA: MceInventory = {
    ...a,
    pools: [
      ...CONVENTION.map((name) => (name === "c200-kv32-az4" ? poolOf(name, 0, { ready: 2, total: 2 }) : poolOf(name, available(name)))),
      poolOf(UNLABELLED),
      poolOf(null, 4),
    ],
  };
  const siteB: MceInventory = { ...b, pools: SITE1_B_POOLS.map((name) => poolOf(name)) };
  return { ...OVERVIEW, mces: [siteA, siteB, c] };
}

const panel = (page: Page, mce: string) => page.locator(`section[data-mce="${mce}"]`);
const rows = (page: Page) => page.getByTestId("pool-row");
const choices = (page: Page) => page.getByTestId("infra-env-choices");
const picked = (page: Page) => page.getByTestId("picked-infra-env");

async function pickMce(page: Page, mce: string) {
  await page.getByTestId("mce-picker").click();
  await page.getByRole("option").filter({ has: page.getByText(mce, { exact: true }) }).click();
  await expect(panel(page, mce)).toBeVisible();
}

/** Open the InfraEnv picker, check each name, and close it. */
async function pickInfraEnvs(page: Page, ...names: string[]) {
  await page.getByTestId("infra-env-picker").click();
  for (const name of names) await choices(page).locator(`[data-infra-env="${name}"]`).click();
  await page.keyboard.press("Escape");
  await expect(choices(page)).toHaveCount(0);
}

const stored = (page: Page) => page.evaluate(() => localStorage.getItem("wingman-inventory-view"));

test.describe("The MCE picker", () => {
  test("shows one MCE at a time, by site, kept in the URL and by this browser", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, "/inventory");
    await expect(panel(page, SITE1_A)).toBeVisible();
    await expect(page.getByTestId("mce-panel")).toHaveCount(1);
    await page.getByTestId("mce-picker").click();
    await expect(page.getByRole("group").filter({ hasText: "site1" }).getByRole("option")).toHaveCount(3);
    await page.keyboard.press("Escape");

    await pickMce(page, SITE1_B);
    await expect(page).toHaveURL(new RegExp(`/inventory\\?mce=${SITE1_B}$`));
    await expect(rows(page)).toHaveCount(3);
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(panel(page, SITE1_B)).toBeVisible();
    await page.goto("/inventory", { waitUntil: "domcontentloaded" });
    await expect(panel(page, SITE1_B)).toBeVisible(); // remembered
    expect(JSON.parse((await stored(page)) ?? "{}")).toEqual({ mce: SITE1_B, infraEnvs: [] });
  });

  test("?mce= opens that MCE; an unknown one shows the first, quietly saying so", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, `/inventory?mce=${SITE1_C}`);
    await expect(panel(page, SITE1_C).getByTestId("mce-no-pools")).toBeVisible();
    await page.goto("/inventory?mce=ocp4-prod-mce-gone", { waitUntil: "domcontentloaded" });
    await expect(panel(page, SITE1_A)).toBeVisible();
    await expect(page.getByTestId("mce-unknown")).toHaveText(`The day1 repo has no MCE named ocp4-prod-mce-gone: showing ${SITE1_A}.`);
  });

  test("the header's Install servers opens on the MCE shown; a row's Install on its pool", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, `/inventory?mce=${SITE1_B}`);
    await page.getByTestId("install-servers").click();
    const dialog = page.getByTestId("add-servers-dialog");
    await expect(dialog.getByRole("combobox", { name: "MCE" })).toContainText(SITE1_B);
    await expect(dialog.getByRole("combobox", { name: "InfraEnv" })).toBeEnabled();
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await page.getByRole("button", { name: "Install servers into r760-mtl-az1" }).click();
    await expect(dialog.getByRole("combobox", { name: "InfraEnv" })).toContainText("r760-mtl-az1");
  });
});

test.describe("The InfraEnvs picked", () => {
  test("several narrow the table, found by a part of the name, and stay in the URL", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, "/inventory");
    await expect(page.getByTestId("pool-count")).toHaveText("25 InfraEnvs");
    await expect(rows(page)).toHaveCount(26); // and the servers no one InfraEnv names
    await page.getByTestId("infra-env-picker").click();
    await choices(page).getByRole("searchbox", { name: "Find an InfraEnv" }).fill("g12-kv32");
    await expect(choices(page).getByRole("checkbox")).toHaveCount(4);
    await choices(page).getByRole("button", { name: "Pick the 4 found" }).click();
    await page.keyboard.press("Escape");

    await expect(page.getByTestId("infra-env-picker")).toHaveAccessibleName("InfraEnvs: 4 InfraEnvs picked");
    await expect(rows(page)).toHaveCount(4);
    await expect(page.getByTestId("pool-count")).toHaveText("4 of 25 InfraEnvs");
    await expect(page).toHaveURL(/infraEnv=g12-kv32-az1,g12-kv32-az2,g12-kv32-az3,g12-kv32-az4/);
    await picked(page).filter({ hasText: "g12-kv32-az2" }).getByRole("button", { name: "Unpick g12-kv32-az2" }).click();
    await expect(rows(page)).toHaveCount(3);
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(rows(page)).toHaveCount(3);
    await page.getByRole("button", { name: "Unpick all" }).click();
    await expect(rows(page)).toHaveCount(26);
    await expect(page).toHaveURL(new RegExp(`/inventory\\?mce=${SITE1_A}$`)); // every InfraEnv: no infraEnv left
  });

  test("switching the MCE keeps them; those it lacks are reported, not lost", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, "/inventory");
    await pickInfraEnvs(page, "c200-mtl-az1", "g12-kv32-az1");
    await expect(rows(page)).toHaveCount(2);

    await pickMce(page, SITE1_B);
    await expect(rows(page)).toHaveCount(1);
    await expect(rows(page).first()).toHaveAttribute("data-pool", "c200-mtl-az1");
    await expect(page.getByTestId("infra-env-missing")).toContainText(`Not on ${SITE1_B}, kept for the other MCEs:`);
    await expect(page.getByTestId("infra-env-missing").getByTestId("picked-infra-env")).toHaveText(["g12-kv32-az1"]);
    await expect(page).toHaveURL(new RegExp(`mce=${SITE1_B}&infraEnv=c200-mtl-az1,g12-kv32-az1`));

    await pickMce(page, SITE1_A);
    await expect(rows(page)).toHaveCount(2);
    await expect(page.getByTestId("infra-env-missing")).toHaveCount(0);
    await page.goto("/inventory", { waitUntil: "domcontentloaded" });
    await expect(rows(page)).toHaveCount(2); // remembered with the MCE
    expect(JSON.parse((await stored(page)) ?? "{}")).toEqual({ mce: SITE1_A, infraEnvs: ["c200-mtl-az1", "g12-kv32-az1"] });
  });

  test("an MCE with none of them says so, and Clear filters shows its pools", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, `/inventory?infraEnv=g12-kv32-az1&mce=${SITE1_B}`);
    await expect(rows(page)).toHaveCount(0);
    await expect(page.getByTestId("pools-none-shown")).toContainText("This MCE has none of the InfraEnvs picked.");
    await page.getByTestId("pools-none-shown").getByRole("button", { name: "Clear filters" }).click();
    await expect(rows(page)).toHaveCount(3);
  });
});

test.describe("The table's filters", () => {
  test("search, zone, size and only with servers combine, and say how many show", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, "/inventory");
    const zone = page.getByRole("group", { name: "Zone filters" });
    const size = page.getByRole("group", { name: "Size filters" });
    await expect(zone.getByRole("button")).toHaveText(["All", "az16", "az26", "az36", "az46"]);
    await expect(size.getByRole("button")).toHaveText(["All", "kv3212", "mtl12"]);

    await page.getByRole("searchbox", { name: "Search the pools by name" }).fill("r760");
    await expect(page.getByTestId("pool-count")).toHaveText("8 of 25 InfraEnvs");
    await zone.getByRole("button", { name: /^az2/ }).click();
    await expect(rows(page)).toHaveCount(2);
    await size.getByRole("button", { name: /^mtl/ }).click();
    await expect(rows(page)).toHaveText([/^r760-mtl-az2/]);
    await page.getByRole("button", { name: "Clear the search" }).click();
    await expect(page.getByTestId("pool-count")).toHaveText("3 of 25 InfraEnvs");

    // A name off the convention is only searchable
    await zone.getByRole("button", { name: "All" }).click();
    await size.getByRole("button", { name: "All" }).click();
    await page.getByRole("searchbox", { name: "Search the pools by name" }).fill("gen12");
    await expect(rows(page)).toHaveCount(1);
    await expect(rows(page).first()).toHaveAttribute("data-pool", UNLABELLED);
    await page.getByRole("searchbox", { name: "Search the pools by name" }).fill("");

    await page.getByTestId("pool-with-servers").click();
    await expect(page.getByTestId("pool-with-servers")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("pool-count")).toHaveText("10 of 25 InfraEnvs"); // g12 ×8, r760-mtl-az3, c200-kv32-az4
    await expect(rows(page)).toHaveCount(11);
  });

  test("hiding every pool offers to clear the filters", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, "/inventory");
    await page.getByRole("searchbox", { name: "Search the pools by name" }).fill("nothing-like-this");
    await expect(page.getByTestId("pools-none-shown")).toContainText("No InfraEnvs match");
    await page.getByTestId("pools-none-shown").getByRole("button", { name: "Clear filters" }).click();
    await expect(page.getByRole("searchbox", { name: "Search the pools by name" })).toHaveValue("");
    await expect(rows(page)).toHaveCount(26);
  });

  test("no zone or size filter when no name follows the convention", async ({ page }) => {
    const [a, ...rest] = OVERVIEW.mces;
    const overview = { ...OVERVIEW, mces: [{ ...a, pools: a.pools.filter((pool) => pool.infra_env !== "r650-mtl-az1") }, ...rest] };
    await setUpInventory(page, { overview });
    await go(page, "/inventory");
    await expect(rows(page)).toHaveCount(2);
    await expect(page.getByRole("group", { name: "Zone filters" })).toHaveCount(0);
    await expect(page.getByRole("group", { name: "Size filters" })).toHaveCount(0);
    await expect(page.getByRole("searchbox", { name: "Search the pools by name" })).toBeVisible();
  });

  test("sorts by name or by available, most first, under a header that stays in view", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, "/inventory");
    await expect(rows(page).first()).toHaveAttribute("data-pool", "c200-kv32-az1");
    await page.getByTestId("pool-sort-available").click();
    await expect(rows(page).first()).toHaveAttribute("data-pool", "r760-mtl-az3");
    await expect(page.locator("th[aria-sort=descending]")).toContainText("Available");
    await expect(rows(page).last()).toHaveAttribute("data-pool", ""); // the servers no one InfraEnv names, last
    await page.getByTestId("pool-sort-name").click();
    await expect(page.locator("th[aria-sort=ascending]")).toContainText("InfraEnv");

    const table = page.getByTestId("pool-table");
    await table.evaluate((frame) => frame.scrollTo({ top: 400 }));
    const frame = await table.boundingBox();
    const head = await table.locator("thead").boundingBox();
    expect(Math.abs((head?.y ?? 0) - (frame?.y ?? -100))).toBeLessThan(2);
  });
});

test.describe("The runs", () => {
  test("stay every MCE's and every InfraEnv's, whatever is picked", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, `/inventory?mce=${SITE1_B}&infraEnv=c200-mtl-az1`);
    await expect(rows(page)).toHaveCount(1);
    await expect(page.getByTestId("runs-scope")).toContainText("every MCE and InfraEnv");
    // The fixture's runs: a pool draw into site1-a's r650-mtl-az1 and a named install on site1-b
    const runs = page.getByTestId("run-row");
    await expect(runs).toHaveCount(2);
    await expect(runs.nth(0)).toContainText(SITE1_A);
    await expect(runs.nth(1)).toContainText(SITE1_B);
  });
});

test.describe("At a phone's width", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the page keeps its width; the table scrolls inside its frame", async ({ page }) => {
    await setUpInventory(page, { overview: fleet() });
    await go(page, "/inventory");
    await expect(rows(page)).toHaveCount(26);
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width).toBeLessThanOrEqual(390);
    const scrolls = await page.getByTestId("pool-table").evaluate((frame) => frame.scrollWidth > frame.clientWidth);
    expect(scrolls).toBe(true);
  });
});
