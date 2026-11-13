import { Page, Route } from "@playwright/test";
import { mockAddons, mockSpecs } from "./addons";
import type {
  ApprovalRollout, ClusterNetworkRead, ClusterNodes, MRDetail, MachineConfigs, Mce, MergeRequestLink, NodePoolNodes, Placement,
  PlacementCandidate, PoolNode, Problem, ErrorCode, RolloutCluster, RolloutStatus, ServerRecord, WorkflowRun,
} from "../../types";

// ── MCE placement (docs/notes/2026-11-12-mce-placement-api.md) ────────────────

/** Every release the default placement's MCEs host, newest first. */
const PLACEMENT_VERSIONS = ["4.21.40", "4.20.44", "4.18.56", "4.18.22", "4.17.58", "4.16.27"];

/** What each MCE hosts, for `placementAnswer`: by default, one prod and one prep MCE per site, hosting everything. */
const PLACEMENT_OFFERED: Record<string, string[]> = Object.fromEntries(
  ["site1", "site2"].flatMap((site) =>
    ["prod", "prep"].map((env) => [`ocp4-${env}-mce-${site}-a`, PLACEMENT_VERSIONS])
  )
);

/** Newest first, by each number (`4.18.56` before `4.18.22` before `4.9.1`). */
function newestFirst(versions: Iterable<string>): string[] {
  const parts = (v: string) => v.split(".").map(Number);
  return [...new Set(versions)].sort((a, b) => {
    const [x, y] = [parts(a), parts(b)];
    for (let i = 0; i < Math.max(x.length, y.length); i++) if ((x[i] ?? 0) !== (y[i] ?? 0)) return (y[i] ?? 0) - (x[i] ?? 0);
    return 0;
  });
}

const LIVE_READS_OFF = "Not checked: live MCE reads are off (CLUSTER_STATUS_ENABLED=false).";

/**
 * `GET /api/day1/placement` as day1 answers it with live MCE reads off: the
 * candidates are the MCEs of `offered` named `ocp4-<env>-mce-<site>-<letter>`;
 * each passes the version check when it hosts the version; free pods, servers
 * and readability are not checked. The first that hosts the version, by name,
 * is the pick. Without a version there is no pick, only the versions.
 */
export function placementAnswer(query: URLSearchParams, offered: Record<string, string[]> = PLACEMENT_OFFERED): Placement {
  const site = query.get("site") ?? "";
  const env = query.get("env") ?? "";
  const version = query.get("version");
  const owner = query.get("owner");
  const names = Object.keys(offered)
    .filter((name) => name.startsWith(`ocp4-${env}-mce-${site}-`))
    .sort();
  const candidates: PlacementCandidate[] = names.map((mce) => {
    const hosts = offered[mce];
    const versionStatus = !version ? "unknown" : hosts.includes(version) ? "pass" : "fail";
    return {
      mce,
      eligible: versionStatus === "pass",
      picked: false,
      rank: null,
      behind_on: null,
      checks: [
        {
          check: "version",
          status: versionStatus,
          detail: !version
            ? "Choose an OpenShift version."
            : versionStatus === "pass"
            ? `Hosts OpenShift ${version}.`
            : hosts.length > 0
            ? `Does not host OpenShift ${version}; it hosts ${hosts.join(", ")}.`
            : `${mce} has no upgrade/mces/${mce}.yaml in the day1 repo, so it hosts no version.`,
        },
        { check: "free_pods", status: "not_checked", detail: LIVE_READS_OFF },
        { check: "servers", status: "not_checked", detail: LIVE_READS_OFF },
        { check: "readable", status: "not_checked", detail: LIVE_READS_OFF },
      ],
      node_types: [],
      versions: hosts,
      clusters: 0,
      open_creates: 0,
      owner_clusters: owner ? 0 : null,
      spare: null,
      spare_detail: null,
      pods: null,
    };
  });
  const eligible = candidates.filter((c) => c.eligible);
  eligible.forEach((c, i) => {
    c.rank = i + 1;
    c.picked = i === 0;
    c.behind_on = i === 0 ? null : "name";
  });
  const pick = eligible[0]?.mce ?? null;
  const problems = !version
    ? ["Choose an OpenShift version."]
    : candidates.length === 0
    ? [`${site} has no ${env} MCE (ocp4-${env}-mce-${site}-<letter>).`]
    : pick
    ? []
    : [`No ${env} MCE at ${site} passes every check.`];
  return {
    site,
    env,
    version,
    owner,
    flavor: query.get("flavor"),
    min_free_pods: 70,
    live_reads: false,
    needs: [],
    versions: newestFirst(candidates.flatMap((c) => c.versions)),
    pick,
    why: pick ? (eligible.length === 1 ? `${pick} is the only MCE that passes every check.` : `${pick} comes first by name.`) : null,
    problems,
    server_scan_error: "server-scan is not configured, so spare servers are unknown.",
    candidates: [...eligible, ...candidates.filter((c) => !c.eligible)],
  };
}

