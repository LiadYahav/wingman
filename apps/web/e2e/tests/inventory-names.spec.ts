/**
 * Inventory Management under the platform's naming convention (mocked; ADR-0057's
 * 3.54.0 amendment): add-server-to-mce's pool draw names its servers from the
 * InfraEnv's agentLabels (`ocp-<flavor>-<size>-<site>-…`). A pool whose
 * InfraEnv lacks them says the workflow would refuse a pool draw; a pool whose
 * labels Wingman could not read counts no free server and lists every one,
 * saying so; a named install may still pick any of them.
 */

import { test, expect, type Page } from "@playwright/test";
import { go } from "../fixtures/api-handlers";
import {
  FREE, R650_NAMES, SITE1_A, SITE1_B, SITE1_B_POOL, UNLABELLED, UNLABELLED_PROBLEMS, setUpInventory,
} from "../fixtures/inventory";
import type { Candidates } from "../../types/inventory";

const card = (page: Page, mce: string) => page.locator(`section[data-mce="${mce}"]`);
const pool = (page: Page, mce: string, infraEnv: string) => card(page, mce).locator(`tr[data-pool="${infraEnv}"]`);
const dialog = (page: Page) => page.getByTestId("add-servers-dialog");
const tooltip = (page: Page) => page.locator("[data-slot=tooltip-content][data-open]");

/** Every free server, as day1 lists it for a pool whose labels name none. */
const UNFILTERED: Candidates = {
  mce: SITE1_A, infra_env: UNLABELLED, server_prefix: null, label_problems: UNLABELLED_PROBLEMS,
  candidates: [FREE, "ocp-r760-mtl-site1-dlfake0801"].map((name) => ({
    id: `srv_${name.slice(-4)}`, name, vendor: "dell", model: "PowerEdge R650", health: "HEALTHY",
    lock: null, offered: true, why_not: null, ready: true, health_problems: [],
  })),
};

test("a pool whose InfraEnv lacks its agentLabels says the workflow refuses a pool draw", async ({ page }) => {
  const calls = await setUpInventory(page);
  await go(page, "/inventory");
  const row = pool(page, SITE1_A, UNLABELLED);
  await expect(row.getByTestId("pool-ready").getByRole("button", { name: "Why not counted" })).toHaveText("—");
  const warning = row.getByTestId("pool-labels-missing");
  await expect(warning).toHaveAccessibleName(`${UNLABELLED} lacks agentLabels`);
  await warning.hover();
  await expect(tooltip(page)).toContainText("redbull.io/flavor is missing; redbull.io/size is missing; redbull.io/site is missing");
  await expect(tooltip(page)).toContainText("the workflow refuses a pool draw into it");
  await row.getByRole("button", { name: `Install servers into ${UNLABELLED}` }).click();
  await expect(dialog(page).getByTestId("add-servers-labels-missing")).toContainText("The workflow would refuse a pool draw here.");
  await dialog(page).getByRole("button", { name: "Install 1" }).click();
  expect(calls.starts).toEqual([{ count: 1 }]); // the workflow is the judge, as for a typed InfraEnv
});

test("a pool's list is every free server, said so, when its labels name none", async ({ page }) => {
  const calls = await setUpInventory(page, { candidates: UNFILTERED });
  await go(page, "/inventory");
  await pool(page, SITE1_A, UNLABELLED).getByRole("button", { name: `Install servers into ${UNLABELLED}` }).click();
  await dialog(page).getByRole("tab", { name: "Choose servers" }).click();
  await expect(dialog(page).getByTestId("candidates-unfiltered")).toContainText("Every free server in server-scan, not filtered by name.");
  await expect(dialog(page).getByTestId("add-servers-labels-missing")).toHaveCount(0);
  await dialog(page).getByRole("checkbox", { name: "Install ocp-r760-mtl-site1-dlfake0801" }).check();
  await dialog(page).getByRole("button", { name: "Install 1" }).click();
  expect(calls.starts).toEqual([{ server_names: ["ocp-r760-mtl-site1-dlfake0801"] }]);
});

test("a pool whose labels are unread counts no free server and says why", async ({ page }) => {
  await setUpInventory(page);
  await go(page, "/inventory");
  const row = pool(page, SITE1_B, SITE1_B_POOL);
  await expect(row.getByTestId("pool-labels-missing")).toHaveCount(0);
  await row.getByTestId("pool-ready").getByRole("button", { name: "Why not counted" }).hover();
  await expect(tooltip(page)).toContainText("Wingman could not read this InfraEnv's agentLabels");
});

test("a pool whose labels name its servers mutes their shared prefix", async ({ page }) => {
  await setUpInventory(page);
  await go(page, "/inventory");
  await pool(page, SITE1_A, "r650-mtl-az1").getByRole("button", { name: "1 ready in server-scan for r650-mtl-az1" }).click();
  const free = page.locator(`[data-testid="candidate"][data-server="${FREE}"]`);
  await expect(free).toContainText(R650_NAMES);
  await expect(page.getByTestId("candidates-unfiltered")).toHaveCount(0);
});
