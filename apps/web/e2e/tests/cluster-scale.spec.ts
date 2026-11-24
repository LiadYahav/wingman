/**
 * Scaling a cluster's NodePools through the platform's update-nodepool
 * workflow (ADR-0062 and its amendments), on the cluster page's Nodes tab: a
 * stepper on each NodePool's card from the MCE (its exact replicas, matched
 * by name), or on its NodePool sizes row when there are no cards (live
 * status off); one NodePool a run, so no hardware type total (2026-11-18);
 * one change at a time; Scale up and Scale down each confirmed first, a
 * scale-down with the nodes its NodePool's scale-down policy removes; the
 * run in place (the workflow's phases, its child's, the plan, the servers a
 * scale-down chose, what a run ignored, and a run recorded by kind before
 * then), refusals and failures in words, a NodePool whose replicas a flavor
 * locks, and a flavor sync's replicas restored by their own run. Scaling
 * off: no steppers. A viewer has no Nodes tab (ADR-0038's 2026-11-23
 * amendment), so no Scale at all. Every API is mocked.
 */
import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, json } from "../fixtures/api-handlers";
import {
  CARDS, DETAIL, FLAVOR, LARK, MCE, OPTIONS, R760, RUN_ID, SITE, UNHEALTHY, ZONE_A, ZONE_B,
  card, confirmation, fewer, field, more, notDrifted, openNodes, run, scaleOf, stepper, yes,
} from "../fixtures/scale";
import type { ClusterDrift, ScaleRun, SyncPreview, UpgradeRun } from "../../types";

/**
 * A run recorded by InfraEnv kind before 2026-11-18 (a total over the zones), done: zone-b lost a node by
 * fewest-pods. The plan, the server chosen and the commit still show.
 */
const DONE: ScaleRun = run({
  status: "completed", phase: "completed", direction: "down",
  result: {
    infra_env_kind: "dell-r660-site1-zone", nodepool: null, day1_path: DETAIL.path, direction: "down", total_before: 6, total_after: 5,
    nodepools: [
      { name: ZONE_A, infra_env: "dell-r660-site1-zone-a", before: 3, after: 3, scale_down_policy: null },
      { name: ZONE_B, infra_env: "dell-r660-site1-zone-b", before: 3, after: 2, scale_down_policy: "fewest-pods" },
    ],
    child_workflow_id: `scale-down-nodepool-${LARK}`, revision: "9f2c1ab77d0e5c3f", committed: true,
    live: [{ name: ZONE_B, replicas: 2, ready_replicas: 3 }],
    chosen: [{ nodepool: ZONE_B, machine: `${ZONE_B}-7xk2p`, node: "worker-7", policy: "fewest-pods", reason: "1 workload pods", server: null }],
    deleting: [`${ZONE_B}-7xk2p`],
    ignored: [],
  },
});

/** A scale-up of zone-a by name, done, whose request also named a server to remove: unused, and said so. */
const UP_IGNORING: ScaleRun = run({
  status: "completed", phase: "completed", direction: "up",
  result: {
    ...(DONE.result as NonNullable<ScaleRun["result"]>),
    infra_env_kind: null, nodepool: ZONE_A, direction: "up", total_before: 3, total_after: 4,
    nodepools: [{ name: ZONE_A, infra_env: "dell-r660-site1-zone-a", before: 3, after: 4, scale_down_policy: null }],
    child_workflow_id: `scale-up-nodepool-${LARK}`, live: [{ name: ZONE_A, replicas: 4, ready_replicas: 3 }], chosen: [], deleting: [],
    ignored: ["server_names ocp-r660-site1-hp0001592: the NodePool scales up"],
  },
});