/**
 * Route `GET /api/day1/placement?...` to `placementAnswer(query, offered)`;
 * each request's query goes into `calls` when given. Registered after the
 * dashboard mocks, it wins (Playwright matches LIFO).
 */
export async function mockPlacement(
  page: Page,
  offered: Record<string, string[]> = PLACEMENT_OFFERED,
  calls?: URLSearchParams[]
) {
  await page.route("**/api/day1/placement**", (route: Route) => {
    const query = new URL(route.request().url()).searchParams;
    calls?.push(query);
    return json(route, placementAnswer(query, offered));
  });
}
import type { Team } from "../../types/day2";

// Shapes follow the services' Pydantic schemas (apps/day1-service/.../api/v1/schemas.py,
// apps/day2-service/.../api/v1/*schemas.py), typed so a shape change fails `tsc`.

/** The fixtures' teams, each with Wingman's account a Developer on its project. */
const WRITABLE_TEAMS: Team[] = ["networking", "observability", "platform", "security"].map((name, i) => ({
  name,
  project_id: i + 2,
  path_with_namespace: `sigs/${name}`,
  web_url: `https://gitlab.example.com/sigs/${name}`,
  writable: true,
  access_level: 30,
  access_role: "developer",
  read_only_reason: null,
}));

/** A Wingman MR as the services return it (`MRDetail`). */
export function mockMR(overrides: Partial<MRDetail> = {}): MRDetail {
  return {
    iid: 42,
    project_id: 7,
    title: "[Wingman/Day1] Create cluster ocp4-prod-test-site1",
    description: "Created via Wingman",
    author: { username: "qa-admin", name: "qa-admin", avatar_url: "" },
    state: "opened",
    created_at: "2026-11-07T10:00:00+00:00",
    updated_at: "2026-11-07T10:00:00+00:00",
    merged_at: null,
    web_url: "https://gitlab.example.com/gitops-day1/platform-config/-/merge_requests/42",
    source_branch: "wingman/create-cluster-ocp4-prod-test-site1",
    target_branch: "main",
    labels: ["wingman"],
    repo: "day1",
    has_conflicts: false,
    sha: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
    ...overrides,
  };
}

/** An RFC 9457 problem body (`application/problem+json`). */
function problemBody(
  status: number,
  code: ErrorCode,
  detail: string,
  details: Problem["details"] = {}
): Problem {
  return {
    type: `/problems/${code.toLowerCase().replace(/_/g, "-")}`,
    title: code.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()),
    status,
    detail,
    instance: "/api/test",
    code,
    request_id: "req_e2e0000000000001",
    details,
  };
}

/** Answer a route with a problem. */
export function fulfillProblem(
  route: Route,
  status: number,
  code: ErrorCode,
  detail: string,
  details: Problem["details"] = {}
) {
  return route.fulfill({
    status,
    contentType: "application/problem+json",
    body: JSON.stringify(problemBody(status, code, detail, details)),
  });
}

