/**
 * A cluster's nodes, as server-scan reports them, and the uninstall of one
 * (mocked; docs/notes/2026-11-11-cluster-nodes-api.md). A list row reads its
 * nodes only once opened, and the cluster page has them on a Nodes tab; each
 * name links to the server in server-scan. Wingman starts the platform's
 * `uninstall-server-from-hc` workflow and shows its run: the button is an
 * admin's, needs the server's name typed exactly, and sends only that name;
 * the phase is the workflow's own string, and a contested node keeps its
 * button (the workflow refuses such a server itself).
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import {
  fulfillProblem, go, injectAdminAuth, json, mockClusterNodes, mockDashboardApis, mockNode, mockNodes, mockUninstallNode,
} from "../fixtures/api-handlers";
import type { ClusterDetail, ClusterNodes, ClusterStatus, DestinationCharts } from "../../types";

const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const LARK = "ocp4-prod-lark-site1";
const HERZI = "ocp4-prod-herzi-site1";

const DL123 = mockNode();
const DL124 = mockNode({
  id: "srv_1e59242b5fdd5c5dadd9ffd7f0835532",
  name: "ocp-dell-r660-site1-64c-512gb-DL0000124",
  url: "https://server-scan.example/servers/srv_1e59242b5fdd5c5dadd9ffd7f0835532",
  serial: "DL0000124",
  health: "WARNING",
  maintenance: true,
});
const CS77 = mockNode({
  id: "srv_2f6a353c6aee6d6ebeeaa0e8a1946643",
  name: "ocp-cisco-c240-site1-96c-768gb-CS0000077",
  url: "https://server-scan.example/servers/srv_2f6a353c6aee6d6ebeeaa0e8a1946643",
  serial: "CS0000077",
  vendor: "cisco",
  model: "UCS C240 M7",
  health: "UNKNOWN",
  reachable: false,
  stale: true,
});
const NODES = mockNodes([CS77, DL123, DL124]);

function listItem(name: string): ClusterStatus {
  const short = name.replace(/^ocp4-/, "");
  return {
    name, site: SITE, mce: MCE, phase: "Unknown", spec_name: null, spec_version: null,
    created_by: "alice", created_at: "2026-11-07T10:00:00+00:00", mastertag: "4.16.27-x86_64",
    path: `sites/${SITE}/mces/${MCE}/hostedClusters/${name}.yaml`,
    hosted_cluster: { cluster_name: short, name: `openshift-${short}`, namespace: `hcp-${short}` },
    naming: { follows_convention: true, env: "prod", short_name: short.split("-")[1], sequence: null, problems: [] },
    owner: { merkaz: "1234", anaf: "56", mador: "7" },
    problems: [],
  };
}

const DETAIL: ClusterDetail = {
  name: LARK, site: SITE, mce: MCE,
  yaml: 'owner:\n  merkaz: "1"\nmastertag: 4.16.27-x86_64\nnodepool:\n  - infraEnvName: dell\n    replicas: 3\n',
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${LARK}.yaml`,
  last_commit_id: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
  metadata: {
    spec_name: null, spec_version: null, created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { merkaz: "1", anaf: "2", mador: "3" }, mastertag: "4.16.27-x86_64", platform: "agent",
    nodepools: [{ name: null, infra_env_name: "dell", replicas: 3, allow_deletion: false, configs: [], node_labels: {}, tuning_config: null }],
    network: { vlan_id: null, dhcp_network: null }, cluster_name: null, automation_keys: [],
  },
  hosted_cluster: { cluster_name: "prod-lark-site1", name: "openshift-prod-lark-site1", namespace: "hcp-prod-lark-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "lark", sequence: null, problems: [] },
  mce_default_mastertag: "4.16.27-x86_64",
  problems: [],
};

async function signIn(page: Page, { viewer = false }: { viewer?: boolean } = {}) {
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
}

async function openList(page: Page, opts: { viewer?: boolean } = {}) {
  await signIn(page, opts);
  await page.route("**/api/day1/clusters", (r) => json(r, [listItem(HERZI), listItem(LARK)]));
  await page.route("**/api/day1/clusters/drift-summary", (r) => json(r, []));
}

