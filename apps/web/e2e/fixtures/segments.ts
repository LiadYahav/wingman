/**
 * Segments area mocks (docs/notes/2026-11-13-segments-area-api.md), typed so
 * a shape change fails `tsc`. Made-up segments in day1's shape: every type, a
 * UPI segment shared by two clusters, Available rows (one that still carries
 * `allocated_at`), an old record without a status, `dhcp: false`, and a site
 * without segments.
 */

import type { Page, Route } from "@playwright/test";
import { fulfillProblem, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "./api-handlers";
import type { Segment, SegmentList, SegmentSites, SegmentStats } from "../../types/segments";

export const HERZI = "ocp4-prod-herzi-site1";
const MCE_SITE1 = "ocp4-prod-mce-site1-a";

function segment(overrides: Partial<Segment> & Pick<Segment, "segment">): Segment {
  return {
    site: "site1",
    vlan_id: 1400,
    epg_name: null,
    dhcp: true,
    status: "Allocated",
    type: "HC",
    cluster_name: null,
    allocated_at: "2026-10-02T09:12:40+00:00",
    holders: [],
    ...overrides,
  };
}

const day1 = (name: string, mce = MCE_SITE1, site = "site1") => ({ name, day1: { site, mce } });
const plain = (name: string) => ({ name, day1: null });

export const SEGMENTS: Segment[] = [
  segment({
    segment: "10.20.42.0/24", vlan_id: 1408, epg_name: "EPG_site1_HC_1408",
    cluster_name: "ocp4-prep-eyal-site1", holders: [day1("ocp4-prep-eyal-site1", "ocp4-prep-mce-site1-a")],
  }),
  segment({
    segment: "10.20.44.0/24", vlan_id: 1418, epg_name: "EPG_site1_HC_1418",
    cluster_name: HERZI, holders: [day1(HERZI)],
  }),
  segment({
    segment: "10.20.48.0/24", vlan_id: 1414, epg_name: "EPG_site1_HC_1414",
    status: "Available", type: null, allocated_at: null,
  }),
  segment({
    segment: "10.20.60.0/24", vlan_id: 1460, epg_name: "EPG_site1_UPI_1460", dhcp: false, type: "UPI",
    cluster_name: ["ocp4-upi-a", "ocp4-upi-b"], holders: [plain("ocp4-upi-a"), plain("ocp4-upi-b")],
  }),
  segment({
    segment: "10.20.11.0/24", vlan_id: 1011, epg_name: "EPG_site1_INVENTORY_1011", type: "INVENTORY",
    cluster_name: MCE_SITE1, holders: [plain(MCE_SITE1)],
  }),
  segment({
    segment: "10.20.50.0/24", site: "site2", vlan_id: 2450, epg_name: "EPG_site2_HC_2450",
    cluster_name: "ocp4-prep-ghost-site2", holders: [plain("ocp4-prep-ghost-site2")],
  }),
  segment({
    segment: "10.20.52.0/24", site: "site2", vlan_id: 2452, epg_name: "EPG_site2_HC_2452",
    status: "Available", type: null, allocated_at: "2026-09-30T07:00:00+00:00",
  }),
  segment({
    segment: "10.20.53.0/24", site: "site2", vlan_id: 2453, epg_name: null, dhcp: null,
    status: null, type: null, allocated_at: null,
  }),
];

export const SITES: SegmentSites = { sites: ["site1", "site2", "site3"] };

const counts = (pairs: [string, number][]) => pairs.map(([type, allocated]) => ({ type, allocated }));

export const STATS: SegmentStats = {
  sites: [
    { site: "site1", total_segments: 5, allocated: 4, by_type: counts([["HC", 2], ["MCE", 0], ["INVENTORY", 1], ["PXE", 0], ["UPI", 1], ["HUB", 0]]) },
    { site: "site2", total_segments: 3, allocated: 1, by_type: counts([["HC", 1], ["MCE", 0], ["INVENTORY", 0], ["PXE", 0], ["UPI", 0], ["HUB", 0]]) },
    { site: "site3", total_segments: 0, allocated: 0, by_type: counts([["HC", 0], ["MCE", 0], ["INVENTORY", 0], ["PXE", 0], ["UPI", 0], ["HUB", 0]]) },
  ],
};

export function mockSegmentList(overrides: Partial<SegmentList> = {}): SegmentList {
  return { segments: SEGMENTS, unreadable: [], clusters_error: null, fresh: false, ...overrides };
}

type Handler = (route: Route) => Promise<void> | void;
type Answer<T> = T | Handler;

const answer = <T>(body: Answer<T>) => (route: Route) =>
  typeof body === "function" ? (body as Handler)(route) : json(route, body);

/** The list reads day1 was asked for, in order: `fresh` is whether each asked for `fresh=true`. */
export interface SegmentReads {
  list: { fresh: boolean }[];
  stats: number;
}

/**
 * Sign in (as a viewer if asked), mock the dashboard's reads and day1's
 * Segments routes. Register a test's own routes after this: mocks match LIFO.
 */
export async function setUpSegments(
  page: Page,
  {
    list = mockSegmentList(),
    stats = STATS,
    sites = SITES,
    viewer = false,
  }: { list?: Answer<SegmentList>; stats?: Answer<SegmentStats>; sites?: Answer<SegmentSites>; viewer?: boolean } = {}
): Promise<SegmentReads> {
  const reads: SegmentReads = { list: [], stats: 0 };
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/segments/sites", answer(sites));
  await page.route("**/api/day1/segments/stats", (route) => {
    reads.stats += 1;
    return answer(stats)(route);
  });
  await page.route(/\/api\/day1\/segments(\?.*)?$/, (route) => {
    reads.list.push({ fresh: new URL(route.request().url()).searchParams.get("fresh") === "true" });
    return answer(list)(route);
  });
  return reads;
}

/** day1's answers when the area cannot be shown. */
export const forbidden: Handler = (route) => fulfillProblem(route, 403, "FORBIDDEN", "This needs the admin role.");
export const off: Handler = (route) =>
  fulfillProblem(route, 501, "FEATURE_DISABLED", "Segments is not set up in this deployment: SEGMENTS_MANAGER_URL is empty.");