function mockMce(overrides: Partial<Mce> = {}): Mce {
  return {
    name: "ocp4-prod-mce-site1-a",
    site: "site1",
    env: "prod",
    letter: "a",
    follows_convention: true,
    naming_problems: [],
    default_mastertag: "4.16.27-x86_64",
    hub_version: "4.16.27-x86_64",
    cluster_count: 0,
    stray_files: [],
    problems: [],
    ...overrides,
  };
}

const mockMces: Mce[] = [
  mockMce(),
  mockMce({ name: "ocp4-prep-mce-site1-a", env: "prep", default_mastertag: "4.20.9-x86_64", hub_version: "4.20.9-x86_64" }),
  mockMce({ name: "ocp4-prod-mce-site2-a", site: "site2" }),
];

/**
 * `GET /api/day1/machine-configs` on the fixtures (the API note's §1): static
 * configs at the root and in `kubevirt/`, three hardware types that overlap
 * (`dell`, `dell-data`), and the team's three nodepool defaults.
 */
export const mockMachineConfigs: MachineConfigs = {
  network_config: "nm-conf",
  static_configs: [
    { name: "nic-ring-buffer", folder: "", path: "mc-files/nic-ring-buffer.bu" },
    { name: "worker-kubeletconfig-reserved", folder: "", path: "mc-files/worker-kubeletconfig-reserved" },
    { name: "workers-chrony-configuration", folder: "", path: "mc-files/workers-chrony-configuration.bu" },
    { name: "kubevirt-worker-tuning", folder: "kubevirt", path: "mc-files/kubevirt/kubevirt-worker-tuning.bu" },
  ],
  // No generic template here: a specs repo without nm-conf-template.bu behaves as before it (ADR-0027)
  hardware_types: [
    { name: "cisco", template: "mc-files/templates/nm-conf-template-cisco.bu", generic: false },
    { name: "dell", template: "mc-files/templates/nm-conf-template-dell.bu", generic: false },
    { name: "dell-data", template: "mc-files/templates/nm-conf-template-dell-data.bu", generic: false },
  ],
  nodepool_defaults: {
    path: "nodepool-defaults.yaml",
    found: true,
    configs: [{ name: "nm-conf" }, { name: "workers-chrony-configuration" }, { name: "nic-ring-buffer" }],
    error: null,
    problems: [],
  },
  problems: [],
};

/** The catalogue with the generic network template, `nm-conf-template.bu`: day1 lists it first. */
export const mockMachineConfigsWithGeneric: MachineConfigs = {
  ...mockMachineConfigs,
  hardware_types: [
    { name: "generic", template: "mc-files/templates/nm-conf-template.bu", generic: true },
    ...mockMachineConfigs.hardware_types,
  ],
};

/** Answer a route with a JSON body. */
export const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

// ── Cluster nodes by NodePool, and node uninstall (docs/notes/2026-11-11-cluster-nodes-api.md) ──

/**
 * server-scan's record of the server called `name` (§1): healthy, installed;
 * its serial is the name's last part, its id and url follow from it.
 */
export function mockServer(name = "ocp-dell-r660-site1-64c-512gb-DL0000123", overrides: Partial<ServerRecord> = {}): ServerRecord {
  const serial = name.split("-").pop() ?? name;
  const id = `srv_${serial.toLowerCase()}`;
  return {
    id,
    name,
    url: `https://server-scan.example/servers/${id}`,
    serial,
    vendor: "dell",
    model: "PowerEdge R660",
    site: "site1",
    mce: "ocp4-prod-mce-site1-a",
    state: "INSTALLED",
    health: "HEALTHY",
    maintenance: false,
    reachable: true,
    stale: false,
    contested: false,
    last_seen_at: "2026-11-11T08:00:03+00:00",
    ...overrides,
  };
}

/** A Machine of a NodePool (§1): ready, its Agent done, `server` behind it (by default the one of `mockServer()`). */
export function mockPoolNode(machine: string, overrides: Partial<PoolNode> = {}): PoolNode {
  const server = overrides.server === undefined ? mockServer() : overrides.server;
  return {
    machine,
    node_name: `worker-${machine.slice(-5)}`,
    state: "ready",
    current: false,
    activity: null,
    waiting_for: null,
    outdated: null,
    agent: { name: `agent-${machine.slice(-5)}`, state: "added-to-existing-cluster", stage: "Done" },
    server_name: server?.name ?? null,
    server,
    uninstall: null,
    ...overrides,
  };
}

