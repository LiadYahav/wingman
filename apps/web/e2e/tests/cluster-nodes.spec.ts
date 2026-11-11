/**
 * The cluster page's Nodes tab, by NodePool, and the uninstall of a server
 * (mocked; docs/notes/2026-11-11-cluster-nodes-api.md). Each NodePool is a
 * card: its summary, an update in progress with its progress, its problems
 * (folded when long), then its Machines, with the one being worked on set
 * apart and a waiting or missing node shown as the missing piece. Servers
 * server-scan places in the cluster that no Machine has are listed apart.
 * Wingman starts the platform's `uninstall-server-from-hc` workflow and shows
 * its run: the button is an admin's, needs the server's name typed exactly,
 * and sends only that name; the phase is the workflow's own string, and a
 * contested server keeps its button (the workflow refuses it itself).
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import {
  BOARD, fulfillProblem, go, injectAdminAuth, json, mockClusterNodes, mockDashboardApis, mockNodePool, mockNodes,
  mockNodesBoard, mockPoolNode, mockServer, mockUninstallNode,
} from "../fixtures/api-handlers";
import type { ClusterDetail, ClusterNodes, DestinationCharts, WorkflowRun } from "../../types";

const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const LARK = "ocp4-prod-lark-site1";
const R660 = "prod-lark-site1-dell-r660-site1";
const R760 = "prod-lark-site1-dell-r760-site1";
const C240 = "prod-lark-site1-cisco-c240-site1";

const DETAIL: ClusterDetail = {
  name: LARK, site: SITE, mce: MCE,
  yaml: 'owner:\n  merkaz: "1"\nmastertag: 4.18.22-x86_64\nnodepool:\n  - infraEnvName: dell-r660-site1\n    replicas: 3\n',
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${LARK}.yaml`,
  last_commit_id: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
  metadata: {
    spec_name: null, spec_version: null, created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { merkaz: "1", anaf: "2", mador: "3" }, mastertag: "4.18.22-x86_64", platform: "agent",
    nodepools: [{ name: null, infra_env_name: "dell-r660-site1", replicas: 3, allow_deletion: false, configs: [], node_labels: {}, tuning_config: null }],
    network: { vlan_id: null, dhcp_network: null }, cluster_name: null, automation_keys: [],
  },
  hosted_cluster: { cluster_name: "prod-lark-site1", name: "openshift-prod-lark-site1", namespace: "hcp-prod-lark-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "lark", sequence: null, problems: [] },
  mce_default_mastertag: "4.18.22-x86_64",
  problems: [],
  segments_manager: null,
};

const CHARTS: DestinationCharts = {
  cluster: LARK, mce: MCE, id: `hosted:${SITE}:prod:${MCE}:${LARK}`, kind: "hosted", site: SITE, env: "prod",
  ocp_version: "4.18.22", installed: [], excluded: [], warnings: [], argocd_note: "",
};

/** Sign in (as a viewer if asked), open the cluster page with `nodes` as the nodes read, and open its Nodes tab. */
async function openNodesTab(
  page: Page,
  nodes: ClusterNodes | ((route: Route) => Promise<void> | void),
  { viewer = false }: { viewer?: boolean } = {}
) {
  await injectAdminAuth(page);
  if (viewer) {
    await page.addInitScript(() => {
      const state = { state: { user: { username: "vera", groups: ["wingman-viewers"], uid: "vera", full_name: "Vera Viewer", role: "viewer" }, isAuthenticated: true }, version: 0 };
      localStorage.setItem("wingman-auth", JSON.stringify(state));
    });
  }
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters/bulk-status", (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
  await page.route(`**/api/day1/clusters/${LARK}?**`, (r) => json(r, DETAIL));
  await page.route(`**/api/day1/clusters/${LARK}/drift?**`, (r) =>
    json(r, {
      cluster: LARK, site: SITE, mce: MCE, state: "not_linked", is_drifted: false, spec_name: null, spec_version: null,
      current_spec_version: null, value_drift: [], addon_drift: [], version_differences: [], error: null,
    })
  );
  await page.route(`**/api/day2/clusters/${LARK}/history?**`, (r) => json(r, []));
  await page.route(`**/api/day2/clusters/${LARK}/addons?**`, (r) => json(r, CHARTS));
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await mockClusterNodes(page, LARK, nodes);
  await go(page, `/clusters/${LARK}?site=${SITE}&mce=${MCE}`);
  await page.getByRole("tab", { name: "Nodes" }).click();
  return page.getByTestId("cluster-nodes");
}

