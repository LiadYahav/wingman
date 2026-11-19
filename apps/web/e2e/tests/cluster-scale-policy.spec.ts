/**
 * A scale-down's own policy for one run (ADR-0062's last 2026-11-18
 * amendment), on the cluster page's Nodes tab: the scale-down's confirmation
 * offers one choice of which servers leave. The NodePool's own policy is the
 * default and sends nothing; "Another policy for this run" offers the
 * workflow's policies but the NodePool's own and sends `scale_down_policy`
 * alone; a scale-up offers no choice and sends neither. The run says which
 * way its servers were chosen. Every API is mocked.
 */
import { test, expect, type Page } from "@playwright/test";
import { CARDS, LARK, OPTIONS, UNHEALTHY, ZONE_A, ZONE_B, card, confirmation, openNodes, run, scaleOf, yes } from "../fixtures/scale";
import type { ScaleRun } from "../../types";

const another = (page: Page) => confirmation(page).getByRole("radio", { name: /^Another policy for this run/ });
const own = (page: Page) => confirmation(page).getByRole("radio", { name: /^The NodePool's own policy/ });
const policy = (page: Page) => confirmation(page).getByTestId("scale-leave-policy-select");
const leavingLine = (page: Page) => confirmation(page).getByTestId("scale-confirm-leaving");

/** Lowers a NodePool's stepper on its card by one (3 now) and opens the confirmation. */
async function scaleDown(page: Page, nodepool: string) {
  await card(page, nodepool).getByRole("button", { name: `One replica fewer for ${nodepool}` }).click();
  await card(page, nodepool).getByTestId("scale-start").click();
  await expect(confirmation(page)).toHaveAttribute("data-direction", "down");
}

/** A completed scale-down of ZONE_B by `applied`. */
const completed = (applied: string | null): ScaleRun =>
  run({
    status: "completed", phase: "completed", direction: "down",
    result: {
      infra_env_kind: null, nodepool: ZONE_B, day1_path: null, direction: "down", total_before: 3, total_after: 2,
      nodepools: [{ name: ZONE_B, infra_env: "dell-r660-site1-zone-b", before: 3, after: 2, scale_down_policy: applied }],
      child_workflow_id: `scale-down-nodepool-${LARK}`, revision: "9f2c1ab77d0e5c3f", committed: true, live: [],
      chosen: applied ? [{ nodepool: ZONE_B, machine: `${ZONE_B}-7xk2p`, node: "worker-7", policy: applied, reason: "3% used", server: null }] : [],
      deleting: applied ? [`${ZONE_B}-7xk2p`] : [], ignored: [],
    },
  });

test.describe("A scale-down's own policy for one run", () => {
  test("the NodePool's own policy is named and the default, and sends nothing", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    await scaleDown(page, ZONE_B);
    const choice = confirmation(page).getByTestId("scale-leave-choice");
    await expect(choice).toContainText("Which servers leave");
    await expect(confirmation(page).getByTestId("scale-leave-own")).toContainText("fewest-pods");
    await expect(own(page)).toBeChecked();
    await expect(policy(page)).toHaveCount(0);
    await yes(page).click();
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 2 }]);
  });

  test("another policy offers the others, says what it removes, and is sent alone", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    await scaleDown(page, ZONE_B);
    await another(page).check();
    await expect(policy(page)).toContainText("least-requested");
    await expect(leavingLine(page)).toHaveText(
      `Removes the node with the lowest requested CPU or memory (least-requested, for this run only). ${UNHEALTHY}`
    );
    await policy(page).click();
    const options = page.getByRole("option");
    await expect(options).toHaveText(["least-requested", "least-utilized"]);
    await page.getByRole("option", { name: "least-utilized" }).click();
    await expect(confirmation(page).getByTestId("scale-leave-policy-note")).toContainText("needs the hosted cluster's metrics API");
    await expect(leavingLine(page)).toContainText("(least-utilized, for this run only)");
    await yes(page).click();
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 2, scale_down_policy: "least-utilized" }]);
  });

  test("without a policy of its own, the platform default is named and all three are offered", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    await scaleDown(page, ZONE_A);
    await expect(confirmation(page).getByTestId("scale-leave-own")).toContainText("the platform default: CAPI picks at random");
    await another(page).check();
    await policy(page).click();
    await expect(page.getByRole("option")).toHaveText(["fewest-pods", "least-requested", "least-utilized"]);
    await page.keyboard.press("Escape");
    await expect(confirmation(page)).toBeVisible();
    await yes(page).click();
    expect(scale.starts).toEqual([{ nodepool: ZONE_A, replicas: 2, scale_down_policy: "fewest-pods" }]);
  });

  test("an unknown policy of its own is refused by the workflow, and another one is the way out", async ({ page }) => {
    const scale = scaleOf({
      options: { ...OPTIONS, nodepools: OPTIONS.nodepools.map((p) => (p.name === ZONE_B ? { ...p, scale_down_policy: "newest-first" } : p)) },
    });
    await openNodes(page, scale, { nodes: CARDS });
    await scaleDown(page, ZONE_B);
    await expect(leavingLine(page)).toContainText("the workflow will refuse it");
    await another(page).check();
    await expect(leavingLine(page)).toHaveText(`Removes the node running the fewest pods (fewest-pods, for this run only). ${UNHEALTHY}`);
    await yes(page).click();
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 2, scale_down_policy: "fewest-pods" }]);
  });

  test("Cancel drops the choice; a scale-up offers none and sends neither", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    await scaleDown(page, ZONE_B);
    await another(page).check();
    await page.getByTestId("scale-confirm-cancel").click();
    await card(page, ZONE_B).getByTestId("scale-start").click();
    await expect(own(page)).toBeChecked();
    await page.getByTestId("scale-confirm-cancel").click();

    await card(page, ZONE_A).getByRole("button", { name: `One replica more for ${ZONE_A}` }).click();
    await card(page, ZONE_A).getByTestId("scale-start").click();
    await expect(confirmation(page)).toHaveAttribute("data-direction", "up");
    await expect(confirmation(page).getByTestId("scale-leave-choice")).toHaveCount(0);
    await yes(page).click();
    expect(scale.starts).toEqual([{ nodepool: ZONE_A, replicas: 4 }]);
  });

  test("the run says which way its servers were chosen", async ({ page }) => {
    const scale = scaleOf({ run: completed("least-utilized") });
    await openNodes(page, scale, { nodes: CARDS });
    await expect(page.getByTestId("scale-run-choice")).toHaveText(
      "Which servers left: By least-utilized, not the day1 file's policy (fewest-pods): this run's choice, or one set on the NodePool itself."
    );
    scale.run = completed("fewest-pods");
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByTestId("scale-run-choice")).toHaveText("Which servers left: By fewest-pods, the NodePool's own policy.");
    scale.run = completed(null);
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByTestId("scale-run-choice")).toHaveText("Which servers left: At random, by CAPI: no scale-down policy.");
  });
});