/** A NodePool (§1): InPlace, three ready nodes, no update, no problems. */
export function mockNodePool(overrides: Partial<NodePoolNodes> = {}): NodePoolNodes {
  const name = overrides.name ?? "prod-lark-site1-dell-r660-site1";
  return {
    name,
    wanted: 3,
    autoscaling: null,
    ready: 3,
    version: "4.18.22",
    upgrade_type: "InPlace",
    agent_selector: "infraenvs.agent-install.openshift.io=dell-r660-site1",
    update: null,
    problems: [],
    free_agents: { matching: 4, free: 1 },
    nodes: ["b2c4d", "k8j3h", "m3n8v"].map((suffix, i) =>
      mockPoolNode(`${name}-${suffix}`, { server: mockServer(`ocp-dell-r660-site1-64c-512gb-DL000012${i + 1}`) })
    ),
    ...overrides,
  };
}

/** `GET /api/day1/clusters/{name}/nodes` (§1): one quiet NodePool, nothing unassigned, everything readable. */
export function mockNodes(overrides: Partial<ClusterNodes> = {}): ClusterNodes {
  return {
    hosted_cluster: "ocp4-prod-lark-site1",
    node_pools: [mockNodePool()],
    unassigned: [],
    uninstall: { available: true, detail: null },
    server_scan_error: null,
    runs_error: null,
    ...overrides,
  };
}

/** The board's servers, by role. */
export const BOARD = {
  rebooting: mockServer("ocp-dell-r660-site1-64c-512gb-DL0000123"),
  readyA: mockServer("ocp-dell-r660-site1-64c-512gb-DL0000121"),
  readyB: mockServer("ocp-dell-r660-site1-64c-512gb-DL0000122", { health: "WARNING", maintenance: true }),
  r760A: mockServer("ocp-dell-r760-site1-96c-768gb-DL0000140", { model: "PowerEdge R760" }),
  r760B: mockServer("ocp-dell-r760-site1-96c-768gb-DL0000141", { model: "PowerEdge R760" }),
  draining: mockServer("ocp-cisco-c240-site1-96c-768gb-CS0000077", { vendor: "cisco", model: "UCS C240 M7" }),
  installing: mockServer("ocp-cisco-c240-site1-96c-768gb-CS0000079", { vendor: "cisco", model: "UCS C240 M7" }),
  outdated: mockServer("ocp-cisco-c240-site1-96c-768gb-CS0000078", { vendor: "cisco", model: "UCS C240 M7" }),
  left: mockServer("ocp-dell-r660-site1-64c-512gb-DL0000099", { stale: true }),
} as const;

/**
 * A cluster mid-change, every case of the API note's §1 in one read:
 * - an InPlace pool updating its version, one node of three updated, the
 *   node it reboots `current`;
 * - an InPlace pool short of servers: a Machine `waiting` for a free Agent
 *   (none of the 4 matching is free), a `missing` node, three problems;
 * - a Replace pool rolling out a config: the old Machine `deleting` (draining)
 *   and its replacement `installing`, both `current`, and an `outdated` one
 *   still ready;
 * - a server server-scan still places here that no Machine has, its
 *   uninstall completed.
 */
