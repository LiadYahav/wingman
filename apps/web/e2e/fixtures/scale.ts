/**
 * The Scale specs' shared page (ADR-0062): the cluster Lark on its Nodes tab
 * with scaling on, its day1 NodePools, the scale routes mocked and what the
 * page sent, the MCE's NodePools as cards, and the steppers and the
 * confirmation by role. Used by cluster-scale.spec.ts and
 * cluster-scale-servers.spec.ts.
 */
import type { Page, Route } from "@playwright/test";
import type { ClusterDetail, ClusterDrift, ClusterNodes, ScaleOptions, ScaleRun, UpgradeRun } from "../../types";
import {
  fulfillProblem, go, injectAdminAuth, injectViewerAuth, json, mockClusterNodes, mockDashboardApis, mockNodePool, mockNodes,
} from "./api-handlers";

export const SITE = "site1";
export const MCE = "ocp4-prod-mce-site1-a";
export const LARK = "ocp4-prod-lark-site1";
export const FLAVOR = "agent-dell";
export const ZONE_A = "prod-lark-site1-dell-r660-site1-zone-a";
export const ZONE_B = "prod-lark-site1-dell-r660-site1-zone-b";
export const R760 = "prod-lark-site1-dell-r760-site1";
export const RUN_ID = `update-nodepool-${LARK}`;

