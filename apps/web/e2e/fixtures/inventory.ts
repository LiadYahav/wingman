/**
 * Inventory Management mocks (docs/notes/2026-11-13-inventory-management-api.md),
 * typed so a shape change fails `tsc`. Made up: two MCEs at site1, one with a
 * pool whose names match no InfraEnv, one MCE server-scan does not know; a
 * pool's servers with a free one, a locked one and one in maintenance; runs
 * of both origins, one failed.
 */

import type { Page, Route } from "@playwright/test";
import { fulfillProblem, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "./api-handlers";
import type {
  AddServersRequest,
  AddServersResult,
  Candidate,
  Candidates,
  InventoryOverview,
  InventoryRun,
  InventoryRuns,
} from "../../types/inventory";

export const SITE1_A = "ocp4-prod-mce-site1-a";
export const R650 = "dell-r650-site1-96c-768gb";
export const FREE = `ocp-${R650}-DLFAKE0811`;
export const LOCKED = `ocp-${R650}-DLFAKE0812`;
export const DONOR = `ocp-${R650}-DLFAKE0813`;
export const SITE1_B = "ocp4-prod-mce-site1-b";
/** The one InfraEnv site1-b's cluster files name: its own list could not be read. */
export const SITE1_B_POOL = "dell-r760-site1-64c-512gb-20tb";

export const OVERVIEW: InventoryOverview = {
  mces: [
    {
      site: "site1", mce: SITE1_A, known: true, servers: 16, in_clusters: 10, available: 6, usable: 5,
      pools: [
        { infra_env: R650, available: 2, usable: 1, drawable: 1,
          hardware: [{ vendor: "dell", model: "PowerEdge R650", available: 2, usable: 1 }] },
        { infra_env: "hp-gen12-site1-64c-512gb", available: 0, usable: 0, drawable: 0, hardware: [] },
        { infra_env: null, available: 4, usable: 4, drawable: null,
          hardware: [{ vendor: "dell", model: "PowerEdge R760", available: 4, usable: 4 }] },
      ],
      infra_envs: [R650, "hp-gen12-site1-64c-512gb"],
      infra_envs_error: null, infra_envs_from: "mce",
    },
    {
      site: "site1", mce: "ocp4-prod-mce-site1-b", known: true, servers: 4, in_clusters: 0, available: 4, usable: 4,
      pools: [{ infra_env: SITE1_B_POOL, available: 0, usable: 0, drawable: 2, hardware: [] }],
      infra_envs: [SITE1_B_POOL], infra_envs_from: "day1",
      infra_envs_error: "HubUnavailable: MCE 'ocp4-prod-mce-site1-b' hub API unreachable",
    },
    {
      site: "site1", mce: "ocp4-prod-mce-site1-c", known: false, servers: 0, in_clusters: 0, available: 0, usable: 0,
      pools: [], infra_envs: [], infra_envs_error: null, infra_envs_from: "mce",
    },
  ],
  add_servers: { available: true, detail: null },
  runs: { available: true, detail: null },
};

const candidate = (name: string, overrides: Partial<Candidate> = {}): Candidate => ({
  id: `srv_${name.slice(-4)}`, name, vendor: "dell", model: "PowerEdge R650", health: "HEALTHY",
  lock: null, offered: true, why_not: null, ...overrides,
});

const CANDIDATES: Candidates = {
  mce: SITE1_A,
  infra_env: R650,
  candidates: [
    candidate(FREE),
    candidate(LOCKED, {
      offered: false,
      why_not: "locked by add-server-to-mce until 2026-11-13T18:00:00+00:00",
      lock: { holder: "add-server-to-mce", mce: "ocp4-prod-mce-site1-b", infra_env: R650, expires_at: "2026-11-13T18:00:00+00:00" },
    }),
    candidate(DONOR, { offered: false, why_not: "in maintenance" }),
  ],
};

const run = (overrides: Partial<InventoryRun>): InventoryRun => ({
  workflow_id: `add-server-to-mce-${SITE1_A}_${R650}_1`, status: "running", started_at: "2026-11-13T12:00:00+00:00",
  closed_at: null, mce: SITE1_A, infra_env: R650, slot: 1, server_name: null, origin: "pool", phase: "acquiring-server",
  error: null, ...overrides,
});

const RUNS: InventoryRuns = {
  runs: [
    run({ phase: "waiting-for-agent", server_name: `ocp-${R650}-DLFAKE0701` }),
    run({
      workflow_id: `add-server-to-mce-ocp4-prod-mce-site1-b_${LOCKED.toLowerCase()}`, mce: "ocp4-prod-mce-site1-b",
      infra_env: null, slot: null, origin: "named", server_name: LOCKED, status: "failed", phase: "reserving-server",
      error: "ServerReservedError: held by another add-server-to-mce run",
    }),
  ],
};

export const STARTED: AddServersResult = {
  started: 2, already_running: 0, failed: 0,
  runs: [
    { workflow_id: `add-server-to-mce-${SITE1_A}_${R650}_2`, status: "started", server_name: null, slot: 2, error: null },
    { workflow_id: `add-server-to-mce-${SITE1_A}_${R650}_3`, status: "started", server_name: null, slot: 3, error: null },
  ],
};

type Handler = (route: Route) => Promise<void> | void;
type Answer<T> = T | Handler;
const answer = <T>(body: Answer<T>, status = 200) => (route: Route) =>
  typeof body === "function" ? (body as Handler)(route) : json(route, body, status);

/** What the page sent: every add-servers body and the path it went to, in order. */
export interface InventoryCalls {
  starts: AddServersRequest[];
  paths: string[];
}

/**
 * Sign in (as a viewer if asked), mock the dashboard's reads and day1's
 * Inventory routes. Register a test's own routes after this: mocks match LIFO.
 */
export async function setUpInventory(
  page: Page,
  {
    overview = OVERVIEW,
    runs = RUNS,
    candidates = CANDIDATES,
    start = STARTED,
    viewer = false,
  }: {
    overview?: Answer<InventoryOverview>;
    runs?: Answer<InventoryRuns>;
    candidates?: Answer<Candidates>;
    start?: Answer<AddServersResult>;
    viewer?: boolean;
  } = {}
): Promise<InventoryCalls> {
  const calls: InventoryCalls = { starts: [], paths: [] };
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/inventory", answer(overview));
  await page.route("**/api/day1/inventory/runs", answer(runs));
  await page.route("**/api/day1/inventory/mces/*/infra-envs/*/candidates", answer(candidates));
  await page.route("**/api/day1/inventory/mces/*/infra-envs/*/add-servers", (route) => {
    calls.starts.push(route.request().postDataJSON() as AddServersRequest);
    calls.paths.push(new URL(route.request().url()).pathname);
    return answer(start, 202)(route);
  });
  return calls;
}

/** day1's answers when the page cannot be shown. */
export const off: Handler = (route) =>
  fulfillProblem(route, 501, "FEATURE_DISABLED", "Inventory Management is not set up in this deployment: SERVER_SCAN_URL is empty.");