export function mockNodesBoard(overrides: Partial<ClusterNodes> = {}): ClusterNodes {
  const r660 = "prod-lark-site1-dell-r660-site1";
  const r760 = "prod-lark-site1-dell-r760-site1";
  const c240 = "prod-lark-site1-cisco-c240-site1";
  return mockNodes({
    node_pools: [
      mockNodePool({
        name: c240,
        wanted: 2,
        ready: 1,
        version: "4.18.20",
        upgrade_type: "Replace",
        agent_selector: "infraenvs.agent-install.openshift.io=cisco-c240-site1",
        update: { kind: "config", message: "Updating config in progress. Target config: 9a7e1d", progress: null, failed: false },
        free_agents: { matching: 3, free: 1 },
        nodes: [
          mockPoolNode(`${c240}-7d9fq`, {
            state: "deleting", current: true, activity: "Draining", outdated: true, server: BOARD.draining,
          }),
          mockPoolNode(`${c240}-h2l6s`, {
            state: "installing", current: true, activity: "Installing: Writing image to disk", outdated: false, node_name: null,
            agent: { name: "agent-h2l6s", state: "installing-in-progress", stage: "Writing image to disk" }, server: BOARD.installing,
          }),
          mockPoolNode(`${c240}-p4r8x`, { outdated: true, server: BOARD.outdated }),
        ],
      }),
      mockNodePool({
        name: r660,
        ready: 2,
        update: {
          kind: "version",
          message: "Nodepool update in progress. Target Config version: 6c1f2b. Total Nodes: 3. Upgraded: 1",
          progress: { total: 3, updated: 1 },
          failed: false,
        },
        problems: [`AllNodesHealthy: Machine ${r660}-x7k2p: NodeConditionsFailed`],
        nodes: [
          mockPoolNode(`${r660}-x7k2p`, {
            state: "not_ready", current: true, node_name: "worker-2",
            activity: "Rebooting for the update (Node condition Ready is Unknown)", server: BOARD.rebooting,
          }),
          mockPoolNode(`${r660}-b2c4d`, { server: BOARD.readyA }),
          mockPoolNode(`${r660}-k8j3h`, { server: BOARD.readyB }),
        ],
      }),
      mockNodePool({
        name: r760,
        wanted: 4,
        ready: 2,
        agent_selector: "infraenvs.agent-install.openshift.io=dell-r760-site1",
        problems: [
          "Ready: WaitingForAvailableMachines: Minimum availability requires 4 replicas, current 2 available",
          "AllMachinesReady: WaitingForInfrastructure: 1 of 3 Machines is not ready",
          "AllNodesHealthy: NodeProvisioning",
        ],
        free_agents: { matching: 4, free: 0 },
        nodes: [
          mockPoolNode(`${r760}-q9w4m`, {
            state: "waiting", node_name: null, agent: null, server_name: null, server: null,
            waiting_for: "No free Agent matches this NodePool: 4 Agents match its selector, none is free (3 bound, 1 not approved)",
          }),
          { ...mockPoolNode("", { state: "missing", node_name: null, agent: null, server: null }), machine: null },
          mockPoolNode(`${r760}-c5v7b`, { server: BOARD.r760A }),
          mockPoolNode(`${r760}-g1f9e`, { server: BOARD.r760B }),
        ],
      }),
    ],
    unassigned: [
      {
        ...BOARD.left,
        uninstall: { workflow_id: `uninstall-server-from-hc-${BOARD.left.name.toLowerCase()}`, status: "completed", phase: null, error: null },
      },
    ],
    ...overrides,
  });
}

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Route `GET /api/day1/clusters/<cluster>/nodes?...` to `answer`: a body, or
 * a handler (called on each read, so a test can count reads or change what
 * the next one returns).
 */
export async function mockClusterNodes(
  page: Page,
  cluster: string,
  answer: ClusterNodes | ((route: Route) => Promise<void> | void)
) {
  await page.route(new RegExp(`/api/day1/clusters/${escapeRegExp(cluster)}/nodes(\\?.*)?$`), (route: Route) =>
    typeof answer === "function" ? answer(route) : json(route, answer)
  );
}

/**
 * Route `POST /api/day1/clusters/<cluster>/nodes/<server_id>/uninstall?...`:
 * `answer` gets the route and the node's id (by default a 202 with a running
 * run). Every request is kept in `posts`, with its body and query.
 */
