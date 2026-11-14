/**
 * The Server Scan area's server page (mocked; docs/notes/2026-11-13-server-scan-area-api.md
 * §9, ADR-0048's 3.25.0 amendment): server-scan's server page in Wingman, its
 * five tabs with the tab in the URL, its words and badges; History with and
 * without server-scan's auditor token; maintenance read only on the record;
 * the states; and the link into it from the Servers table (Inventory
 * Management's links: inventory.spec.ts).
 */

import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go, json } from "../fixtures/api-handlers";
import { CISCO_ID, HOST_ID, NODE, NODE_ID, VM_ID, ciscoRecord, nodeRecord, setUpServer, vmRecord } from "../fixtures/server-scan-server";

const PAGE = `/server-scan/servers/${NODE_ID}`;
const field = (page: Page, label: string) => page.getByTestId("ss-overview").locator("div").filter({ has: page.locator(`dt:text-is("${label}")`) }).locator("dd");
const tab = (page: Page, name: string) => page.getByRole("tab", { name });

test.describe("The server's page", () => {
  test("the Servers name opens it, the sidebar keeps Servers, and ← Servers returns to the view it came from", async ({ page }) => {
    await setUpServer(page);
    await go(page, "/server-scan/servers?vendor=dell&sort=name");
    const row = page.locator(`[data-testid="ss-server-row"][data-server="${NODE}"]`);
    await expect(row.getByRole("button", { name: `Copy server name ${NODE}` })).toBeAttached();
    await row.getByRole("link", { name: NODE, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/server-scan/servers/${NODE_ID}$`));
    await expect(page.getByRole("heading", { level: 1, name: NODE })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Server Scan" }).getByTestId("area-nav-servers")).toHaveAttribute("aria-current", "page");
    await page.getByTestId("ss-back").click();
    await expect(page).toHaveURL(/\/server-scan\/servers\?vendor=dell&sort=name$/);
  });

  test("Overview: server-scan's header and fields, in its words", async ({ page }) => {
    await setUpServer(page);
    await go(page, PAGE);
    await expect(page.getByTestId("ss-server-model")).toHaveText("PowerEdge R660");
    await expect(page.getByRole("link", { name: `Open BMC console for ${NODE}` })).toHaveAttribute("href", "https://192.0.2.101");
    await expect(page.getByRole("button", { name: `Copy server name ${NODE}` })).toBeVisible();
    await expect(tab(page, "Overview")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tablist").getByRole("tab")).toHaveText(["Overview", "Hardware", "Network", "Connectivity", "History"]);
    await expect(field(page, "Serial")).toHaveText("DL0101");
    await expect(field(page, "Manager")).toHaveText("openmanage-site1");
    const openshift = page.getByTestId("ss-openshift");
    await expect(openshift.getByTestId("ss-installation")).toHaveText("Installed");
    await expect(openshift).toContainText("ocp4-prod-lark-site1");
    await expect(openshift).toContainText("MCE ocp4-prod-mce-site1-a");
    // OpenManage: no Connectivity, no GPU row; RAID with who answered
    const breakdown = page.getByTestId("ss-health-breakdown");
    await expect(breakdown.locator("[data-category]")).toHaveText([
      "Memory●Healthy", "Storage▲Warning", "RAID●HealthyiDRAC9 · redfish_storage", "Network●Healthy", "Power●Healthy", "BMC●Healthy", "Name●Healthy",
    ]);
    await expect(page.getByRole("list", { name: "Why this health" })).toHaveCount(0);
    await expect(field(page, "Last seen")).toHaveText("3 hours ago");
    await expect(field(page, "Vendor")).toHaveText("dell");
    await expect(field(page, "Deployment template")).toHaveText("R660-Standard");
    await expect(field(page, "Site")).toHaveText("site1");
    await expect(field(page, "Classification")).toHaveText("HOSTED_CLUSTER");
    await expect(field(page, "Matched rule")).toHaveText("Hosted cluster nodes (name ~ ^ocp-)");
    await expect(field(page, "Overall health")).toHaveText("●Healthy");
    await expect(page.getByTestId("ss-maintenance")).toContainText("Not in maintenance");
    await expect(field(page, "Last changed")).toHaveText(/^13\/11\/2026, 10:00:00/);
    await expect(page.getByTestId("ss-collection")).toHaveCount(0);
  });

  test("Overview of a server in trouble: why, the install lock, a rename, a second claimant, its BMC refusing", async ({ page }) => {
    await setUpServer(page, { records: [ciscoRecord()] });
    await go(page, `/server-scan/servers/${CISCO_ID}`);
    await expect(page.getByTestId("ss-server-model")).toHaveText("A100 (from GPU)");
    const why = page.getByRole("list", { name: "Why this health" });
    await expect(why.getByRole("listitem")).toHaveText([
      "◆CriticalStorage4.80 TB of storage, but the name promises 10.00 TB",
      "⬟MajorConnectivityA fabric path is down",
    ]);
    // Cisco: Connectivity yes, BMC no
    await expect(page.locator('[data-category="connectivity"]')).toBeVisible();
    await expect(page.locator('[data-category="bmc"]')).toHaveCount(0);
    const openshift = page.getByTestId("ss-openshift");
    await expect(openshift.getByTestId("ss-reservation")).toHaveText("→Installing to ocp4-prod-mce-site1-b");
    await expect(openshift.getByTestId("ss-reservation")).toHaveAttribute("title", /InfraEnv ucs-c240 · held by add-server-to-mce · lock has no expiry/);
    await expect(openshift).toContainText("Name mismatchInstalled as ucs-cisco-site2-old-07");
    await expect(openshift).toContainText("Duplicate serverAlso claimed by ocp4-upi-other as ocp-old-node-07");
    await expect(field(page, "Server profile template")).toHaveText("upi-worker-spt");
    await expect(field(page, "Last seen")).toContainText("Stale");
    await expect(page.getByTestId("ss-collection")).toContainText(/Wrong credentials since 12\/11\/2026, 08:00:00/);
    const maintenance = page.getByTestId("ss-maintenance");
    await expect(maintenance).toContainText("PSU swap - by API token (admin)");
    await expect(maintenance.getByText("PSU swap - by API token (admin)")).toHaveAttribute("title", /^Since 12\/11\/2026, 11:00:00.*expected to end 14\/11\/2026, 16:00:00/);
  });

  test("a VM's Host: its node and cluster, and the server it runs on linked to its page", async ({ page }) => {
    const host = nodeRecord({ id: HOST_ID, name: "ocp-dell-r760-site1-virt-03" });
    await setUpServer(page, { records: [vmRecord(), host] });
    await go(page, `/server-scan/servers/${VM_ID}`);
    const vmHost = page.getByTestId("ss-vm-host");
    await expect(vmHost).toContainText("worker-3 · cluster ocp4-prod-virt-site1");
    await expect(vmHost).toContainText("CPU AMD EPYC 9654");
    await expect(vmHost).toContainText("▲Warning");
    await expect(vmHost).toContainText("Maintenance");
    // A VM has no BMC, power, RAID or template to judge
    await expect(page.locator('[data-category]')).toHaveText(["Memory●Healthy", "Storage▲Warning", "Network●Healthy", "Name●Healthy"]);
    await expect(page.getByRole("link", { name: /Open BMC console/ })).toHaveCount(0);
    await vmHost.getByRole("link", { name: "ocp-dell-r760-site1-virt-03" }).click();
    await expect(page).toHaveURL(new RegExp(`/server-scan/servers/${HOST_ID}$`));
    await expect(page.getByRole("heading", { level: 1, name: "ocp-dell-r760-site1-virt-03" })).toBeVisible();
  });

  test("Hardware: CPU, memory, drives smallest first, PSUs; an unread field says so", async ({ page }) => {
    await setUpServer(page, { records: [nodeRecord(), ciscoRecord()] });
    await go(page, PAGE);
    await tab(page, "Hardware").click();
    await expect(page).toHaveURL(/\?tab=hardware$/);
    const hardware = page.getByTestId("ss-hardware");
    await expect(hardware.getByRole("region", { name: "CPU" })).toContainText("Intel(R) Xeon(R) Platinum 8462Y+");
    await expect(hardware.getByRole("region", { name: "Memory" })).toContainText("1024.0 GiB total (16 modules)");
    await expect(hardware.getByRole("region", { name: "Storage" })).toContainText("4.80 TB total");
    await expect(page.getByTestId("ss-drive")).toHaveText([/^MZ7L3960S6XX00SSD960\.0 GB▲Warning\(Predictive failure\)$/, /^MZ7L33T8S6XX01SSD3\.84 TB●Healthy\(OK\)$/]);
    await expect(hardware.getByRole("region", { name: "GPU" })).toContainText("No GPUs.");
    await expect(page.getByTestId("ss-psu")).toHaveText(["PWR SPLY,1400W — 1400W rated, 312W now ●Healthy", "PSU.Slot.2 —"]);
    // A Cisco GPU's health is its own word; unread memory is carried forward, unread drives never read
    await go(page, `/server-scan/servers/${CISCO_ID}?tab=hardware`);
    await expect(page.getByTestId("ss-gpu")).toContainText("NVIDIA A100 80GB");
    await expect(page.getByTestId("ss-gpu")).toContainText("80.0 GiB");
    await expect(page.getByTestId("ss-gpu")).toContainText("UP");
    await expect(page.getByRole("region", { name: "Memory" }).getByTestId("ss-unconfirmed")).toContainText("512.0 GiB total (0 modules)unconfirmed");
    await expect(page.getByRole("region", { name: "Storage" }).getByTestId("ss-unconfirmed")).toContainText("MZ7L3960");
  });

  test("Network: the BMC with a copy button, each interface in words, an OS name marked derived", async ({ page }) => {
    await setUpServer(page);
    await go(page, `${PAGE}?tab=network`);
    await expect(tab(page, "Network")).toHaveAttribute("aria-selected", "true");
    const network = page.getByTestId("ss-network");
    await expect(network.getByRole("region", { name: "BMC" })).toContainText("192.0.2.101");
    await expect(network.getByRole("button", { name: "Copy BMC address 192.0.2.101" })).toBeVisible();
    await expect(network.getByRole("region", { name: "BMC" })).toContainText("02:00:00:00:01:ff");
    const interfaces = page.getByTestId("ss-interface");
    await expect(interfaces.nth(0)).toContainText("Onboard · port 1·MAC #1·25000 Mbps·UP");
    await expect(interfaces.nth(0)).toContainText("OS name (derived): eno12399np0");
    await expect(interfaces.nth(1)).toContainText("Slot 8 · port 1·MAC #2·—·DOWN");
    await expect(interfaces.nth(1)).not.toContainText("OS name");
  });

  test("Connectivity: the fabric paths and a card per fabric, the vNICs left out; none on a Dell", async ({ page }) => {
    await setUpServer(page, { records: [nodeRecord(), ciscoRecord()] });
    await go(page, `/server-scan/servers/${CISCO_ID}?tab=connectivity`);
    await expect(page.getByTestId("ss-fabric-paths")).toHaveText("2/3 fabric paths up");
    const fabrics = page.getByTestId("ss-fabric");
    await expect(fabrics.locator("h3")).toHaveText(["Fabric A", "Fabric B", "Fabric Other"]);
    await expect(fabrics.nth(0).locator("li")).toHaveCount(1);
    await expect(fabrics.nth(0)).toContainText("FI-A-SITE2");
    await expect(fabrics.nth(0)).toContainText("Fabric portEthernet1/17");
    await expect(fabrics.nth(1).getByTestId("ss-link-state")).toHaveText("DOWN");
    await go(page, `${PAGE}?tab=connectivity`);
    await expect(page.getByTestId("ss-connectivity")).toHaveText("No connectivity data.");
  });

  test("the tab is in the URL; an unknown one opens Overview", async ({ page }) => {
    await setUpServer(page);
    await go(page, `${PAGE}?tab=nodes`);
    await expect(tab(page, "Overview")).toHaveAttribute("aria-selected", "true");
    await tab(page, "Connectivity").click();
    await expect(page).toHaveURL(/\?tab=connectivity$/);
    await tab(page, "Overview").click();
    await expect(page).toHaveURL(new RegExp(`/server-scan/servers/${NODE_ID}$`));
  });
});

test.describe("History", () => {
  test("the server's trail, newest first, with details and pages", async ({ page }) => {
    const calls = await setUpServer(page);
    await go(page, PAGE);
    expect(calls.history).toEqual([]);
    await tab(page, "History").click();
    await expect(page).toHaveURL(/\?tab=history$/);
    const events = page.getByTestId("ss-event");
    await expect(events).toHaveCount(2);
    await expect(events.nth(0)).toContainText("MAINTENANCE_ENABLED");
    await expect(events.nth(0)).toContainText("API token (admin)token");
    await expect(events.nth(0).locator("time")).toHaveText(/^12\/11\/2026, 11:14:00/);
    await expect(events.nth(1).getByRole("group", { name: "HEALTHY → WARNING" })).toBeVisible();
    await events.nth(0).getByRole("button", { name: "▸ Details" }).click();
    await expect(page.getByTestId("ss-event-details")).toContainText("Put into maintenance by API token (admin): Replacing PSU 2 — INC-4417");
    await events.nth(1).getByRole("button", { name: "▸ Details" }).click();
    const health = page.getByTestId("ss-event-details").nth(1);
    await expect(health.getByRole("region", { name: "FROM" })).toContainText("nothing failing");
    await expect(health.getByRole("region", { name: "TO" })).toContainText("Disk.Bay.0 predicts failure");
    const pager = page.getByTestId("ss-history-pager");
    await expect(pager).toContainText("Page 1 of 2");
    await pager.getByRole("button", { name: "Next" }).click();
    await expect(events).toHaveCount(1);
    await expect(events.nth(0)).toContainText("SERVER_CREATED");
    await expect(pager).toContainText("Page 2 of 2");
    await expect(pager.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(calls.history).toEqual(["", "c2"]);
    await pager.getByRole("button", { name: "Previous" }).click();
    await expect(events).toHaveCount(2);
    expect(calls.history).toEqual(["", "c2"]);
  });

  test("without server-scan's auditor token it says so in one line, and asks nothing", async ({ page }) => {
    const detail =
      "History needs server-scan's auditor token: add the key auditor-token to the server-scan Secret and restart day1 (SERVER_SCAN_AUDITOR_TOKEN).";
    const calls = await setUpServer(page, { records: [nodeRecord({ history_available: false, history_detail: detail })] });
    await go(page, `${PAGE}?tab=history`);
    await expect(page.getByTestId("ss-history-off")).toHaveText(detail);
    await expect(page.getByTestId("ss-event")).toHaveCount(0);
    expect(calls.history).toEqual([]);
  });

  test("a refused auditor token is day1's problem; an empty trail says so", async ({ page }) => {
    const refused = "server-scan refused Wingman's auditor token (403) reading the history of srv_x: check SERVER_SCAN_AUDITOR_TOKEN";
    await setUpServer(page, { history: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", refused) });
    await go(page, `${PAGE}?tab=history`);
    await expect(page.getByTestId("ss-history").getByRole("alert")).toContainText(refused);
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await setUpServer(page, { history: (route) => json(route, { items: [], page: { next_cursor: null, has_more: false, page_size: 50, total: 0 } }) });
    await go(page, `${PAGE}?tab=history`);
    await expect(page.getByTestId("ss-history-empty")).toHaveText("No events recorded.");
  });
});

test.describe("The page's states", () => {
  test("no such server: says so, with a link to Servers", async ({ page }) => {
    await setUpServer(page);
    await go(page, "/server-scan/servers/srv_gone");
    await expect(page.getByTestId("ss-server-not-found")).toContainText("No server srv_gone");
    await page.getByTestId("ss-server-not-found").getByRole("link", { name: "Servers" }).click();
    await expect(page).toHaveURL(/\/server-scan\/servers$/);
  });

  test("server-scan failing shows day1's problem; a viewer and an unset area are told why", async ({ page }) => {
    const down = "server-scan unreachable reading server srv_x: ConnectError";
    await setUpServer(page, { record: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", down) });
    await go(page, PAGE);
    await expect(page.getByRole("alert").filter({ hasText: "The server could not be loaded from server-scan" })).toContainText(down);
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await setUpServer(page, { record: (route) => fulfillProblem(route, 403, "FORBIDDEN", "This needs the admin role.") });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-forbidden")).toBeVisible();
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await setUpServer(page, { record: (route) => fulfillProblem(route, 501, "FEATURE_DISABLED", "Server Scan is not set up in this deployment: SERVER_SCAN_URL is empty.") });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-off")).toBeVisible();
  });
});

test.describe("Maintenance on the record", () => {
  test("is read only, as in server-scan, with a link to switch it from Servers", async ({ page }) => {
    const calls = await setUpServer(page);
    await go(page, PAGE);
    const block = page.getByTestId("ss-maintenance");
    await expect(block).toContainText("Not in maintenance");
    await expect(block.getByTestId("ss-maintenance-toggle")).toHaveCount(0);
    const link = block.getByTestId("ss-maintenance-switch");
    await expect(link).toHaveText("Switch on Servers");
    await expect(link).toHaveAttribute("href", `/server-scan/servers?search=${encodeURIComponent(NODE)}`);
    expect(calls.changes).toEqual([]);
  });
});