const pool = (page: Page, name: string) => page.getByTestId(`node-pool-${name}`);
const row = (page: Page, server: string) => page.getByTestId(`node-${server}`);
const uninstallOf = (page: Page, server: string) => row(page, server).getByRole("button", { name: `Uninstall ${server}` });

async function startUninstall(page: Page, server: string) {
  await uninstallOf(page, server).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: /server name/i }).fill(server);
  await dialog.getByRole("button", { name: "Uninstall server" }).click();
  return dialog;
}

test.describe("The Nodes tab, by NodePool", () => {
  test("one card per NodePool, with its summary in the header and each server linked to server-scan", async ({ page }) => {
    const board = mockNodesBoard();
    const tab = await openNodesTab(page, board);

    await expect(tab.locator("[data-testid^='node-pool-prod-']")).toHaveCount(3);
    const r660 = pool(page, R660);
    await expect(r660.getByRole("heading", { name: R660 })).toBeVisible();
    await expect(r660.getByTestId("node-pool-ready")).toContainText("2 / 3 ready");
    await expect(r660).toContainText("4.18.22");
    await expect(r660.getByTestId("node-pool-upgrade-type")).toHaveText("InPlace");
    await expect(r660).toContainText("infraenvs.agent-install.openshift.io=dell-r660-site1");
    await expect(pool(page, C240).getByTestId("node-pool-upgrade-type")).toHaveText("Replace");

    for (const p of board.node_pools) {
      for (const node of p.nodes) {
        if (!node.server) continue;
        const link = row(page, node.server.name).getByRole("link", { name: node.server.name });
        await expect(link).toHaveAttribute("href", node.server.url);
        await expect(link).toHaveAttribute("target", "_blank");
        await expect(link).toHaveAttribute("rel", "noopener noreferrer");
      }
    }
    // The second line: serial · hardware · Machine · Agent
    const rebooting = row(page, BOARD.rebooting.name);
    await expect(rebooting).toContainText("DL0000123");
    await expect(rebooting).toContainText("dell PowerEdge R660");
    await expect(rebooting).toContainText(`Machine ${R660}-x7k2p`);
    await expect(rebooting).toContainText("Agent Added to existing cluster, Done");
    // Health and flags; a healthy ready row stays quiet
    await expect(row(page, BOARD.readyB.name).getByTestId("node-health")).toHaveText("Warning");
    await expect(row(page, BOARD.readyB.name).getByTestId("node-flag-maintenance")).toBeVisible();
    await expect(row(page, BOARD.readyA.name).getByTestId("node-state")).toHaveText("Ready");
    await expect(row(page, BOARD.readyA.name).getByTestId("node-health")).toHaveText("Healthy");
  });

  test("an in-place update shows its progress, and the node it works on stands out", async ({ page }) => {
    await openNodesTab(page, mockNodesBoard());
    const r660 = pool(page, R660);

    const update = r660.getByTestId("node-pool-update");
    await expect(update).toContainText("Updating version");
    await expect(update.getByTestId("node-pool-update-progress")).toHaveText("1 of 3 nodes updated");
    const bar = update.getByRole("progressbar", { name: "Nodes updated" });
    await expect(bar).toHaveAttribute("aria-valuenow", "1");
    await expect(bar).toHaveAttribute("aria-valuemax", "3");
    await expect(update).toContainText("Target Config version: 6c1f2b");

    // Exactly one node of this pool is being worked on: the one rebooting
    await expect(r660.locator("[data-current]")).toHaveCount(1);
    const current = row(page, BOARD.rebooting.name);
    await expect(current).toHaveAttribute("data-current", "true");
    await expect(current.getByTestId("node-state")).toHaveText("Not ready");
    await expect(current.getByTestId("node-activity")).toHaveText("Rebooting for the update (Node condition Ready is Unknown)");
    await expect(row(page, BOARD.readyA.name)).not.toHaveAttribute("data-current", /.*/);
  });

  test("a failed update is shown in the destructive style", async ({ page }) => {
    await openNodesTab(
      page,
      mockNodes({
        node_pools: [
          mockNodePool({
            update: { kind: "config", message: "InplaceUpgradeFailed: Node worker-2 is degraded", progress: { total: 3, updated: 1 }, failed: true },
          }),
        ],
      })
    );

    const update = pool(page, R660).getByTestId("node-pool-update");
    await expect(update).toContainText("Config update failed");
    await expect(update).toContainText("InplaceUpgradeFailed: Node worker-2 is degraded");
    await expect(update).toHaveClass(/destructive/);
  });

  test("the missing piece: a waiting Machine and a missing node are placeholders that say why", async ({ page }) => {
    await openNodesTab(page, mockNodesBoard());
    const r760 = pool(page, R760);

    await expect(r760.getByTestId("node-pool-ready")).toContainText("2 / 4 ready");
    await expect(r760.getByTestId("node-pool-free-agents")).toHaveText("0 free of 4 matching Agents");

    const waiting = r760.getByTestId(`node-placeholder-${R760}-q9w4m`);
    await expect(waiting).toContainText("Waiting for a server");
    await expect(waiting.getByTestId("node-waiting-for")).toHaveText(
      "No free Agent matches this NodePool: 4 Agents match its selector, none is free (3 bound, 1 not approved)"
    );
    await expect(waiting).toContainText(`Machine ${R760}-q9w4m`);

    const missing = r760.getByTestId("node-placeholder-missing");
    await expect(missing).toContainText("A node is missing");
    await expect(missing).toContainText("The NodePool wants more nodes than it has Machines");
    // No Machine, so no Machine name
    await expect(missing).not.toContainText(`Machine ${R760}`);
    // Nothing to uninstall in a gap
    await expect(waiting.getByRole("button")).toHaveCount(0);
    await expect(missing.getByRole("button")).toHaveCount(0);
    // A pool that is not short does not count its Agents
    await expect(pool(page, R660).getByTestId("node-pool-free-agents")).toHaveCount(0);
  });

  test("a Replace pool marks the Machines it replaces and the ones it works on", async ({ page }) => {
    await openNodesTab(page, mockNodesBoard());
    const c240 = pool(page, C240);

    await expect(c240.getByTestId("node-pool-update")).toContainText("Updating config");
    await expect(c240.getByTestId("node-pool-update").getByRole("progressbar")).toHaveCount(0);

    const draining = row(page, BOARD.draining.name);
    await expect(draining).toHaveAttribute("data-current", "true");
    await expect(draining.getByTestId("node-state")).toHaveText("Deleting");
    await expect(draining.getByTestId("node-activity")).toHaveText("Draining");
    await expect(draining.getByTestId("node-flag-outdated")).toHaveText("Will be replaced");

    const installing = row(page, BOARD.installing.name);
    await expect(installing).toHaveAttribute("data-current", "true");
    await expect(installing.getByTestId("node-activity")).toHaveText("Installing: Writing image to disk");
    await expect(installing.getByTestId("node-flag-outdated")).toHaveCount(0);

    const outdated = row(page, BOARD.outdated.name);
    await expect(outdated).not.toHaveAttribute("data-current", /.*/);
    await expect(outdated.getByTestId("node-flag-outdated")).toBeVisible();
  });

  test("a NodePool's problems fold when there are many", async ({ page }) => {
    await openNodesTab(page, mockNodesBoard());
    const problems = pool(page, R760).getByTestId("node-pool-problems");

    await expect(problems.getByRole("listitem")).toHaveCount(2);
    const more = problems.getByRole("button", { name: "Show 1 more" });
    await expect(more).toHaveAttribute("aria-expanded", "false");
    await more.click();
    await expect(problems.getByRole("listitem")).toHaveCount(3);
    await expect(problems).toContainText("AllNodesHealthy: NodeProvisioning");
    await expect(problems.getByRole("button", { name: "Show fewer" })).toHaveAttribute("aria-expanded", "true");
    // One problem is just listed
    await expect(pool(page, R660).getByTestId("node-pool-problems").getByRole("button")).toHaveCount(0);
  });

  test("servers server-scan places here that no Machine has are listed apart, with why", async ({ page }) => {
    await openNodesTab(page, mockNodesBoard());
    const group = page.getByTestId("nodes-unassigned");

    await expect(group.getByRole("heading", { name: /In server-scan, not in any NodePool/ })).toBeVisible();
    await expect(group).toContainText("no Machine on the MCE has them");
    await expect(group.getByRole("link", { name: BOARD.left.name })).toHaveAttribute("href", BOARD.left.url);
    await expect(row(page, BOARD.left.name).getByTestId("node-uninstall-run")).toContainText("Uninstall completed");
    await expect(row(page, BOARD.left.name).getByTestId("node-flag-stale")).toBeVisible();
  });

  test("a run shows the workflow's own phase in words, or its error", async ({ page }) => {
    const run = (status: string, phase: string | null, error: string | null): WorkflowRun => ({
      workflow_id: `uninstall-server-from-hc-${status}`, status, phase, error,
    });
    await openNodesTab(
      page,
      mockNodes({
        node_pools: [
          mockNodePool({
            nodes: [
              mockPoolNode(`${R660}-a`, { server: BOARD.readyA, uninstall: run("running", "wiping-disks-v2", null) }),
              mockPoolNode(`${R660}-b`, { server: BOARD.rebooting, uninstall: run("failed", null, "ServerReservedError: the server is reserved by another run") }),
            ],
          }),
        ],
      })
    );

    // A phase Wingman has never heard of is shown in words, not dropped
    const running = row(page, BOARD.readyA.name).getByTestId("node-uninstall-run");
    await expect(running).toContainText("Uninstalling");
    await expect(running.getByTestId("node-uninstall-phase")).toHaveText("Wiping disks v2");
    await expect(uninstallOf(page, BOARD.readyA.name)).toHaveCount(0);

    const failed = row(page, BOARD.rebooting.name).getByTestId("node-uninstall-run");
    await expect(failed).toContainText("Uninstall failed");
    await expect(failed).toContainText("ServerReservedError: the server is reserved by another run");
    // A re-run resumes: a failed one can be started again
    await expect(uninstallOf(page, BOARD.rebooting.name)).toBeVisible();
  });
});

