/**
 * The Servers page's mocks (docs/notes/2026-11-13-server-scan-area-api.md
 * §8), typed so a shape change fails `tsc`: a made-up fleet in server-scan's
 * own row shape, on the Sites fixture's sites (site1, site2, and names that
 * carry no site), and a generated fleet of production's size.
 */

import type { Page, Route } from "@playwright/test";
import { json } from "./api-handlers";
import { mockSites, setUpServerScan } from "./server-scan";
import type { SiteStatsList } from "../../types/server-scan";
import type { ServerRow, ServerRowsAnswer } from "../../types/server-scan-servers";

const FREE = { held: false, holder: null, mce_cluster: null, infra_env: null, expires_at: null } as const;

/** A healthy Dell, available, in site1; `overrides` replace its fields. */
function server(name: string, overrides: Partial<ServerRow> = {}): ServerRow {
  return {
    id: `srv_${name}`,
    name,
    vendor: "dell",
    model: "PowerEdge R660",
    site_id: "site1",
    source_provider: "OPENMANAGE",
    installation_type: "HOSTED_CLUSTER",
    health: "HEALTHY",
    maintenance: { enabled: false, reason: null, created_by: null },
    reservation: { ...FREE },
    openshift_state: "AVAILABLE",
    cluster_name: null,
    mce_name: null,
    openshift_reported_name: null,
    contested_with: null,
    profile_template_name: "R660-Standard",
    last_seen_at: "2026-11-13T08:00:00Z",
    stale: false,
    reachable: true,
    serial: name.toUpperCase().slice(-6),
    bmc_host: `192.0.2.${name.length}`,
    macs: ["02:00:00:00:01:01"],
    ...overrides,
  };
}

const LARK = { installation_type: "HOSTED_CLUSTER", openshift_state: "INSTALLED", cluster_name: "ocp4-prod-lark-site1", mce_name: "ocp4-prod-mce-site1-a" } as const;

/**
 * Twelve servers: a hosted cluster's nodes (one critical, one in maintenance
 * by a person, one a donor), an MCE's Agent with an install holding another,
 * a UPI cluster on Cisco, a contested server, a renamed one, a stale HPE, two
 * that share a name, and one whose name carries no site.
 */
export const FLEET: ServerRow[] = [
  server("ocp-dell-r660-site1-node-01", { ...LARK, bmc_host: "192.0.2.101", serial: "DL0101" }),
  server("ocp-dell-r660-site1-node-02", { ...LARK, health: "CRITICAL", serial: "DL0102" }),
  server("ocp-dell-r660-site1-node-03", {
    ...LARK,
    health: "WARNING",
    maintenance: { enabled: true, reason: "Replacing PSU 2 — INC-4417", created_by: "api-token-admin" },
  }),
  server("ocp-dell-r660-site1-node-04", { ...LARK, maintenance: { enabled: true, reason: "DONOR - DIMM B3 bad", created_by: "alice" } }),
  server("ocp-dell-r660-site1-agent-05", { installation_type: "MCE", openshift_state: "INSTALLED_TO_INVENTORY", mce_name: "ocp4-prod-mce-site1-a" }),
  server("ocp-dell-r760-site1-free-06", {
    model: "PowerEdge R760",
    reservation: { held: true, holder: "add-server-to-mce", mce_cluster: "ocp4-prod-mce-site1-b", infra_env: "dell-r760-64c", expires_at: null },
  }),
  server("ucs-cisco-site2-upi-07", {
    vendor: "cisco",
    model: "UCS C240",
    site_id: "site2",
    source_provider: "INTERSIGHT",
    installation_type: "UPI",
    openshift_state: "INSTALLED",
    cluster_name: "ocp4-upi-orca",
    health: "MAJOR",
  }),
  server("ucs-cisco-site2-upi-08", {
    vendor: "cisco",
    model: "UCS C240",
    site_id: "site2",
    source_provider: "INTERSIGHT",
    installation_type: "UPI",
    openshift_state: "INSTALLED",
    cluster_name: "ocp4-upi-orca",
    contested_with: "ocp4-upi-other",
  }),
  server("ocp-dell-r660-site2-node-09", { ...LARK, site_id: "site2", openshift_reported_name: "ocp-dell-r660-site2-old-09" }),
  server("hpe-dl380-site2-stale-10", {
    vendor: "hp",
    model: "ProLiant DL380",
    site_id: "site2",
    source_provider: "ONEVIEW",
    installation_type: "UNCLASSIFIED",
    stale: true,
    last_seen_at: "2026-11-10T08:00:00Z",
    health: "UNKNOWN",
  }),
  server("ocp-twin", { id: "srv_twin_a", model: null, bmc_host: null, serial: "TWINA" }),
  server("ocp-twin", { id: "srv_twin_b", vendor: "standalone", source_provider: "REDFISH_STANDALONE", site_id: null, installation_type: "UNCLASSIFIED", serial: "TWINB" }),
];