export async function mockUninstallNode(
  page: Page,
  cluster: string,
  answer?: (route: Route, serverId: string) => Promise<void> | void
) {
  const posts: { serverId: string; body: unknown; search: URLSearchParams }[] = [];
  const pattern = new RegExp(`/api/day1/clusters/${escapeRegExp(cluster)}/nodes/([^/?]+)/uninstall(\\?.*)?$`);
  await page.route(pattern, async (route: Route) => {
    const url = new URL(route.request().url());
    const serverId = decodeURIComponent(url.pathname.match(pattern)?.[1] ?? "");
    posts.push({ serverId, body: route.request().postDataJSON(), search: url.searchParams });
    if (answer) return answer(route, serverId);
    const run: WorkflowRun = { workflow_id: `uninstall-server-from-hc-${serverId}`, status: "running", phase: null, error: null };
    return json(route, run, 202);
  });
  return { posts };
}

/**
 * A response held until `release()`, so the page's loading state stays on
 * screen meanwhile: `answer(body)` is a route handler that answers once
 * released; `released` is the promise, for a handler of one's own.
 */
export function held() {
  let release: () => void = () => {};
  const released = new Promise<void>((resolve) => (release = resolve));
  return {
    released,
    release: () => release(),
    answer: (body: unknown) => async (route: Route) => {
      await released;
      await json(route, body);
    },
  };
}

/** Land on "/" first so the persisted session hydrates (see injectAdminAuth), then open `path`. */
export async function go(page: Page, path: string) {
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
  if (path !== "/") {
    await page.goto(path);
    await page.waitForLoadState("domcontentloaded");
  }
}

/**
 * Inject a fake authenticated admin user into localStorage/cookie so the app
 * doesn't redirect to /login.  Must be called before page.goto().
 *
 * IMPORTANT: After calling this, you must navigate to "/" first to establish
 * auth state, then navigate to your target page (`go()` does both).  Direct
 * navigation to a sub-route may fail because Zustand's persist hydration is
 * asynchronous.
 *
 * Usage:
 *   await injectAdminAuth(page);
 *   // ... register your route mocks ...
 *   await go(page, "/approvals");   // "/" first, then the target
 */
export async function injectAdminAuth(page: Page, username = "test-admin") {
  // Route the auth config check so it doesn't 401
  await page.route("**/api/auth/config", (route: Route) =>
    json(route, { authorize_url: "/login", dev_auth_enabled: false })
  );

  // Pre-seed localStorage with a persisted auth state that Zustand will hydrate
  await page.addInitScript((name: string) => {
    // Clear any stale query cache that could interfere with fresh test state
    localStorage.removeItem("wingman-query-cache");

    const authState = {
      state: {
        user: {
          username: name,
          groups: ["wingman-admins"],
          uid: name,
          full_name: "Test Admin",
          role: "admin",
        },
        isAuthenticated: true,
      },
      version: 0,
    };
    localStorage.setItem("wingman-auth", JSON.stringify(authState));

    // Set a fake token cookie so the API client includes it in requests
    document.cookie = "wingman-token=fake-e2e-token; path=/; SameSite=Strict";
  }, username);
}

/**
 * Sign in as the viewer Vera instead. Call it after `injectAdminAuth`: init
 * scripts run in order, so this user replaces the admin it seeds.
 */
export async function injectViewerAuth(page: Page) {
  await page.addInitScript(() => {
    const state = { state: { user: { username: "vera", groups: ["wingman-viewers"], uid: "vera", full_name: "Vera Viewer", role: "viewer" }, isAuthenticated: true }, version: 0 };
    localStorage.setItem("wingman-auth", JSON.stringify(state));
  });
}

/**
 * Mock every API the dashboard calls so that navigating to "/" doesn't cause
 * 401s that would redirect to login during auth establishment.
 */