test.describe("Uninstall", () => {
  test("needs the exact name, sends only it, and the node then shows its running run", async ({ page }) => {
    let current = mockNodesBoard();
    await openNodesTab(page, (r) => json(r, current));
    const target = BOARD.readyA;
    const { posts } = await mockUninstallNode(page, LARK, async (route) => {
      const running: WorkflowRun = { workflow_id: `uninstall-server-from-hc-${target.name.toLowerCase()}`, status: "running", phase: "awaiting-machine-deletion", error: null };
      current = mockNodesBoard();
      for (const p of current.node_pools) for (const n of p.nodes) if (n.server?.id === target.id) n.uninstall = running;
      await json(route, { ...running, phase: null }, 202);
    });

    await uninstallOf(page, target.name).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("This is a replacement, not a shrink.", { exact: false })).toBeVisible();
    const identity = dialog.getByTestId("uninstall-node-identity");
    await expect(identity).toContainText(`Machine ${R660}-b2c4d`);
    await expect(identity).toContainText(`NodePool ${R660}`);
    const submit = dialog.getByRole("button", { name: "Uninstall server" });
    const input = dialog.getByRole("textbox", { name: /server name/i });
    await expect(submit).toBeDisabled();
    await input.fill(target.name.slice(0, -1));
    await expect(submit).toBeDisabled();
    await input.fill(target.name.toLowerCase());
    await expect(submit).toBeDisabled();
    await input.fill(target.name);
    await expect(submit).toBeEnabled();
    await submit.click();

    await expect(page.getByText("Uninstall started")).toBeVisible();
    await expect(dialog).toHaveCount(0);
    expect(posts).toHaveLength(1);
    expect(posts[0].serverId).toBe(target.id);
    expect(posts[0].body).toEqual({ server_name: target.name });
    expect(posts[0].search.get("mce")).toBe(MCE);

    const run = row(page, target.name).getByTestId("node-uninstall-run");
    await expect(run).toContainText("Uninstalling");
    await expect(run.getByTestId("node-uninstall-phase")).toHaveText("Awaiting machine deletion");
    await expect(uninstallOf(page, target.name)).toHaveCount(0);
  });

  test("a server in no NodePool can be uninstalled too", async ({ page }) => {
    await openNodesTab(page, mockNodesBoard({ unassigned: [{ ...BOARD.left, uninstall: null }] }));
    const { posts } = await mockUninstallNode(page, LARK);

    await uninstallOf(page, BOARD.left.name).click();
    await expect(page.getByRole("dialog").getByTestId("uninstall-node-identity")).toContainText("in no NodePool");
    await page.getByRole("dialog").getByRole("textbox", { name: /server name/i }).fill(BOARD.left.name);
    await page.getByRole("dialog").getByRole("button", { name: "Uninstall server" }).click();
    await expect(page.getByText("Uninstall started")).toBeVisible();
    expect(posts[0].body).toEqual({ server_name: BOARD.left.name });
  });

  test("a contested server keeps its button, with its flag shown", async ({ page }) => {
    const contested = mockServer("ocp-dell-r660-site1-64c-512gb-DL0000150", { contested: true });
    await openNodesTab(page, mockNodes({ node_pools: [mockNodePool({ nodes: [mockPoolNode(`${R660}-z`, { server: contested })] })] }));

    await expect(row(page, contested.name).getByTestId("node-flag-contested")).toBeVisible();
    await expect(uninstallOf(page, contested.name)).toBeEnabled();
  });

  test("a 409 UNINSTALL_ALREADY_RUNNING is shown in the dialog, which offers no retry", async ({ page }) => {
    await openNodesTab(page, mockNodesBoard());
    await mockUninstallNode(page, LARK, (route) =>
      fulfillProblem(route, 409, "UNINSTALL_ALREADY_RUNNING", "the orchestrator already runs an uninstall of this server")
    );

    const dialog = await startUninstall(page, BOARD.readyA.name);
    const problem = dialog.getByTestId("uninstall-node-error");
    await expect(problem).toContainText("An uninstall of this server is already running");
    await expect(problem).toContainText("the orchestrator already runs an uninstall of this server");
    await expect(dialog.getByRole("button", { name: "Uninstall server" })).toBeDisabled();
    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(dialog).toHaveCount(0);
  });

  test("a 409 NODE_NOT_IN_CLUSTER and a 504 AMBIGUOUS_WRITE say what they mean", async ({ page }) => {
    await openNodesTab(page, mockNodesBoard());
    let answer: "moved" | "unconfirmed" = "moved";
    await mockUninstallNode(page, LARK, (route) =>
      answer === "moved"
        ? fulfillProblem(route, 409, "NODE_NOT_IN_CLUSTER", "no Machine of ocp4-prod-lark-site1 leads to this server")
        : fulfillProblem(route, 504, "AMBIGUOUS_WRITE", "the orchestrator did not answer the start")
    );

    let dialog = await startUninstall(page, BOARD.readyA.name);
    await expect(dialog.getByTestId("uninstall-node-error")).toContainText(
      "Neither the MCE nor server-scan places this server in this cluster any more; refresh the list."
    );
    await dialog.getByRole("button", { name: "Close" }).click();

    answer = "unconfirmed";
    dialog = await startUninstall(page, BOARD.readyA.name);
    await expect(dialog.getByTestId("uninstall-node-error")).toContainText(
      "it may have started: check the node's status before trying again"
    );
    await expect(dialog.getByRole("button", { name: "Uninstall server" })).toBeDisabled();
  });

  test("without the orchestrator there are no buttons, and an admin is told why", async ({ page }) => {
    const tab = await openNodesTab(
      page,
      mockNodesBoard({ uninstall: { available: false, detail: "the workflows orchestrator is not configured" } })
    );

    await expect(tab.getByRole("link", { name: BOARD.readyA.name })).toBeVisible();
    await expect(tab.getByRole("button", { name: /^Uninstall / })).toHaveCount(0);
    await expect(tab.getByTestId("nodes-uninstall-unavailable")).toContainText("the workflows orchestrator is not configured");
  });

  test("a viewer sees the board but no Uninstall", async ({ page }) => {
    const tab = await openNodesTab(page, mockNodesBoard(), { viewer: true });

    await expect(tab.getByRole("link", { name: BOARD.readyA.name })).toBeVisible();
    await expect(tab.getByRole("button", { name: /uninstall/i })).toHaveCount(0);
    await expect(tab.getByTestId("nodes-uninstall-unavailable")).toHaveCount(0);
  });
});