export const DETAIL: ClusterDetail = {
  name: LARK, site: SITE, mce: MCE,
  yaml: `# specName: ${FLAVOR}\n# specVersion: 1.0.0\nmastertag: 4.18.22-x86_64\nnodepool: []\n`,
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${LARK}.yaml`,
  last_commit_id: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
  metadata: {
    spec_name: FLAVOR, spec_version: "1.0.0", created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { merkaz: "1" }, mastertag: "4.18.22-x86_64", platform: "agent", nodepools: [],
    network: { vlan_id: null, dhcp_network: null, segment: null }, cluster_name: null, automation_keys: [],
  },
  hosted_cluster: { cluster_name: "prod-lark-site1", name: "openshift-prod-lark-site1", namespace: "hcp-prod-lark-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "lark", sequence: null, problems: [] },
  mce_default_mastertag: "4.18.22-x86_64",
  problems: [],
  segments_manager: null,
};

/**
 * Two zones (zone-b removes its nodes by fewest-pods, zone-a has no policy), a locked NodePool whose file holds 3
 * (the flavor locks 2), and one that cannot be named.
 */
export const OPTIONS: ScaleOptions = {
  cluster: LARK, mce: MCE, flavor: FLAVOR,
  nodepools: [
    {
      index: 0, name: ZONE_A, infra_env: "dell-r660-site1-zone-a", replicas: 3, locked_by: null, locked_replicas: null, unnamed: null,
      scale_down_policy: null,
    },
    {
      index: 1, name: ZONE_B, infra_env: "dell-r660-site1-zone-b", replicas: 3, locked_by: null, locked_replicas: null, unnamed: null,
      scale_down_policy: "fewest-pods",
    },
    {
      index: 2, name: R760, infra_env: "dell-r760-site1", replicas: 3, locked_by: FLAVOR, locked_replicas: 2, unnamed: null,
      scale_down_policy: null,
    },
    {
      index: 3, name: null, infra_env: null, replicas: 1, locked_by: null, locked_replicas: null,
      unnamed: "nodepool[3] has neither name nor infraEnvName: its NodePool cannot be named", scale_down_policy: null,
    },
  ],
};

export const run = (overrides: Partial<ScaleRun> = {}): ScaleRun => ({
  workflow_id: RUN_ID, status: "running", phase: "pending", direction: null, child: null, result: null, error: null, error_type: null,
  ...overrides,
});

export const notDrifted: ClusterDrift = {
  cluster: LARK, site: SITE, mce: MCE, state: "in_sync", is_drifted: false, spec_name: FLAVOR, spec_version: "1.0.0",
  current_spec_version: "1.0.0", value_drift: [], addon_drift: [], version_differences: [], error: null, update: null,
};

/** What day1 answers on the scale routes, and what the page sent. */
export interface Scale {
  options: ScaleOptions;
  run: ScaleRun | null;
  starts: unknown[];
  runReads: number;
  /** The start's answer (default: 202 with a running run). */
  start?: (route: Route) => Promise<void>;
}

export const scaleOf = (overrides: Partial<Scale> = {}): Scale => ({ options: OPTIONS, run: null, starts: [], runReads: 0, ...overrides });

async function mockScale(page: Page, scale: Scale) {
  await page.route(`**/api/day1/clusters/${LARK}/scale?**`, async (route) => {
    if (route.request().method() === "GET") return json(route, scale.options);
    scale.starts.push(route.request().postDataJSON());
    if (scale.start) return scale.start(route);
    scale.run = run();
    return json(route, scale.run, 202);
  });
  await page.route(`**/api/day1/clusters/${LARK}/scale-run?**`, (route) => {
    scale.runReads += 1;
    return scale.run ? json(route, scale.run) : fulfillProblem(route, 404, "NOT_FOUND", `cluster '${LARK}' has no update-nodepool run`);
  });
}

/**
 * The cluster page with scaling on (unless `scale` is `null`: day1's 501, the
 * dashboard mocks' default), on its Nodes tab. Live status is off unless
 * `nodes` gives the MCE's NodePools, shown as cards, or answers the nodes
 * read itself (a route handler).
 */
export async function openNodes(
  page: Page,
  scale: Scale | null,
  { viewer = false, upgrade, drift = notDrifted, tab = "nodes", nodes }: {
    viewer?: boolean; upgrade?: UpgradeRun; drift?: ClusterDrift; tab?: string;
    nodes?: ClusterNodes | ((route: Route) => Promise<void> | void);
  } = {}
) {
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
  await page.route(`**/api/day1/clusters/${LARK}?**`, (r) => json(r, DETAIL));
  await page.route(`**/api/day1/clusters/${LARK}/drift?**`, (r) => json(r, drift));
  await page.route(`**/api/day2/clusters/${LARK}/history?**`, (r) => json(r, []));
  await page.route(`**/api/day2/clusters/${LARK}/addons?**`, (r) =>
    json(r, { cluster: LARK, mce: MCE, id: `hosted:${SITE}:prod:${MCE}:${LARK}`, kind: "hosted", site: SITE, env: "prod",
      ocp_version: "4.18.22", installed: [], excluded: [], warnings: [], argocd_note: "" })
  );
  await page.route("**/api/day2/addons", (r) => json(r, []));
  if (upgrade) await page.route(/\/api\/day1\/clusters\/[^/]+\/upgrade-run(\?.*)?$/, (r) => json(r, upgrade));
  if (scale) await mockScale(page, scale);
  if (nodes) await mockClusterNodes(page, LARK, nodes);
  await go(page, `/clusters/${LARK}?site=${SITE}&mce=${MCE}&tab=${tab}`);
}

/** A NodePool's stepper, by the name its group says. */
export const stepper = (page: Page, name: string) => page.getByRole("group", { name: `${name} replicas`, exact: true });
export const field = (page: Page, name: string) => stepper(page, name).getByRole("spinbutton");
export const more = (page: Page, name: string) => page.getByRole("button", { name: `One replica more for ${name}`, exact: true });
export const fewer = (page: Page, name: string) => page.getByRole("button", { name: `One replica fewer for ${name}`, exact: true });
export const card = (page: Page, name: string) => page.getByTestId(`node-pool-${name}`);
/** The confirmation every scale opens, and its Yes. */
export const confirmation = (page: Page) => page.getByTestId("scale-confirm");
export const yes = (page: Page) => page.getByTestId("scale-confirm-yes");
export const UNHEALTHY = "Unhealthy machines always go first.";

/** The MCE's NodePools as cards: the two zones, the locked r760, and one the day1 file does not name. */
export const CARDS = mockNodes({
  hosted_cluster: "prod-lark-site1",
  node_pools: [ZONE_A, ZONE_B, R760, "prod-lark-site1-extra"].map((name) => mockNodePool({ name, ready: 3, wanted: 3 })),
});