test.describe("Scale a cluster's NodePools through update-nodepool", () => {
  test("scaling off: no sizes and no steppers, and the Nodes tab is as before", async ({ page }) => {
    await openNodes(page, null);
    await expect(page.getByTestId("cluster-nodes-off")).toHaveText("Nodes need live status from the MCE (CLUSTER_STATUS_ENABLED).");
    await expect(page.getByTestId("scale-panel")).toHaveCount(0);
    await expect(page.getByTestId("scale-stepper")).toHaveCount(0);
  });

  test("a viewer has no Nodes tab, so no sizes, steppers or run, and reads none of them", async ({ page }) => {
    const reads: string[] = [];
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (/\/(scale|scale-run|nodes)$/.test(path)) reads.push(path);
    });
    await openNodes(page, scaleOf({ run: DONE }), { viewer: true, nodes: CARDS });
    await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tab", { name: "Nodes" })).toHaveCount(0);
    // The fixture's file lists no nodepool; a viewer's card does not read the MCE's
    await expect(page.getByText("Nodepools (0)")).toBeVisible();
    await expect(page.getByTestId("scale-panel")).toHaveCount(0);
    await expect(page.getByTestId("scale-stepper")).toHaveCount(0);
    await page.waitForTimeout(1_000);
    expect(reads).toEqual([]);
  });

  test("live status off: each NodePool scales on its sizes row; Scale up asks first, then sends its exact replicas, once", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    await expect(page.getByTestId("cluster-nodes-off")).toBeVisible();
    await expect(field(page, ZONE_A)).toHaveValue("3");
    await more(page, ZONE_A).click();
    await expect(field(page, ZONE_A)).toHaveValue("4");
    await expect(stepper(page, ZONE_A)).toHaveAttribute("data-changed", "true");
    const pending = page.getByTestId("scale-pool-0").getByTestId("scale-pending");
    await expect(pending.getByTestId("scale-change")).toHaveText("Replicas 3 → 4 (+1)");
    await expect(pending).toContainText("One commit to day1 main; the workflow syncs Argo CD itself.");
    await expect(page.getByTestId("scale-announce")).toHaveText(`${ZONE_A}: 3 → 4 (+1)`);
    await expect(page.getByTestId("scale-announce")).toHaveAttribute("role", "status");
    await expect(pending.getByTestId("scale-start")).toHaveText("Scale up");

    // Scale up asks first: what the run does, in a few lines; Yes arms after half a second
    const opened = Date.now();
    await pending.getByTestId("scale-start").click();
    const confirm = confirmation(page);
    await expect(confirm.getByRole("heading", { name: `Scale up ${ZONE_A}?` })).toBeVisible();
    await expect(confirm.getByTestId("scale-confirm-change")).toHaveText("3 → 4 replicas (+1)");
    const points = confirm.getByTestId("scale-confirm-points");
    await expect(points).toContainText("Adds 1 node: it takes a free server of the NodePool's hardware; with none free, it waits until one is added.");
    await expect(points).toContainText("One commit to day1 main, no merge request; the workflow has Argo CD apply it.");
    await expect(points).toContainText("Done when the NodePool shows the new size; new nodes join after they install.");
    await expect(yes(page)).toHaveText("Yes, scale up");
    await expect(yes(page)).toBeEnabled();
    expect(Date.now() - opened).toBeGreaterThanOrEqual(450);
    expect(scale.starts).toEqual([]);

    // Yes sends it; the second click of a double-click sends nothing
    await yes(page).dblclick();
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    await expect(confirm).toHaveCount(0);
    expect(scale.starts).toEqual([{ nodepool: ZONE_A, replicas: 4 }]);
    await expect(page.getByTestId("scale-run")).toBeFocused();
    // The run holds every stepper, and says why once
    const why = "An update-nodepool run of this cluster is running";
    await expect(page.getByTestId("scale-busy-reason")).toContainText(why);
    await expect(page.getByText(why)).toHaveCount(1);
    // Nothing looks editable while it runs: each size is text
    await expect(page.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(page.getByTestId("scale-pool-0")).toContainText("3 replicas");
    await expect(page.getByTestId("scale-pending")).toHaveCount(0);
  });

  test("a number can be typed, and the arrow keys step it by one", async ({ page }) => {
    await openNodes(page, scaleOf());
    const b = field(page, ZONE_B);
    const change = page.getByTestId("scale-change");
    await b.fill("5");
    await expect(change).toHaveText("Replicas 3 → 5 (+2)");
    await b.press("ArrowDown");
    await expect(b).toHaveValue("4");
    await b.press("ArrowUp");
    await b.press("ArrowUp");
    await expect(b).toHaveValue("6");
    await expect(change).toHaveText("Replicas 3 → 6 (+3)");
    await b.fill("");
    await expect(change).toHaveText("Replicas are a whole number from 0 to 500.");
    await expect(b).toHaveAttribute("aria-invalid", "true");
    await expect(page.getByTestId("scale-start")).toBeDisabled();
    // Back at its value now: nothing to send
    await b.fill("3");
    await expect(page.getByTestId("scale-pending")).toHaveCount(0);
  });

  test("one change at a time: changing a stepper puts every other back; there is no hardware type total", async ({ page }) => {
    await openNodes(page, scaleOf());
    await more(page, ZONE_A).click();
    await fewer(page, ZONE_B).click();
    await expect(field(page, ZONE_A)).toHaveValue("3");
    await expect(field(page, ZONE_B)).toHaveValue("2");
    await expect(page.getByTestId("scale-pending")).toHaveCount(1);
    await expect(page.getByTestId("scale-pool-1").getByTestId("scale-change")).toHaveText("Replicas 3 → 2 (−1)");
    await expect(page.locator('[data-testid="scale-stepper"][data-changed="true"]')).toHaveCount(1);
    // update-nodepool sets one NodePool a run: nothing offers a total over a hardware type
    await expect(page.getByRole("button", { name: /hardware type/i })).toHaveCount(0);

    // A NodePool's Cancel returns to its field
    await more(page, ZONE_A).click();
    await page.getByTestId("scale-cancel").click();
    await expect(field(page, ZONE_A)).toHaveValue("3");
    await expect(field(page, ZONE_A)).toBeFocused();
  });

  test("the confirmation's Cancel and Escape send nothing, and the change stays where it was", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    await more(page, ZONE_A).click();
    const start = page.getByTestId("scale-pool-0").getByTestId("scale-start");
    await start.click();
    await expect(confirmation(page)).toBeVisible();
    // Focus starts on Cancel: Enter alone confirms nothing
    await expect(page.getByTestId("scale-confirm-cancel")).toBeFocused();
    await page.getByTestId("scale-confirm-cancel").click();
    await expect(confirmation(page)).toHaveCount(0);
    await expect(start).toBeFocused();
    await expect(field(page, ZONE_A)).toHaveValue("4");
    await expect(page.getByTestId("scale-change")).toHaveText("Replicas 3 → 4 (+1)");

    await start.click();
    await expect(confirmation(page)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(confirmation(page)).toHaveCount(0);
    await expect(start).toBeFocused();
    await expect(field(page, ZONE_A)).toHaveValue("4");
    expect(scale.starts).toEqual([]);
  });

  test("a scale-down asks first, with the nodes its NodePool's policy removes, and is sent only from there", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    await fewer(page, ZONE_B).click();
    const pending = page.getByTestId("scale-pending");
    await expect(pending.getByTestId("scale-start")).toHaveText("Scale down");
    await pending.getByTestId("scale-start").click();
    const confirm = confirmation(page);
    await expect(confirm).toHaveAttribute("data-direction", "down");
    await expect(confirm.getByRole("heading", { name: `Scale down ${ZONE_B}?` })).toBeVisible();
    await expect(confirm.getByTestId("scale-confirm-change")).toHaveText("3 → 2 replicas (\u22121)");
    await expect(confirm.getByTestId("scale-confirm-leaving")).toHaveText(`Removes the node running the fewest pods (fewest-pods). ${UNHEALTHY}`);
    const points = confirm.getByTestId("scale-confirm-points");
    await expect(points).toContainText("Their pods move to the remaining nodes; the servers stay in the MCE's inventory, free.");
    await expect(points).toContainText("One commit to day1 main, applied by Argo CD.");
    await expect(yes(page)).toHaveText("Yes, scale down");
    expect(scale.starts).toEqual([]);

    await page.keyboard.press("Escape");
    await expect(confirm).toHaveCount(0);
    await expect(pending.getByTestId("scale-start")).toBeFocused();
    expect(scale.starts).toEqual([]);

    await pending.getByTestId("scale-start").click();
    await yes(page).click();
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 2 }]);
  });

  test("the nodes unreadable (404): a scale-down's confirmation reads them no more and holds still; picking waits, and says why", async ({ page }) => {
    let reads = 0;
    await openNodes(page, scaleOf(), {
      nodes: (route) => {
        reads += 1;
        return fulfillProblem(route, 404, "NOT_FOUND", `the MCE has no HostedCluster ${LARK} yet`);
      },
    });
    await expect(page.getByTestId("cluster-nodes-error")).toBeVisible();
    const before = reads;
    await fewer(page, ZONE_B).click();
    await page.getByTestId("scale-pool-1").getByTestId("scale-start").click();
    const choice = confirmation(page).getByTestId("scale-leave-choice");
    await expect(choice).toBeVisible();
    // Open for two seconds: the same choice all along, and not one read of the nodes
    const shown = await choice.elementHandle();
    await page.waitForTimeout(2_000);
    expect(reads).toBe(before);
    expect(await shown?.evaluate((el) => el.isConnected)).toBe(true);
    // Picking needs the nodes: it waits, and says why; the other choices take a click
    await expect(confirmation(page).getByRole("radio", { name: /^Pick the servers/ })).toBeDisabled();
    await expect(confirmation(page).getByTestId("scale-pick-none")).toHaveText("Needs this NodePool's nodes from the MCE (live status).");
    const another = confirmation(page).getByRole("radio", { name: /^Another policy for this run/ });
    await another.check();
    await expect(another).toBeChecked();
    await expect(yes(page)).toBeEnabled();
    expect(reads).toBe(before);
  });

  test("a scale-down's confirmation names what each policy removes, CAPI's at random without one, and an unknown one refused", async ({ page }) => {
    const policies: [string | null, string][] = [
      ["fewest-pods", `Removes the 2 nodes running the fewest pods (fewest-pods). ${UNHEALTHY}`],
      ["least-requested", `Removes the 2 nodes with the lowest requested CPU or memory (least-requested). ${UNHEALTHY}`],
      ["least-utilized", `Removes the 2 nodes with the lowest live CPU or memory use (least-utilized). ${UNHEALTHY}`],
      [null, `Removes 2 nodes, picked at random by CAPI: the day1 file sets no scale-down policy. ${UNHEALTHY}`],
      ["newest-first", "Would remove 2 nodes by the scale-down policy “newest-first”, which the workflow does not know: the workflow will refuse it."],
    ];
    const nodepools = policies.map(([policy], index) => ({ ...OPTIONS.nodepools[0], index, name: `${ZONE_A}-${index}`, scale_down_policy: policy }));
    const scale = scaleOf({ options: { ...OPTIONS, nodepools } });
    await openNodes(page, scale);
    for (const [index, [, words]] of policies.entries()) {
      await field(page, `${ZONE_A}-${index}`).fill("1");
      await page.getByTestId(`scale-pool-${index}`).getByTestId("scale-start").click();
      await expect(page.getByTestId("scale-confirm-leaving")).toHaveText(words);
      await page.getByTestId("scale-confirm-cancel").click();
      await expect(confirmation(page)).toHaveCount(0);
    }
    expect(scale.starts).toEqual([]);
  });

  test("a locked NodePool has no stepper: its size as text, why and a restore; an unnamed one has none either", async ({ page }) => {
    await openNodes(page, scaleOf());
    const row = page.getByTestId("scale-pool-2");
    await expect(row.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(row).toContainText("3 replicas");
    await expect(row.getByTestId("scale-pool-locked")).toHaveText(`Locked by flavor ${FLAVOR} at 2.`);
    await expect(row.getByRole("button", { name: `Restore ${R760} to 2 replicas with update-nodepool` })).toBeVisible();
    const unnamed = page.getByTestId("scale-pool-3");
    await expect(unnamed.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(unnamed).toContainText("its NodePool cannot be named");
  });

  test("live status on: each NodePool scales on its card, and the sizes fold to a line", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    await expect(page.getByTestId("scale-summary")).toContainText("4 NodePools, 10 replicas, as the day1 file sets them; each card below scales its own.");
    // Only the entry no card shows stays a row
    await expect(page.getByTestId("scale-pool-0")).toHaveCount(0);
    await expect(page.getByTestId("scale-pool-3")).toContainText("its NodePool cannot be named");
    await expect(stepper(page, ZONE_A)).toHaveCount(1);

    const a = card(page, ZONE_A);
    await expect(a.getByTestId("scale-card-control")).toContainText("Replicas");
    await expect(a.getByTestId("node-pool-ready")).toContainText("3 / 3 ready");
    await a.getByRole("button", { name: `One replica more for ${ZONE_A}` }).click();
    await expect(a.getByTestId("scale-change")).toHaveText("Replicas 3 → 4 (+1)");
    // One change at a time, across the cards
    await card(page, ZONE_B).getByRole("button", { name: `One replica more for ${ZONE_B}` }).click();
    await expect(a.getByTestId("scale-pending")).toHaveCount(0);
    await expect(field(page, ZONE_A)).toHaveValue("3");
    await card(page, ZONE_B).getByTestId("scale-start").click();
    await expect(confirmation(page).getByRole("heading", { name: `Scale up ${ZONE_B}?` })).toBeVisible();
    await yes(page).click();
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Pending");
    expect(scale.starts).toEqual([{ nodepool: ZONE_B, replicas: 4 }]);
  });

  test("on the cards: a locked NodePool says why and restores there; one the file does not name has no stepper", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { nodes: CARDS });
    const r760 = card(page, R760);
    await expect(r760.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(r760.getByTestId("scale-card-control")).toHaveText("3 replicas");
    await expect(r760.getByTestId("scale-pool-locked")).toHaveText(`Locked by flavor ${FLAVOR} at 2.`);
    await r760.getByRole("button", { name: `Restore ${R760} to 2 replicas with update-nodepool` }).click();
    await r760.getByTestId("restore-start").click();
    await expect(r760.getByTestId("restore-started")).toContainText(`update-nodepool started (${RUN_ID}): its run shows under NodePool sizes.`);
    expect(scale.starts).toEqual([{ nodepool: R760, replicas: 2 }]);

    const extra = card(page, "prod-lark-site1-extra");
    await expect(extra.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(extra.getByTestId("scale-card-unmatched")).toHaveText("Not named in the day1 file");
  });

  test("the run in place: the workflow's phase and its child's, then the plan and the servers chosen, a run by kind too", async ({ page }) => {
    const scale = scaleOf({
      run: run({
        phase: "scaling-down", direction: "down",
        child: { workflow_id: `scale-down-nodepool-${LARK}`, status: "running", phase: "marking-machines", error: null },
      }),
    });
    await openNodes(page, scale);
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Scaling down · Marking machines");
    await expect(page.getByTestId("scale-run")).toContainText(`scale-down-nodepool-${LARK}`);
    await expect(page.getByTestId("scale-run")).toContainText("The workflow reports each NodePool before and after once it completes.");

    scale.run = DONE;
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    const runCard = page.getByTestId("scale-run");
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Completed");
    await expect(runCard.getByRole("heading", { level: 3, name: "Scale kind dell-r660-site1-zone" })).toBeVisible();
    await expect(page.getByTestId(`scale-run-pool-${ZONE_B}`)).toContainText("3 → 2");
    await expect(page.getByTestId(`scale-run-pool-${ZONE_B}`)).toContainText("fewest-pods");
    await expect(page.getByTestId(`scale-run-pool-${ZONE_A}`)).toContainText("none: CAPI picks at random");
    await expect(page.getByTestId("scale-run-total")).toContainText("6 → 5");
    await expect(page.getByTestId("scale-run-chosen")).toContainText(`worker-7 (${ZONE_B}-7xk2p) · ${ZONE_B} · fewest-pods: 1 workload pods`);
    await expect(page.getByTestId("scale-run-commit")).toContainText("Committed 9f2c1ab77d to day1 main");
    await expect(page.getByTestId("scale-run-ignored")).toHaveCount(0);
  });

  test("a run that did not scale down lists, in the workflow's words, what it did not use", async ({ page }) => {
    await openNodes(page, scaleOf({ run: UP_IGNORING }));
    const runCard = page.getByTestId("scale-run");
    await expect(runCard.getByRole("heading", { level: 3, name: `Scale NodePool ${ZONE_A}` })).toBeVisible();
    await expect(page.getByTestId(`scale-run-pool-${ZONE_A}`)).toContainText("3 → 4");
    const ignored = page.getByTestId("scale-run-ignored");
    await expect(ignored).toContainText("Not used: the run did not scale down");
    await expect(ignored.getByRole("listitem")).toHaveText(["server_names ocp-r660-site1-hp0001592: the NodePool scales up"]);
    await expect(page.getByTestId("scale-run-chosen")).toHaveCount(0);
  });

  test("a 409 is shown in the orchestrator's words, nothing is sent again, and the run is read again", async ({ page }) => {
    const words = `An update-nodepool run is already in flight for cluster ${LARK}`;
    const scale = scaleOf({ start: (route) => fulfillProblem(route, 409, "SCALE_ALREADY_RUNNING", words) });
    await openNodes(page, scale);
    await more(page, ZONE_A).click();
    const reads = scale.runReads;
    await page.getByTestId("scale-start").click();
    await yes(page).click();
    const refused = confirmation(page).getByTestId("scale-error");
    await expect(refused).toContainText("update-nodepool refused to start: a run of this cluster is going.");
    await expect(refused).toContainText(words);
    await expect(yes(page)).toBeDisabled();
    // Nothing more can be sent from it: Close leaves the change, its refusal shown under it
    await page.getByTestId("scale-confirm-cancel").filter({ hasText: "Close" }).click();
    await expect(confirmation(page)).toHaveCount(0);
    await expect(page.getByTestId("scale-pending").getByTestId("scale-error")).toContainText(words);
    await expect(page.getByTestId("scale-start")).toBeDisabled();
    await expect(page.getByTestId("scale-cancel")).toBeEnabled();
    await expect.poll(() => scale.runReads).toBeGreaterThan(reads);
    expect(scale.starts).toHaveLength(1);
  });

  test("an orchestrator without update-nodepool: the tab loads, and only Scale says it is not deployed yet", async ({ page }) => {
    const words =
      `update-nodepool is not deployed on this orchestrator yet (it has no POST /workflows/server-lifecycle/update-nodepool): ` +
      `nothing was started for ${LARK}. Scaling works as soon as the workflow is deployed there, with no change to Wingman.`;
    const scale = scaleOf({ start: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", words) });
    await openNodes(page, scale);
    await expect(page.getByTestId("scale-run")).toHaveCount(0);
    await expect(page.getByTestId("scale-error")).toHaveCount(0);
    await more(page, ZONE_A).click();
    await page.getByTestId("scale-start").click();
    await yes(page).click();
    const refused = confirmation(page).getByTestId("scale-error");
    await expect(refused).toContainText("Nothing started: the workflows orchestrator could not start update-nodepool.");
    await expect(refused).toContainText(words);
    expect(scale.starts).toHaveLength(1);
  });

  test("a failed run says why in the workflow's words, with its type", async ({ page }) => {
    const words = `scale-down-nodepool-${LARK} failed — ArgoSyncRefusedError: the Application ${LARK} has other changes pending. Its history has the detail`;
    await openNodes(page, scaleOf({ run: run({ status: "failed", phase: "scaling-down", direction: "down", error: words, error_type: "ArgoSyncRefusedError" }) }));
    await expect(page.getByTestId("scale-run-phase")).toHaveText("Failed");
    const error = page.getByTestId("scale-run-error");
    await expect(error).toContainText("ArgoSyncRefusedError");
    await expect(error).toContainText(words);
    await expect(page.getByTestId("scale-run-error-hint")).toHaveCount(0);
    // A closed run does not hold the steppers back
    await expect(field(page, ZONE_A)).toBeEnabled();
    await expect(page.getByTestId("scale-busy-reason")).toHaveCount(0);
  });

  test("named servers a scale-down could not remove fail the run with a plain line under the workflow's words", async ({ page }) => {
    const words = `scale-down-nodepool-${LARK} failed — ScaleDownServersInvalidError: NodePool ${ZONE_B}: the servers named cannot be the ones that leave. Nothing was marked or written`;
    const failed = run({ status: "failed", phase: "scaling-down", direction: "down", error: words, error_type: "ScaleDownServersInvalidError" });
    await openNodes(page, scaleOf({ run: failed }));
    const error = page.getByTestId("scale-run-error");
    await expect(error).toContainText("ScaleDownServersInvalidError");
    await expect(error).toContainText(words);
    await expect(page.getByTestId("scale-run-error-hint")).toContainText("The servers named to leave cannot be the ones this scale-down removes");
    await expect(page.getByTestId("scale-run-error-hint")).toContainText("Nothing was marked or written.");
  });

  test("an open upgrade of the cluster leaves no stepper, and says why once", async ({ page }) => {
    const upgrade = { workflow_id: `upgrade-cluster-${LARK}`, status: "running", phase: "awaiting-approval" } as UpgradeRun;
    await openNodes(page, scaleOf(), { upgrade, nodes: CARDS });
    const why = "An upgrade-cluster run of this cluster is open";
    await expect(page.getByTestId("scale-busy-reason")).toContainText(why);
    await expect(page.getByText(why)).toHaveCount(1);
    // Nothing looks editable: every size is text
    await expect(page.getByTestId("scale-stepper")).toHaveCount(0);
    await expect(card(page, ZONE_A).getByTestId("scale-card-control")).toHaveText("3 replicas");
  });

  test("a locked NodePool that drifted is restored to its flavor's value by its own run", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale);
    const row = page.getByTestId("scale-pool-2");
    await expect(row).toContainText(`Locked by flavor ${FLAVOR} at 2`);
    await row.getByRole("button", { name: `Restore ${R760} to 2 replicas with update-nodepool` }).click();
    const confirm = row.getByTestId("restore-confirm");
    await expect(confirm).toContainText(`Set NodePool ${R760} from 3 → 2 replicas, the value its flavor locks?`);
    await expect(confirm.getByTestId("scale-truths")).toContainText("scale-down-policy");
    await confirm.getByTestId("restore-start").click();
    await expect(row.getByTestId("restore-started")).toContainText(`update-nodepool started (${RUN_ID}): its run shows under NodePool sizes.`);
    expect(scale.starts).toEqual([{ nodepool: R760, replicas: 2 }]);
  });
});