test.describe("What the tab says when a source is missing", () => {
  test("501 FEATURE_DISABLED: nodes need live status from the MCE", async ({ page }) => {
    // mockDashboardApis answers every nodes read 501 FEATURE_DISABLED
    await openNodesTab(page, (r) =>
      fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled in this deployment (CLUSTER_STATUS_ENABLED=false).")
    );

    await expect(page.getByTestId("cluster-nodes-off")).toHaveText("Nodes need live status from the MCE (CLUSTER_STATUS_ENABLED).");
  });

  test("server-scan unreadable: the Machines are listed, without links, health or Uninstall", async ({ page }) => {
    const board = mockNodesBoard();
    for (const p of board.node_pools) for (const n of p.nodes) n.server = null;
    const tab = await openNodesTab(page, { ...board, unassigned: [], server_scan_error: "server-scan did not answer: timeout" });

    await expect(tab.getByTestId("nodes-server-scan-error")).toContainText("server links and health are unavailable");
    await expect(tab.getByTestId("nodes-server-scan-error")).toContainText("server-scan did not answer: timeout");
    // The BareMetalHost name still names the server, as text
    await expect(row(page, BOARD.rebooting.name)).toContainText(BOARD.rebooting.name);
    await expect(tab.getByRole("link")).toHaveCount(0);
    await expect(tab.getByTestId("node-health")).toHaveCount(0);
    await expect(tab.getByRole("button", { name: /^Uninstall / })).toHaveCount(0);
    await expect(row(page, BOARD.rebooting.name).getByTestId("node-activity")).toBeVisible();
  });

  test("runs that could not be read are unknown, not none", async ({ page }) => {
    const tab = await openNodesTab(page, mockNodesBoard({ runs_error: "the orchestrator did not answer" }));

    await expect(tab.getByTestId("nodes-runs-error")).toContainText("whether any is running is unknown");
    await expect(tab.getByTestId("nodes-runs-error")).toContainText("the orchestrator did not answer");
  });

  test("a 502 shows the problem and a retry", async ({ page }) => {
    let fail = true;
    const tab = await openNodesTab(page, (r) =>
      fail ? fulfillProblem(r, 502, "DEPENDENCY_UNAVAILABLE", "the MCE did not answer: timeout") : json(r, mockNodesBoard())
    );

    await expect(tab.getByRole("alert")).toContainText("the MCE did not answer: timeout");
    fail = false;
    await tab.getByRole("button", { name: "Retry" }).click();
    await expect(tab.getByRole("link", { name: BOARD.readyA.name })).toBeVisible();
    await expect(tab.getByRole("alert")).toHaveCount(0);
  });
});