export async function mockDashboardApis(page: Page) {
  await page.route("**/api/day1/clusters", (route: Route) => json(route, []));
  await page.route("**/api/day1/clusters/drift-summary", (route: Route) => json(route, []));
  await page.route("**/api/day1/clusters/bulk-status", (route: Route) => json(route, {}));
  // Not built yet (ADR-0033): the panel says "Not available yet" until it is.
  await page.route("**/api/day1/clusters/*/delete-workflow**", (route: Route) =>
    fulfillProblem(route, 501, "FEATURE_DISABLED", "The delete-cluster workflow is not available yet.")
  );
  // The MCE is not read unless a test sets the nodes up (mockClusterNodes): the Nodes tab says "off", quietly
  await page.route("**/api/day1/clusters/*/nodes**", (route: Route) =>
    fulfillProblem(route, 501, "FEATURE_DISABLED", "Live cluster status is disabled in this deployment (CLUSTER_STATUS_ENABLED=false).")
  );
  // No name to suggest unless a test says otherwise (ADR-0040): the create form's name stays as typed
  await page.route("**/api/day1/clusters/name-suggestion**", (route: Route) =>
    json(route, { name: null, env: null, short_name: "", sequence: null, problems: [] })
  );
  // Wingman picks the MCE (ADR-0050): ocp4-<env>-mce-<site>-a for every site and env, live reads off
  await mockPlacement(page);
  // A create opens Wingman's merge request unless a test turns the provision-cluster workflow on (ADR-0042)
  await page.route("**/api/day1/clusters/provisioner", (route: Route) => json(route, { mode: "merge-request" }));
  // segments-manager is off unless a test says otherwise (mockClusterNetwork): the card shows the file, EPG "—"
  await page.route("**/api/day1/clusters/*/network**", (route: Route) =>
    json(route, { vlan_id: null, segment: null, epg: null, ledger: null, problems: [], ledger_error: null })
  );
  await page.route("**/api/day1/specs", (route: Route) => json(route, []));
  await page.route("**/api/day1/machine-configs", (route: Route) => json(route, mockMachineConfigs));
  await page.route("**/api/day1/approvals", (route: Route) => json(route, []));
  await page.route("**/api/day2/approvals", (route: Route) => json(route, []));
  // Every team of the fixtures is writable unless a test sets its own list (mockAuthoring). The web
  // fails closed (ADR-0053): a team the list does not have is read-only.
  await page.route("**/api/day2/teams", (route: Route) => json(route, WRITABLE_TEAMS));
  await page.route("**/api/day2/fleet-defaults**", (route: Route) => json(route, []));
  // A flavor's rollout follows no cluster unless a test says otherwise (mockRollout, ADR-0044)
  await page.route("**/api/day1/specs/*/rollout", (route: Route) => {
    const spec = decodeURIComponent(new URL(route.request().url()).pathname.split("/").at(-2) ?? "");
    return json(route, mockRollout({ spec_name: spec }), route.request().method() === "POST" ? 202 : 200);
  });
  // A flavor MR's merge opens nothing unless a test says otherwise (mockApprovalRollout)
  await page.route("**/api/day1/approvals/*/rollout**", (route: Route) => json(route, mockApprovalRollout()));
}

// ── A flavor's rollout, one MR per cluster (docs/notes/2026-11-12-flavor-rollout-api.md §2) ──

const NO_COUNTS: RolloutStatus["counts"] = {
  on_version: 0, merge_request_open: 0, pending: 0, needs_decision: 0, declined: 0, failed: 0, unknown: 0,
};

/** `GET /api/day1/specs/{name}/rollout`: `counts` are counted from `clusters` unless given. */
export function mockRollout(overrides: Partial<RolloutStatus> = {}): RolloutStatus {
  const clusters = overrides.clusters ?? [];
  const counts = { ...NO_COUNTS };
  for (const c of clusters) counts[c.state] += 1;
  return {
    spec_name: "agent-baseline",
    version: "1.0.0",
    running: false,
    last_run: null,
    counts,
    clusters,
    ...overrides,
  };
}

/** One cluster of a rollout, on site1's MCE, on v1.0.0, with an MR for `merge_request_open` and `declined`. */
export function mockRolloutCluster(name: string, state: RolloutCluster["state"], overrides: Partial<RolloutCluster> = {}): RolloutCluster {
  const mce = "ocp4-prod-mce-site1-a";
  return {
    name,
    site: "site1",
    mce,
    path: `sites/site1/mces/${mce}/hostedClusters/${name}.yaml`,
    from_version: "1.0.0",
    state,
    merge_request: null,
    reasons: [],
    ...overrides,
  };
}

