/**
 * Inventory Management and herzi's used Agents (mocked; ADR-0057's 3.55.0
 * amendment): a free Agent labelled `redbull.io/ever-installed` is shown
 * apart, "used", on its MCE and its pool, never as available; the MCE's
 * NodePools that do not exclude the label are listed by cluster once it
 * matters (herzi has used Agents there, or the deployment excludes the label),
 * each cluster linked to its page.
 */

import { test, expect, type Page } from "@playwright/test";
import { go } from "../fixtures/api-handlers";
import { HERZI_LABEL, OVERVIEW, R650, SITE1_A, SITE1_B, setUpInventory } from "../fixtures/inventory";
import type { InventoryOverview, MceInventory } from "../../types/inventory";

const card = (page: Page, mce: string) => page.locator(`section[data-mce="${mce}"]`);
const tooltip = (page: Page) => page.locator("[data-slot=tooltip-content][data-open]");
const USED = ["ocp-r650-mtl-site1-dlfake0901", "ocp-r650-mtl-site1-dlfake0902"];

/** site1-a with two used Agents in R650, and two clusters whose NodePools lack the exclusion. */
function withUsed(source: "herzi" | "setting" = "herzi", used: number | null = 2): InventoryOverview {
  const [siteA, ...rest] = OVERVIEW.mces;
  const a: MceInventory = {
    ...siteA,
    used,
    pools: siteA.pools.map((p) => (p.infra_env === R650 ? { ...p, used: used ? USED : [] } : p)),
    unguarded: [
      { cluster: "ocp4-prod-heron-site1", nodepool: "prod-heron-site1-r650", infra_envs: [R650], missing: [HERZI_LABEL], replace: false },
      { cluster: "ocp4-prod-heron-site1", nodepool: "prod-heron-site1-gpu", infra_envs: ["g12-mtl-az1"], missing: [HERZI_LABEL], replace: true },
      { cluster: "ocp4-prod-lark-site1", nodepool: "prod-lark-site1-r650", infra_envs: [R650], missing: [HERZI_LABEL], replace: false },
    ],
  };
  return { ...OVERVIEW, mces: [a, ...rest], used_labels: { keys: [HERZI_LABEL], source } };
}

test("used Agents are counted apart on the MCE and the pool, and say why", async ({ page }) => {
  await setUpInventory(page, { overview: withUsed() });
  await go(page, "/inventory");
  const siteA = card(page, SITE1_A);
  await expect(siteA.getByTestId("mce-available")).toContainText("6 available");
  await expect(siteA.getByTestId("mce-used")).toHaveText("2 used");
  const pool = siteA.locator(`tr[data-pool="${R650}"]`);
  await expect(pool.getByTestId("pool-total")).toHaveText("4"); // not in the total
  await pool.getByTestId("pool-used").hover();
  await expect(tooltip(page)).toContainText(`waiting for herzi to remove: ${USED.join(", ")}.`);
  await expect(tooltip(page)).toContainText(`labelled ${HERZI_LABEL}`);
  await expect(card(page, SITE1_B).getByTestId("mce-used")).toHaveCount(0); // not read there
});

test("the NodePools that lack the exclusion are listed by cluster, each linked", async ({ page }) => {
  await setUpInventory(page, { overview: withUsed() });
  await go(page, "/inventory");
  const notice = card(page, SITE1_A).getByTestId("mce-unguarded");
  await expect(notice).toContainText(`3 NodePools in 2 clusters do not exclude ${HERZI_LABEL}`);
  await notice.locator("summary").click();
  const clusters = notice.getByTestId("unguarded-cluster");
  await expect(clusters).toHaveCount(2);
  await expect(clusters.first()).toContainText("prod-heron-site1-r650, prod-heron-site1-gpu (Replace: change it to InPlace first)");
  await expect(notice.getByRole("link", { name: "ocp4-prod-lark-site1" })).toHaveAttribute(
    "href",
    `/clusters/ocp4-prod-lark-site1?site=site1&mce=${SITE1_A}`
  );
});

test("the exclusion is not raised before herzi has used Agents or the deployment excludes the label", async ({ page }) => {
  await setUpInventory(page, { overview: withUsed("herzi", 0) });
  await go(page, "/inventory");
  await expect(card(page, SITE1_A).getByTestId("mce-used")).toHaveCount(0);
  await expect(card(page, SITE1_A).getByTestId("mce-unguarded")).toHaveCount(0);
});

test("once the deployment excludes the label, the NodePools still lacking it are listed", async ({ page }) => {
  await setUpInventory(page, { overview: withUsed("setting", 0) });
  await go(page, "/inventory");
  await expect(card(page, SITE1_A).getByTestId("mce-unguarded")).toBeVisible();
});

test("a pool herzi paused says so, and that its used Agents wait for it", async ({ page }) => {
  const overview = withUsed();
  overview.mces[0] = {
    ...overview.mces[0],
    pools: overview.mces[0].pools.map((p) => (p.infra_env === R650 ? { ...p, herzi: { ...p.herzi, paused: true } } : p)),
  };
  await setUpInventory(page, { overview });
  await go(page, "/inventory");
  const pool = card(page, SITE1_A).locator(`tr[data-pool="${R650}"]`);
  await expect(pool.getByTestId("pool-herzi")).toHaveText("herzi paused");
  await pool.getByTestId("pool-herzi").hover();
  await expect(tooltip(page)).toContainText("herzi watches this pool but orders nothing for it");
  await page.mouse.move(0, 0);
  await pool.getByTestId("pool-used").hover();
  await expect(tooltip(page)).toContainText("herzi is paused on this pool, so it removes none of them");
  await expect(card(page, SITE1_A).locator(`tr[data-pool="${OVERVIEW.mces[0].pools[0].infra_env}"]`).getByTestId("pool-herzi")).toHaveCount(0);
});

test("used Agents that could not be read say why", async ({ page }) => {
  const overview = withUsed("herzi", null);
  overview.mces[0] = { ...overview.mces[0], used_error: "HubDenied: MCE 'ocp4-prod-mce-site1-a' denied Wingman's token" };
  await setUpInventory(page, { overview });
  await go(page, "/inventory");
  await expect(card(page, SITE1_A).getByTestId("mce-used-unread")).toContainText("Used Agents not read: HubDenied");
});