async function openNodesTab(page: Page, nodes: ClusterNodes | ((route: Route) => Promise<void> | void), opts: { viewer?: boolean } = {}) {
  await signIn(page, opts);
  await page.route(`**/api/day1/clusters/${LARK}?**`, (r) => json(r, DETAIL));
  await page.route(`**/api/day1/clusters/${LARK}/drift?**`, (r) =>
    json(r, {
      cluster: LARK, site: SITE, mce: MCE, state: "not_linked", is_drifted: false, spec_name: null, spec_version: null,
      current_spec_version: null, value_drift: [], addon_drift: [], version_differences: [], error: null,
    })
  );
  await page.route(`**/api/day2/clusters/${LARK}/history?**`, (r) => json(r, []));
  await page.route(`**/api/day2/clusters/${LARK}/addons?**`, (r) =>
    json(r, {
      cluster: LARK, mce: MCE, id: `hosted:${SITE}:prod:${MCE}:${LARK}`, kind: "hosted", site: SITE, env: "prod",
      ocp_version: "4.16.27", installed: [], excluded: [], warnings: [], argocd_note: "",
    } satisfies DestinationCharts)
  );
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await mockClusterNodes(page, LARK, nodes);
  await go(page, `/clusters/${LARK}?site=${SITE}&mce=${MCE}`);
  await page.getByRole("tab", { name: "Nodes" }).click();
  return page.getByTestId("cluster-nodes");
}

const nodeRow = (page: Page, name: string) => page.getByTestId(`node-${name}`);

test.describe("Nodes in the cluster list", () => {
  test("a row reads its nodes only once opened, and links each to server-scan", async ({ page }) => {
    await openList(page);
    let reads = 0;
    await mockClusterNodes(page, LARK, (r) => {
      reads += 1;
      return json(r, NODES);
    });
    await mockClusterNodes(page, HERZI, mockNodes([], { hosted_cluster: HERZI }));
    await go(page, "/clusters");

    const toggle = page.getByRole("button", { name: `Show nodes of ${LARK}` });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByTestId(`cluster-nodes-row-${LARK}`)).toHaveCount(0);
    expect(reads).toBe(0);

    // Opening it must not move the list's columns (the list's own header; the nodes have a table of their own)
    const widths = () =>
      page.locator("table").first().evaluate((table: HTMLTableElement) =>
        [...table.tHead!.rows[0].cells].map((th) => Math.round(th.getBoundingClientRect().width))
      );
    const before = await widths();

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    const row = page.getByTestId(`cluster-nodes-row-${LARK}`);
    await expect(row).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-controls", (await row.getAttribute("id"))!);
    await expect.poll(() => reads).toBe(1);

    for (const node of NODES.nodes) {
      const link = row.getByRole("link", { name: node.name });
      await expect(link).toHaveAttribute("href", node.url);
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
    await expect(row.getByText("3 nodes")).toBeVisible();
    expect(await widths()).toEqual(before);

    // Several rows open at once; an empty one says so
    await page.getByRole("button", { name: `Show nodes of ${HERZI}` }).click();
    await expect(page.getByTestId(`cluster-nodes-row-${HERZI}`)).toContainText("server-scan places no server in this cluster");
    await expect(row).toBeVisible();

    await toggle.click();
    await expect(row).toHaveCount(0);
    await expect(page.getByTestId(`cluster-nodes-row-${HERZI}`)).toBeVisible();
  });

  test("without server-scan, an open row says so quietly", async ({ page }) => {
    // mockDashboardApis answers every nodes read 501 FEATURE_DISABLED
    await openList(page);
    await go(page, "/clusters");
    await page.getByRole("button", { name: `Show nodes of ${LARK}` }).click();

    const row = page.getByTestId(`cluster-nodes-row-${LARK}`);
    await expect(row.getByTestId("cluster-nodes-off")).toHaveText("Nodes need server-scan, and this deployment has not configured it.");
    await expect(row.getByRole("alert")).toHaveCount(0);
  });

  test("a viewer sees the nodes but no Uninstall", async ({ page }) => {
    await openList(page, { viewer: true });
    await mockClusterNodes(page, LARK, NODES);
    await go(page, "/clusters");
    await page.getByRole("button", { name: `Show nodes of ${LARK}` }).click();

    const row = page.getByTestId(`cluster-nodes-row-${LARK}`);
    await expect(row.getByRole("link", { name: DL123.name })).toBeVisible();
    await expect(row.getByRole("button", { name: /uninstall/i })).toHaveCount(0);
  });
});