export function mockServers(items: ServerRow[] = FLEET, overrides: Partial<ServerRowsAnswer> = {}): ServerRowsAnswer {
  return { items, generated_at: "2026-11-13T08:00:00Z", maintenance_available: true, maintenance_detail: null, ...overrides };
}

const MODELS = ["PowerEdge R660", "PowerEdge R760", "UCS C240", "ProLiant DL380"] as const;
const VENDORS = ["dell", "dell", "cisco", "hp"] as const;

/** `n` servers over two sites, four models, every tenth in a cluster: production's size is about 3,100. */
export function bigFleet(n: number): ServerRow[] {
  return Array.from({ length: n }, (_, i) =>
    server(`srv-${String(i).padStart(4, "0")}`, {
      vendor: VENDORS[i % 4],
      model: MODELS[i % 4],
      site_id: i % 2 === 0 ? "site1" : "site2",
      health: i % 50 === 0 ? "CRITICAL" : "HEALTHY",
      cluster_name: i % 10 === 0 ? `ocp4-prod-c${i % 30}-site1` : null,
      mce_name: i % 10 === 0 ? "ocp4-prod-mce-site1-a" : null,
      openshift_state: i % 10 === 0 ? "INSTALLED" : "AVAILABLE",
    })
  );
}

type Handler = (route: Route) => Promise<void> | void;

/**
 * Sign in as an admin and mock the Sites and Servers reads. Returns how many
 * times the servers were read. Register a test's own routes after this: mocks
 * match LIFO.
 */
export async function setUpServers(
  page: Page,
  { servers = mockServers(), sites = mockSites() }: { servers?: ServerRowsAnswer | Handler; sites?: SiteStatsList | Handler } = {}
): Promise<{ reads: () => number }> {
  let reads = 0;
  await setUpServerScan(page, { sites });
  await page.route("**/api/day1/server-scan/servers", (route) => {
    reads += 1;
    return typeof servers === "function" ? servers(route) : json(route, servers);
  });
  return { reads: () => reads };
}

/** A maintenance change the page sent: its method, server id and body. */
export interface MaintenanceCall {
  method: string;
  id: string;
  body: unknown;
}

/**
 * day1's maintenance routes (§8.3) over `answer`'s rows: a PUT puts the server
 * into maintenance by `api-token-admin` (as server-scan records a token), a
 * DELETE ends it, and the next read of the rows shows it. `fail` answers
 * every change with a problem instead.
 */
export async function mockMaintenance(page: Page, answer: ServerRowsAnswer, fail?: Handler): Promise<MaintenanceCall[]> {
  const calls: MaintenanceCall[] = [];
  await page.route("**/api/day1/server-scan/servers/*/maintenance", (route) => {
    const request = route.request();
    const id = decodeURIComponent(new URL(request.url()).pathname.split("/").at(-2) ?? "");
    calls.push({ method: request.method(), id, body: request.postData() ? JSON.parse(request.postData() ?? "null") : null });
    if (fail) return fail(route);
    const at = answer.items.findIndex((row) => row.id === id);
    const start = request.method() === "PUT" ? (JSON.parse(request.postData() ?? "{}") as { reason: string | null }) : null;
    const maintenance = start
      ? { enabled: true, reason: start.reason, created_by: "api-token-admin" }
      : { enabled: false, reason: null, created_by: null };
    answer.items[at] = { ...answer.items[at], maintenance };
    return json(route, { id, name: answer.items[at].name, maintenance });
  });
  return calls;
}
