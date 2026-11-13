/**
 * Server Scan area mocks (docs/notes/2026-11-13-server-scan-area-api.md),
 * typed so a shape change fails `tsc`. A made-up fleet in server-scan's own
 * `GET /api/v1/sites` shape, summed the way server-scan sums it: two sites
 * with servers, a configured site with none, and two servers whose names
 * carry no site (Unassigned).
 */

import type { Page, Route } from "@playwright/test";
import { fulfillProblem, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "./api-handlers";
import type { Breakdown, FleetSummary, SiteStats, SiteStatsList } from "../../types/server-scan";

const VENDORS = ["dell", "cisco", "hp", "standalone", "kubevirt"] as const;
const SEVERITIES = ["UNKNOWN", "HEALTHY", "WARNING", "MAJOR", "CRITICAL"] as const;

type Counts = { vendors?: Partial<Record<(typeof VENDORS)[number], number>> } & Partial<Record<(typeof SEVERITIES)[number], number>> & {
  maintenance?: number;
};

/** A breakdown from its counts: the total is the sum of the severities. */
function breakdown({ vendors = {}, maintenance = 0, ...health }: Counts = {}): Breakdown {
  const by_health = Object.fromEntries(SEVERITIES.map((s) => [s, health[s] ?? 0]));
  return {
    total: Object.values(by_health).reduce((a, b) => a + b, 0),
    by_vendor: VENDORS.map((vendor) => ({ vendor, count: vendors[vendor] ?? 0 })),
    by_health,
    in_maintenance: maintenance,
  };
}

function add(a: Breakdown, b: Breakdown): Breakdown {
  return {
    total: a.total + b.total,
    by_vendor: a.by_vendor.map((v, i) => ({ vendor: v.vendor, count: v.count + (b.by_vendor[i]?.count ?? 0) })),
    by_health: Object.fromEntries(SEVERITIES.map((s) => [s, (a.by_health[s] ?? 0) + (b.by_health[s] ?? 0)])),
    in_maintenance: a.in_maintenance + b.in_maintenance,
  };
}

const sum = (parts: Breakdown[]) => parts.reduce(add, breakdown());

interface Slices {
  hosted?: Counts;
  mce?: Counts;
  upi?: Counts;
  unclassified?: Counts;
  /** How many of the site's servers are in no cluster; the rest are installed. */
  available?: Counts;
  inventory?: Counts;
}

/** A site (or the fleet) whose installation types add up to its total, as server-scan's are. */
function summary({ hosted, mce, upi, unclassified, available, inventory }: Slices): FleetSummary {
  const types = { HOSTED_CLUSTER: breakdown(hosted), MCE: breakdown(mce), UPI: breakdown(upi), UNCLASSIFIED: breakdown(unclassified) };
  const all = sum(Object.values(types));
  const free = breakdown(available);
  const agents = breakdown(inventory);
  const installed = { ...all, total: all.total - free.total - agents.total };
  return {
    ...all,
    by_installation_type: types,
    by_openshift_state: { AVAILABLE: free, INSTALLED: installed, INSTALLED_TO_INVENTORY: agents },
  };
}

const site = (site_id: string, name: string, slices: Slices): SiteStats => ({ site_id, name, ...summary(slices) });

const SITES: SiteStats[] = [
  site("site1", "Site 1", {
    hosted: { HEALTHY: 20, WARNING: 1, CRITICAL: 2, vendors: { dell: 15, hp: 8 }, maintenance: 1 },
    mce: { HEALTHY: 3, vendors: { dell: 3 } },
    upi: { HEALTHY: 5, MAJOR: 1, vendors: { cisco: 6 } },
    available: { HEALTHY: 4 },
    inventory: { HEALTHY: 6 },
  }),
  site("site2", "Site 2", {
    hosted: { HEALTHY: 4, vendors: { dell: 4 } },
    available: { HEALTHY: 1 },
  }),
  site("site3", "Site 3", {}),
  site("unassigned", "Unassigned", { unclassified: { UNKNOWN: 2, vendors: { standalone: 2 } }, available: { UNKNOWN: 2 } }),
];

/** The fleet, summed from the sites as server-scan sums it. */
function fleetOf(items: SiteStats[]): FleetSummary {
  const slice = <K extends string>(key: K, pick: (s: SiteStats) => Partial<Record<K, Breakdown>>) =>
    sum(items.map((s) => pick(s)[key] ?? breakdown()));
  const types = ["HOSTED_CLUSTER", "MCE", "UPI", "UNCLASSIFIED"] as const;
  const states = ["AVAILABLE", "INSTALLED", "INSTALLED_TO_INVENTORY"] as const;
  return {
    ...sum(items),
    by_installation_type: Object.fromEntries(types.map((t) => [t, slice(t, (s) => s.by_installation_type)])),
    by_openshift_state: Object.fromEntries(states.map((t) => [t, slice(t, (s) => s.by_openshift_state)])),
  };
}

export function mockSites(items: SiteStats[] = SITES): SiteStatsList {
  return { items, fleet: fleetOf(items) };
}

/** A fleet server-scan has not collected yet: every configured site at 0. */
export const NO_SERVERS = mockSites([site("site1", "Site 1", {}), site("site2", "Site 2", {}), site("unassigned", "Unassigned", {})]);

type Handler = (route: Route) => Promise<void> | void;

/** day1's answers when the page cannot show the sites. */
export const forbidden: Handler = (route) => fulfillProblem(route, 403, "FORBIDDEN", "This needs the admin role.");
export const off: Handler = (route) =>
  fulfillProblem(route, 501, "FEATURE_DISABLED", "Server Scan is not set up in this deployment: SERVER_SCAN_URL is empty.");
export const failing: Handler = (route) =>
  fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "server-scan unreachable listing sites: ConnectError");

/**
 * Sign in (as a viewer if asked), mock the dashboard's reads and day1's Server
 * Scan routes. Returns how many times the sites were read. Register a test's
 * own routes after this: mocks match LIFO.
 */
export async function setUpServerScan(
  page: Page,
  { sites = mockSites(), viewer = false }: { sites?: SiteStatsList | Handler; viewer?: boolean } = {}
): Promise<{ reads: () => number }> {
  let reads = 0;
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/server-scan/sites", (route) => {
    reads += 1;
    return typeof sites === "function" ? sites(route) : json(route, sites);
  });
  return { reads: () => reads };
}