test.describe("The Overview's nodepools open to their nodes", () => {
  /** The cluster page on its Overview tab, with `nodes` as the nodes read. */
  async function openOverview(page: Page, nodes: ClusterNodes | ((route: Route) => Promise<void> | void)) {
    await openNodesTab(page, nodes);
    await page.getByRole("tab", { name: "Overview" }).click();
  }

  test("a nodepool opens to its MCE NodePool's nodes, each opening its server in server-scan", async ({ page }) => {
    const board = mockNodesBoard();
    await openOverview(page, board);
    // The file's nodepool has no name: the chart derives <clusterName>-<infraEnv>
    const toggle = page.getByRole("button", { name: `Show the nodes of ${R660}` });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.click();
    await expect(page.getByRole("button", { name: `Hide the nodes of ${R660}` })).toHaveAttribute("aria-expanded", "true");
    const panel = page.getByTestId("pool-nodes-inline");
    const r660 = board.node_pools.find((p) => p.name === R660)!;
    await expect(panel.getByTestId("pool-node")).toHaveCount(r660.nodes.length);
    for (const node of r660.nodes.filter((n) => n.server)) {
      const link = panel.getByRole("link", { name: `${node.server!.name}: open in server-scan (new tab)` });
      await expect(link).toHaveAttribute("href", node.server!.url);
      await expect(link).toHaveAttribute("target", "_blank");
    }
    await expect(panel).toContainText(`${r660.update!.progress!.updated} of ${r660.update!.progress!.total} updated`);
    await panel.getByRole("button", { name: /Details and uninstall in the Nodes tab/ }).click();
    await expect(page.getByRole("tab", { name: "Nodes" })).toHaveAttribute("aria-selected", "true");
  });

  test("a nodepool the MCE does not report says so", async ({ page }) => {
    await openOverview(page, mockNodes({ node_pools: [] }));
    await page.getByRole("button", { name: `Show the nodes of ${R660}` }).click();
    await expect(page.getByTestId("pool-nodes-inline")).toContainText(`The MCE reports no NodePool ${R660} yet.`);
  });

  test("without live status the opened nodepool says what the nodes need", async ({ page }) => {
    await openOverview(page, (route) => fulfillProblem(route, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
    await page.getByRole("button", { name: `Show the nodes of ${R660}` }).click();
    await expect(page.getByTestId("pool-nodes-inline")).toContainText("Nodes need live status from the MCE");
  });
});
