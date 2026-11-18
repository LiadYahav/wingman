/**
 * Picking the servers a scale-down removes (ADR-0062's 2026-11-18
 * amendments), on the cluster page's Nodes tab: in the scale-down's
 * confirmation, "Pick the servers" is one of the ways the servers that leave
 * are chosen (the NodePool's own policy stays the default, and sends
 * nothing). Picked, it lists the NodePool's servers from the MCE's nodes, and
 * Yes waits for exactly as many as leave; the body then carries
 * `server_names`, by the workflow's own name for each Machine's server
 * (`machine_server`). A scale-up never sends names; without the MCE's nodes
 * there is nothing to pick, and the choice says so. The run shows a named
 * server, and a refusal of the names in plain words. Every API is mocked.
 */
import { test, expect, type Page } from "@playwright/test";
import { mockNodePool, mockNodes, mockPoolNode, mockServer } from "../fixtures/api-handlers";
import { CARDS, LARK, ZONE_A, ZONE_B, card, confirmation, openNodes, run, scaleOf, yes } from "../fixtures/scale";
import type { ClusterNodes, ScaleRun } from "../../types";

/** ZONE_B's three servers on the cards, as server-scan names them, and as the workflow does (lowercased). */
const B1 = "ocp-dell-r660-site1-64c-512gb-DL0000121";
const B2 = "ocp-dell-r660-site1-64c-512gb-DL0000122";
const B3 = "ocp-dell-r660-site1-64c-512gb-DL0000123";