test.describe("A flavor sync leaves locked replicas to update-nodepool", () => {
  const drifted: ClusterDrift = {
    ...notDrifted, state: "drifted", is_drifted: true,
    value_drift: [{
      path: "nodepools[2].replicas", file_key: "nodepool[2].replicas", nodepool: { index: 2, name: R760 }, flavor_value: 2,
      cluster_value: 3, in_file: true, added: [], removed: [], needs_decision: null, needs_hardware: false, reboots: false,
    }],
  };
  const held: SyncPreview = {
    cluster: LARK, site: SITE, mce: MCE, path: DETAIL.path ?? "", last_commit_id: DETAIL.last_commit_id, spec_name: FLAVOR,
    spec_version: "1.0.0", file_spec_version: "1.0.0", changes: [], diff: "", removals: [], rebooting: [], problems: [],
    warnings: [], can_sync: false, addons_to_install: [], version_differences: [], addons_error: null,
    held_replicas: [{ index: 2, name: R760, replicas: 3, flavor_replicas: 2 }],
  };

  test("the preview lists the replicas the MR leaves out, each with a restore that sends the flavor's value", async ({ page }) => {
    const scale = scaleOf();
    await openNodes(page, scale, { drift: drifted, tab: "drift" });
    await page.route(`**/api/day1/clusters/${LARK}/sync/preview?**`, (r) => json(r, held));
    await page.getByRole("button", { name: "Sync to flavor" }).click();

    const section = page.getByTestId("sync-held-replicas");
    await expect(section).toContainText("Not in this merge request: NodePool replicas");
    await expect(section.getByTestId("sync-held-2")).toContainText(`${R760} 3 → 2`);
    await expect(page.getByTestId("sync-blocked")).toHaveText("Nothing else to sync: the replicas above change through update-nodepool.");
    await section.getByRole("button", { name: `Restore ${R760} to 2 replicas with update-nodepool` }).click();
    await section.getByTestId("restore-start").click();
    await expect(section.getByTestId("restore-started")).toContainText(`update-nodepool started (${RUN_ID})`);
    expect(scale.starts).toEqual([{ nodepool: R760, replicas: 2 }]);
  });
});