/** A day1 MR as a rollout or an update links it. */
export function mockMergeRequestLink(iid: number, title: string): MergeRequestLink {
  return { repo: "day1", iid, title, web_url: `https://gitlab.example.com/gitops-day1/platform-config/-/merge_requests/${iid}` };
}

/** `GET /api/day1/approvals/{iid}/rollout?repo=specs`: by default an MR that gives no flavor a new version. */
export function mockApprovalRollout(overrides: Partial<ApprovalRollout> = {}): ApprovalRollout {
  return {
    applies: false,
    reason: "the merge request gives no existing flavor a new version",
    spec_name: "",
    version: null,
    current_version: null,
    following: 0,
    opens: 0,
    already_on_version: 0,
    needs_decision: [],
    rolls_nodes: [],
    removes_configs: [],
    adds_addons: [],
    ...overrides,
  };
}

async function mockDay2Api(page: Page) {
  await page.route("**/api/day2/addons", (route: Route) => json(route, mockAddons));

  await page.route("**/api/day2/addons/*/**", async (route: Route) => {
    const url = route.request().url();
    const match = url.match(/\/api\/day2\/addons\/([^/]+)\/([^/?]+)(\/values)?/);
    if (match) {
      const [, team, name, values] = match;
      const addon = mockAddons.find((a) => a.team === team && a.name === name);
      if (values) {
        // Helm chart defaults; the configure dialog deep-merges the Sig
        // values (default_values) on top, so an empty chart means "Sig values only".
        await json(route, {});
        return;
      }
      if (addon) {
        await json(route, addon);
        return;
      }
    }
    await fulfillProblem(route, 404, "NOT_FOUND", "no such addon");
  });
}

async function mockDay1Api(page: Page) {
  await page.route("**/api/day1/specs", async (route: Route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      await json(route, mockMR({ repo: "specs", iid: 5, title: `[Wingman/Specs] Create spec ${body?.metadata?.name}` }), 201);
    } else {
      await json(route, mockSpecs);
    }
  });

  await page.route("**/api/day1/specs/*", async (route: Route) => {
    const method = route.request().method();
    const name = new URL(route.request().url()).pathname.split("/").pop();
    const spec = mockSpecs.find((s) => s.metadata.name === name);

    if (method === "GET" && spec) {
      await json(route, spec);
    } else if ((method === "PUT" || method === "DELETE") && spec) {
      await json(route, mockMR({ repo: "specs", iid: 6, title: `[Wingman/Specs] Update spec ${name}` }));
    } else {
      await fulfillProblem(route, 404, "NOT_FOUND", `spec '${name}' does not exist`);
    }
  });

  // Registered after the "specs/*" catch-all so these win (Playwright matches LIFO)
  await page.route("**/api/day1/specs/template", (route: Route) =>
    json(route, "# cluster-template.j2\nmastertag: {{ openshift_release_version }}")
  );

  await page.route("**/api/day1/specs/template/schema**", (route: Route) =>
    json(route, [
      { name: "nodepools_count", type: "integer", required: true, default: 1 },
      { name: "cluster_name", type: "string", required: true },
    ])
  );

  // GET /mces[?site=]: every MCE, or one site's
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (route: Route) => {
    const site = new URL(route.request().url()).searchParams.get("site");
    return json(route, site ? mockMces.filter((m) => m.site === site) : mockMces);
  });

  await page.route("**/api/day1/sites", (route: Route) => json(route, ["site1", "site2"]));

  await page.route("**/api/day1/machine-configs", (route: Route) => json(route, mockMachineConfigs));
}

export async function mockAllApis(page: Page) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await mockDay1Api(page);
  await mockDay2Api(page);
}

/**
 * Route `GET /api/day1/clusters/<cluster>/network?...` to `body`
 * (docs/notes/2026-11-11-cluster-network-api.md §2).
 */
export async function mockClusterNetwork(page: Page, cluster: string, body: ClusterNetworkRead) {
  await page.route(new RegExp(`/api/day1/clusters/${escapeRegExp(cluster)}/network(\\?.*)?$`), (route: Route) => json(route, body));
}