test.describe("The Nodes tab", () => {
  test("shows the same nodes, with health, state and flags", async ({ page }) => {
    const nodes = await openNodesTab(page, NODES);

    for (const node of NODES.nodes) {
      await expect(nodes.getByRole("link", { name: node.name })).toHaveAttribute("href", node.url);
    }
    await expect(nodes.getByText("3 nodes")).toBeVisible();
    await expect(nodeRow(page, DL123.name).getByTestId("node-health")).toHaveText("Healthy");
    await expect(nodeRow(page, DL123.name).getByTestId("node-state")).toHaveText("Installed");
    await expect(nodeRow(page, DL123.name)).toContainText("DL0000123");
    await expect(nodeRow(page, DL123.name)).toContainText("dell PowerEdge R660");
    await expect(nodeRow(page, DL124.name).getByTestId("node-health")).toHaveText("Warning");
    await expect(nodeRow(page, DL124.name).getByTestId("node-flag-maintenance")).toBeVisible();
    // UNKNOWN is no verdict: never shown as healthy
    await expect(nodeRow(page, CS77.name).getByTestId("node-health")).toHaveText("Unknown");
    await expect(nodeRow(page, CS77.name).getByTestId("node-flag-unreachable")).toBeVisible();
    await expect(nodeRow(page, CS77.name).getByTestId("node-flag-stale")).toBeVisible();
    // Every node an admin can uninstall
    await expect(nodes.getByRole("button", { name: /^Uninstall / })).toHaveCount(3);
  });

  test("a run shows the workflow's own phase, its error, or that it completed", async ({ page }) => {
    const nodes = mockNodes([
      mockNode({ ...CS77, uninstall: { workflow_id: "uninstall-server-from-hc-a", status: "running", phase: "wiping-disks-v2", error: null } }),
      mockNode({ ...DL123, uninstall: { workflow_id: "uninstall-server-from-hc-b", status: "failed", phase: null, error: "ServerReservedError: the server is reserved by another run" } }),
      mockNode({ ...DL124, uninstall: { workflow_id: "uninstall-server-from-hc-c", status: "completed", phase: null, error: null } }),
    ]);
    await openNodesTab(page, nodes);

    // A phase Wingman has never heard of is shown in words, not dropped
    const running = nodeRow(page, CS77.name).getByTestId("node-uninstall-run");
    await expect(running).toContainText("Uninstalling");
    await expect(running.getByTestId("node-uninstall-phase")).toHaveText("Wiping disks v2");
    await expect(nodeRow(page, CS77.name).getByRole("button", { name: /^Uninstall / })).toHaveCount(0);

    const failed = nodeRow(page, DL123.name).getByTestId("node-uninstall-run");
    await expect(failed).toContainText("Uninstall failed");
    await expect(failed).toContainText("ServerReservedError: the server is reserved by another run");
    // A re-run resumes: a failed node can be uninstalled again
    await expect(nodeRow(page, DL123.name).getByRole("button", { name: /^Uninstall / })).toBeVisible();

    await expect(nodeRow(page, DL124.name).getByTestId("node-uninstall-run")).toContainText("Uninstall completed");
  });

  test("the uninstall needs the exact name, sends only it, and the node then shows its running run", async ({ page }) => {
    let current = NODES;
    const nodes = await openNodesTab(page, (r) => json(r, current));
    const { posts } = await mockUninstallNode(page, LARK, async (route, serverId) => {
      current = mockNodes(
        NODES.nodes.map((n) =>
          n.id === serverId
            ? { ...n, uninstall: { workflow_id: `uninstall-server-from-hc-${n.name.toLowerCase()}`, status: "running", phase: "awaiting-machine-deletion", error: null } }
            : n
        )
      );
      await json(route, { workflow_id: `uninstall-server-from-hc-${DL123.name.toLowerCase()}`, status: "running", phase: null, error: null }, 202);
    });

    await nodeRow(page, DL123.name).getByRole("button", { name: `Uninstall ${DL123.name}` }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("This is a replacement, not a shrink.", { exact: false })).toBeVisible();
    await expect(dialog.getByText("Drains the node and deletes its Machine.")).toBeVisible();
    const submit = dialog.getByRole("button", { name: "Uninstall server" });
    const input = dialog.getByRole("textbox", { name: /server name/i });
    await expect(submit).toBeDisabled();

    await input.fill(DL123.name.slice(0, -1));
    await expect(submit).toBeDisabled();
    await input.fill(DL123.name.toLowerCase());
    await expect(submit).toBeDisabled();
    await input.fill(DL123.name);
    await expect(submit).toBeEnabled();
    await submit.click();

    await expect(page.getByText("Uninstall started")).toBeVisible();
    await expect(dialog).toHaveCount(0);
    expect(posts).toHaveLength(1);
    expect(posts[0].serverId).toBe(DL123.id);
    expect(posts[0].body).toEqual({ server_name: DL123.name });
    expect(posts[0].search.get("mce")).toBe(MCE);

    const run = nodeRow(page, DL123.name).getByTestId("node-uninstall-run");
    await expect(run).toContainText("Uninstalling");
    await expect(run.getByTestId("node-uninstall-phase")).toHaveText("Awaiting machine deletion");
    await expect(nodeRow(page, DL123.name).getByRole("button", { name: /^Uninstall / })).toHaveCount(0);
    await expect(nodes.getByRole("button", { name: /^Uninstall / })).toHaveCount(2);
  });

  test("a contested node still has its button, with its flag shown", async ({ page }) => {
    await openNodesTab(page, mockNodes([mockNode({ ...DL123, contested: true })]));

    await expect(nodeRow(page, DL123.name).getByTestId("node-flag-contested")).toBeVisible();
    await expect(nodeRow(page, DL123.name).getByRole("button", { name: `Uninstall ${DL123.name}` })).toBeEnabled();
  });

  test("a 409 UNINSTALL_ALREADY_RUNNING is shown in the dialog, which offers no retry", async ({ page }) => {
    await openNodesTab(page, NODES);
    await mockUninstallNode(page, LARK, (route) =>
      fulfillProblem(route, 409, "UNINSTALL_ALREADY_RUNNING", "the orchestrator already runs an uninstall of this server")
    );

    await nodeRow(page, DL123.name).getByRole("button", { name: `Uninstall ${DL123.name}` }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("textbox", { name: /server name/i }).fill(DL123.name);
    await dialog.getByRole("button", { name: "Uninstall server" }).click();

    const problem = dialog.getByTestId("uninstall-node-error");
    await expect(problem).toContainText("An uninstall of this server is already running");
    await expect(problem).toContainText("the orchestrator already runs an uninstall of this server");
    await expect(dialog.getByRole("button", { name: "Uninstall server" })).toBeDisabled();
    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(dialog).toHaveCount(0);
  });

  test("a 409 NODE_NOT_IN_CLUSTER and a 504 AMBIGUOUS_WRITE say what they mean", async ({ page }) => {
    await openNodesTab(page, NODES);
    let answer: "moved" | "unconfirmed" = "moved";
    await mockUninstallNode(page, LARK, (route) =>
      answer === "moved"
        ? fulfillProblem(route, 409, "NODE_NOT_IN_CLUSTER", "server-scan does not place this server in ocp4-prod-lark-site1")
        : fulfillProblem(route, 504, "AMBIGUOUS_WRITE", "the orchestrator did not answer the start")
    );
    const start = async () => {
      await nodeRow(page, DL123.name).getByRole("button", { name: `Uninstall ${DL123.name}` }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("textbox", { name: /server name/i }).fill(DL123.name);
      await dialog.getByRole("button", { name: "Uninstall server" }).click();
      return dialog;
    };

    let dialog = await start();
    await expect(dialog.getByTestId("uninstall-node-error")).toContainText(
      "server-scan no longer lists this server in this cluster; refresh the list."
    );
    await dialog.getByRole("button", { name: "Close" }).click();

    answer = "unconfirmed";
    dialog = await start();
    await expect(dialog.getByTestId("uninstall-node-error")).toContainText(
      "it may have started: check the node's status before trying again"
    );
    await expect(dialog.getByRole("button", { name: "Uninstall server" })).toBeDisabled();
  });

  test("without the orchestrator there are no buttons, and an admin is told why", async ({ page }) => {
    const nodes = await openNodesTab(
      page,
      mockNodes(NODES.nodes, { uninstall: { available: false, detail: "the workflows orchestrator is not configured" } })
    );

    await expect(nodes.getByRole("link", { name: DL123.name })).toBeVisible();
    await expect(nodes.getByRole("button", { name: /^Uninstall / })).toHaveCount(0);
    await expect(nodes.getByTestId("nodes-uninstall-unavailable")).toContainText("the workflows orchestrator is not configured");
  });

  test("runs that could not be read are unknown, not none", async ({ page }) => {
    const nodes = await openNodesTab(page, mockNodes(NODES.nodes, { runs_error: "the orchestrator did not answer" }));

    await expect(nodes.getByTestId("nodes-runs-error")).toContainText("whether any is running is unknown");
    await expect(nodes.getByTestId("nodes-runs-error")).toContainText("the orchestrator did not answer");
  });

  test("501 FEATURE_DISABLED shows the off note", async ({ page }) => {
    await openNodesTab(page, (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "server-scan is not configured (SERVER_SCAN_URL is empty)"));

    await expect(page.getByTestId("cluster-nodes-off")).toHaveText("Nodes need server-scan, and this deployment has not configured it.");
  });

  test("a 502 shows the problem and a retry", async ({ page }) => {
    let fail = true;
    const nodes = await openNodesTab(page, (r) =>
      fail ? fulfillProblem(r, 502, "DEPENDENCY_UNAVAILABLE", "server-scan did not answer: timeout") : json(r, NODES)
    );

    await expect(nodes.getByRole("alert")).toContainText("server-scan did not answer: timeout");
    fail = false;
    await nodes.getByRole("button", { name: "Retry" }).click();
    await expect(nodes.getByRole("link", { name: DL123.name })).toBeVisible();
    await expect(nodes.getByRole("alert")).toHaveCount(0);
  });

  test("a viewer sees no Uninstall", async ({ page }) => {
    const nodes = await openNodesTab(page, NODES, { viewer: true });

    await expect(nodes.getByRole("link", { name: DL123.name })).toBeVisible();
    await expect(nodes.getByRole("button", { name: /uninstall/i })).toHaveCount(0);
  });
});