// Screenshots for the review (SCALE_SCREENSHOTS=<dir>): a card's change, a row's scale-up and scale-down
// confirmations and a done run, light and dark.
const SHOTS = process.env.SCALE_SCREENSHOTS;

/** Once the confirmation has armed and every finite animation (the dialog's, its backdrop's) has finished. */
async function settledConfirmation(page: Page) {
  await expect(yes(page)).toBeEnabled();
  await page.evaluate(() =>
    Promise.all(document.getAnimations().filter((a) => a.effect?.getTiming().iterations !== Infinity).map((a) => a.finished))
  );
  await page.mouse.move(0, 0);
}

test.describe("Scale screenshots", () => {
  test.skip(!SHOTS, "only with SCALE_SCREENSHOTS");
  for (const scheme of ["light", "dark"] as const) {
    test(`a card's change, ${scheme}`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 1000 });
      // The app starts dark (next-themes' defaultTheme); the person's choice is kept under `theme`
      await page.addInitScript((theme) => localStorage.setItem("theme", theme), scheme);
      await openNodes(page, scaleOf(), { nodes: CARDS });
      const a = card(page, ZONE_A);
      await more(page, ZONE_A).click();
      await expect(a.getByTestId("scale-change")).toHaveText("Replicas 3 → 4 (+1)");
      await page.mouse.move(0, 0);
      await page.getByTestId("scale-panel").scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${SHOTS}/scale-card-change-${scheme}.png` });
      await a.screenshot({ path: `${SHOTS}/scale-card-${scheme}.png` });
    });

    test(`a row's scale-up and scale-down confirmations and a done run, ${scheme}`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 1000 });
      await page.addInitScript((theme) => localStorage.setItem("theme", theme), scheme);
      await openNodes(page, scaleOf({ run: DONE }));
      await more(page, ZONE_A).click();
      await page.getByTestId("scale-start").click();
      await settledConfirmation(page);
      await page.screenshot({ path: `${SHOTS}/scale-confirm-up-${scheme}.png` });
      await page.keyboard.press("Escape");
      await expect(confirmation(page)).toHaveCount(0);
      await fewer(page, ZONE_B).click();
      await page.getByTestId("scale-start").click();
      await settledConfirmation(page);
      await page.screenshot({ path: `${SHOTS}/scale-confirm-down-${scheme}.png` });
      await page.keyboard.press("Escape");
      await expect(confirmation(page)).toHaveCount(0);
      await page.getByTestId("scale-run").screenshot({ path: `${SHOTS}/scale-run-${scheme}.png` });
    });
  }
});