const box = (page: Page, server: string) => confirmation(page).getByRole("checkbox", { name: server, exact: true });
const count = (page: Page) => confirmation(page).getByTestId("scale-pick-count");
const pick = (page: Page) => confirmation(page).getByRole("radio", { name: /^Pick the servers/ });
const own = (page: Page) => confirmation(page).getByRole("radio", { name: /^The NodePool's own policy/ });

/** Sets ZONE_B's replicas on its card (3 now) and opens the confirmation. */
async function scaleZoneB(page: Page, replicas: number) {
  const b = card(page, ZONE_B);
  await b.getByRole("spinbutton").fill(String(replicas));
  await b.getByTestId("scale-start").click();
  await expect(confirmation(page)).toBeVisible();
}

test.describe("Pick the servers a scale-down removes", () => {
  test("the NodePool's own policy is the default: no list, no names sent", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    await scaleZoneB(page, 2);
    await expect(own(page)).toBeChecked();
    await expect(confirmation(page).getByTestId("scale-pick")).toHaveCount(0);
    await expect(confirmation(page).getByTestId("scale-confirm-leaving")).toContainText("Removes the node running the fewest pods (fewest-pods).");
    await yes(page).click();
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 2 }]);
  });

  test("exactly as many as leave: Yes waits for the count, then sends the workflow's names", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    await scaleZoneB(page, 1);
    await pick(page).check();
    const picker = confirmation(page).getByTestId("scale-pick");
    await expect(picker.getByRole("checkbox")).toHaveCount(3);
    await expect(count(page)).toHaveText("Tick the 2 servers to remove.");
    await expect(confirmation(page).getByTestId("scale-confirm-leaving")).toHaveText("Removes the 2 servers you tick below.");
    await expect(yes(page)).toBeDisabled();

    await box(page, B3).click();
    await expect(box(page, B3)).toHaveAttribute("aria-checked", "true");
    await expect(count(page)).toHaveText("1 of 2 picked: tick 1 more.");
    await expect(yes(page)).toBeDisabled();

    await box(page, B1).click();
    await expect(count(page)).toHaveText("2 of 2 picked: exactly these leave.");
    // No more than leave: the third waits
    await expect(box(page, B2)).toBeDisabled();
    await expect(confirmation(page).getByTestId("scale-confirm-leaving")).toHaveText(
      `Removes exactly the 2 servers you picked: ${B3.toLowerCase()}, ${B1.toLowerCase()}. The NodePool's scale-down policy is not used.`
    );
    await expect(yes(page)).toBeEnabled();
    expect(scale.starts).toEqual([]);

    await yes(page).click();
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 1, server_names: [B3.toLowerCase(), B1.toLowerCase()] }]);
  });

  test("another choice drops the ticks; Cancel drops the choice and keeps the change", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    await scaleZoneB(page, 2);
    await pick(page).check();
    await box(page, B2).click();
    await expect(box(page, B1)).toBeDisabled();
    await box(page, B2).click();
    await expect(box(page, B1)).toBeEnabled();
    await box(page, B1).click();
    await own(page).check();
    await expect(confirmation(page).getByTestId("scale-pick")).toHaveCount(0);
    await pick(page).check();
    await expect(box(page, B1)).toHaveAttribute("aria-checked", "false");
    await box(page, B1).click();
    await page.getByTestId("scale-confirm-cancel").click();
    await expect(confirmation(page)).toHaveCount(0);
    await expect(card(page, ZONE_B).getByTestId("scale-change")).toHaveText("Replicas 3 → 2 (−1)");

    await card(page, ZONE_B).getByTestId("scale-start").click();
    await expect(own(page)).toBeChecked();
    await yes(page).click();
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 2 }]);
  });

  test("a scale-up offers no choice and never sends names", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    await card(page, ZONE_A).getByRole("button", { name: `One replica more for ${ZONE_A}` }).click();
    await card(page, ZONE_A).getByTestId("scale-start").click();
    await expect(confirmation(page)).toHaveAttribute("data-direction", "up");
    await expect(confirmation(page).getByTestId("scale-leave-choice")).toHaveCount(0);
    await yes(page).click();
    expect(scale.starts).toEqual([{ nodepool: ZONE_A, replicas: 4 }]);
  });

  test("a Machine with no server yet, or one already leaving, cannot be picked, and says why", async ({ page }) => {
    const nodes: ClusterNodes = mockNodes({
      hosted_cluster: "prod-lark-site1",
      node_pools: [
        mockNodePool({
          name: ZONE_B,
          nodes: [
            mockPoolNode(`${ZONE_B}-a1b2c`, { server: mockServer(B1) }),
            mockPoolNode(`${ZONE_B}-d3e4f`, { server: mockServer(B2), state: "deleting" }),
            mockPoolNode(`${ZONE_B}-g5h6i`, { server: null, server_name: null, machine_server: null, node_name: null, agent: null, state: "waiting" }),
          ],
        }),
      ],
    });
    await openNodes(page, scaleOf(), { nodes });
    await scaleZoneB(page, 2);
    await pick(page).check();
    const rows = confirmation(page).getByTestId("scale-pick-server");
    await expect(rows).toHaveCount(3);
    await expect(box(page, B1)).toBeEnabled();
    await expect(box(page, B2)).toBeDisabled();
    await expect(rows.nth(1)).toContainText("Already leaving");
    await expect(rows.nth(2)).toContainText(`${ZONE_B}-g5h6i`);
    await expect(rows.nth(2)).toContainText("Not installed yet: no server to name");
    await expect(rows.nth(2).getByRole("checkbox")).toBeDisabled();
  });

  test("without the MCE's nodes there is nothing to pick: the choice says so, and the policy picks", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    await page.getByTestId("scale-pool-1").getByRole("spinbutton").fill("2");
    await page.getByTestId("scale-pool-1").getByTestId("scale-start").click();
    await expect(pick(page)).toBeDisabled();
    await expect(confirmation(page).getByTestId("scale-pick-none")).toHaveText("Needs this NodePool's nodes from the MCE (live status).");
    await yes(page).click();
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 2 }]);
  });

  test("the run shows the servers picked by name, and a refusal of them in plain words", async ({ page }) => {
    const named: ScaleRun = run({
      status: "completed", phase: "completed", direction: "down",
      result: {
        infra_env_kind: null, nodepool: ZONE_B, day1_path: null, direction: "down", total_before: 3, total_after: 2,
        nodepools: [{ name: ZONE_B, infra_env: "dell-r660-site1-zone-b", before: 3, after: 2, scale_down_policy: null }],
        child_workflow_id: `scale-down-nodepool-${LARK}`, revision: "9f2c1ab77d0e5c3f", committed: true, live: [],
        chosen: [{ nodepool: ZONE_B, machine: `${ZONE_B}-a1b2c`, node: B1.toLowerCase(), policy: "named", reason: `named: ${B1}`, server: B1.toLowerCase() }],
        deleting: [`${ZONE_B}-a1b2c`], ignored: [],
      },
    });
    const scale = scaleOf({ run: named });
    await openNodes(page, scale, { nodes: CARDS });
    await expect(page.getByTestId("scale-run-choice")).toHaveText("Which servers left: Picked by name.");
    await expect(page.getByTestId("scale-run-chosen")).toContainText(`${B1.toLowerCase()} (${ZONE_B}-a1b2c) · ${ZONE_B} · picked by name`);

    const words = `scale-down-nodepool-${LARK} failed — ScaleDownServersInvalidError: no Machine of NodePool ${ZONE_B} is server ocp-x; its servers are ${B1.toLowerCase()} (${ZONE_B}-a1b2c). Nothing was marked or written`;
    scale.run = run({ status: "failed", phase: "scaling-down", direction: "down", error: words, error_type: "ScaleDownServersInvalidError" });
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByTestId("scale-run-error")).toContainText(words);
    await expect(page.getByTestId("scale-run-error-hint")).toHaveText(
      "A picked server is not a machine of the NodePool now (the workflow lists its servers): read the nodes again and pick again. Nothing was marked or written."
    );
  });
});
