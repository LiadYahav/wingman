import type { Page, Route } from "@playwright/test";
import { mockAddons } from "./addons";
import type {
  BulkBody,
  BulkResult,
  CatalogEntry,
  ChangeResult,
  Destination,
  DestinationCharts,
  Finding,
  InstalledChart,
  LeafApp,
  MergePreviewBody,
  ValueLayer,
  ValuesPreview,
} from "../../types/day2";

/**
 * A day2 world shaped like the service's responses (types/day2.ts, from the
 * Pydantic schemas): one hosted cluster with its own charts, a fleet default
 * and an emergency pin; an MCE, the hub, a UPI cluster; a name two
 * destinations share; and lint findings.
 */

export const HOSTED_ID = "hosted:site1:prod:mce-a:ocp4-prod-hawk-site1";
export const HOSTED_NAME = "ocp4-prod-hawk-site1";
export const MCE_ID = "mce:site1:prod:mce-a";
export const TWIN_IDS = ["hosted:site1:prod:mce-a:twin", "hosted:site2:prep:mce-b:twin"];

const HOSTED_FOLDER = `sites/site1/prod/mces/mce-a/${HOSTED_NAME}`;

export function finding(overrides: Partial<Finding> & Pick<Finding, "rule" | "message">): Finding {
  return { severity: "warning", team: "", path: "", cluster: "", chart: "", ...overrides };
}

const kyverno: CatalogEntry = {
  team: "security",
  name: "kyverno",
  available_versions: [],
  current_version: "main",
  default_values: {},
  argocd_metadata: { projectNamespace: "kyverno", repourl: "", targetRevision: "main", syncPolicy: {}, path: "." },
  dependencies: [],
  ocp_version_pins: [],
  fleet_defaults: [],
  chart_project: null,
  warnings: [
    finding({
      rule: "repourl-miscased",
      message: "operators/kyverno/kyverno.yaml sets `repoUrl`; the platform reads only lowercase `repourl`",
      team: "security",
      path: "operators/kyverno/kyverno.yaml",
      chart: "kyverno",
    }),
  ],
};

/** The catalog of the cluster scenario: the shared mock catalog plus a chart with the miscased repoUrl. */
export const day2Catalog: CatalogEntry[] = [...mockAddons, kyverno];

function catalogEntry(team: string, name: string): CatalogEntry {
  const entry = day2Catalog.find((e) => e.team === team && e.name === name);
  if (!entry) throw new Error(`no catalog entry ${team}/${name}`);
  return entry;
}

function leaf(team: string, chart: string, revision: string, autoSync = false): LeafApp {
  return {
    app_name: `${team}-${HOSTED_NAME}-${chart}-deploy`,
    argo: "mce-a",
    namespace: `gitops-${team}`,
    repo_url: `https://gitlab.example.com/helm-charts/${chart}.git`,
    target_revision: revision,
    path: ".",
    release_name: chart,
    destination: HOSTED_NAME,
    destination_namespace: chart,
    sync_policy: autoSync ? { automated: { selfHeal: true } } : { syncOptions: ["CreateNamespace=true"] },
    auto_sync: autoSync,
  };
}

function installed(
  team: string,
  name: string,
  overrides: Partial<InstalledChart> = {},
): InstalledChart {
  const fleet = overrides.source === "fleet-default";
  const folder = fleet ? `defaults/hosted-clusters/${name}` : `${HOSTED_FOLDER}/${name}`;
  const version = overrides.version ?? catalogEntry(team, name).current_version;
  return {
    team,
    name,
    version,
    override_values: {},
    parse_errors: [],
    gitlab_url: `https://gitlab.example.com/sigs/${team}/-/tree/main/${folder}`,
    source: "cluster",
    path: folder,
    override_path: fleet ? `${folder}/values-${HOSTED_NAME}.yaml` : `${folder}/values.yaml`,
    last_commit_id: `${name}-commit-1`,
    pinned: false,
    deploy: leaf(team, name, version),
    warnings: [],
    ...overrides,
  };
}

export function hostedCharts(): DestinationCharts {
  return {
    cluster: HOSTED_NAME,
    mce: "mce-a",
    id: HOSTED_ID,
    kind: "hosted",
    site: "site1",
    env: "prod",
    ocp_version: "4.18.22",
    installed: [
      installed("platform", "cert-manager", { override_values: { replicas: 2 }, last_commit_id: "c0ffee1" }),
      installed("platform", "external-secrets", { source: "fleet-default", last_commit_id: null }),
      installed("observability", "prometheus", {
        version: "2.44.0",
        pinned: true,
        override_values: { retention: "30d" },
        deploy: leaf("observability", "prometheus", "2.44.0", true),
        warnings: [
          finding({
            rule: "emergency-pin",
            severity: "info",
            message: `pins prometheus to 2.44.0 on ${HOSTED_NAME} only (an emergency pin)`,
            team: "observability",
            cluster: HOSTED_ID,
            chart: "prometheus",
          }),
        ],
      }),
    ],
    excluded: [{ team: "observability", name: "grafana", scope: "hosted-clusters" }],
    warnings: [],
    argocd_note:
      "Installed means the platform generates an ArgoCD app for the chart. Wingman has no ArgoCD access yet: sync and health are not shown, and leaf apps are manual-sync unless their syncPolicy is automated.",
  };
}

export function destination(id: string, overrides: Partial<Destination> = {}): Destination {
  const [kind, site = "", env = "", ...rest] = id.split(":");
  const name = id === "hub" ? "hub" : (rest[rest.length - 1] ?? "");
  return {
    id,
    kind: (id === "hub" ? "hub" : kind) as Destination["kind"],
    name,
    site,
    env,
    mce: kind === "hosted" ? rest[0] : kind === "mce" ? name : "",
    ocp_version: id === "hub" ? null : "4.18.22",
    argo: kind === "upi" || id === "hub" ? "prod-hub" : "mce-a",
    teams: ["platform"],
    in_day1: kind === "hosted" || kind === "mce",
    warnings: [],
    ...overrides,
  };
}

export const destinations: Destination[] = [
  destination("hub", { teams: ["platform", "observability"] }),
  destination(MCE_ID),
  destination(HOSTED_ID, { teams: ["platform", "observability"] }),
  destination("upi:site2:prep:ocp4-dok-site2", { site: "site2", env: "prep" }),
  ...TWIN_IDS.map((id) => destination(id)),
];

export const lints: Finding[] = [
  finding({
    rule: "repourl-missing",
    severity: "error",
    message: "no layer of kyverno's deploy config sets a lowercase `repourl`",
    team: "security",
    path: "sites/site1/prod/mces/mce-a/in-cluster/kyverno",
    cluster: MCE_ID,
    chart: "kyverno",
  }),
  finding({
    rule: "repourl-miscased",
    message: "operators/kyverno/kyverno.yaml sets `repoUrl`; the platform reads only lowercase `repourl`",
    team: "security",
    path: "operators/kyverno/kyverno.yaml",
    chart: "kyverno",
  }),
  finding({ rule: "emergency-pin", severity: "info", message: "prometheus is pinned on one cluster", team: "observability" }),
];

// ── Values previews ──────────────────────────────────────────────────────────

type Values = Record<string, unknown>;

function deepMerge(base: Values, top: Values): Values {
  const out: Values = { ...base };
  for (const [k, v] of Object.entries(top)) {
    const b = out[k];
    out[k] =
      v && typeof v === "object" && !Array.isArray(v) && b && typeof b === "object" && !Array.isArray(b)
        ? deepMerge(b as Values, v as Values)
        : v;
  }
  return out;
}

function label(values: Values, role: string): Values {
  return Object.fromEntries(
    Object.entries(values).map(([k, v]) => [k, v && typeof v === "object" && !Array.isArray(v) ? label(v as Values, role) : role]),
  );
}

/** What the service previews for a chart on the hosted cluster, with `override` as its own file. */
export function previewOf(team: string, chart: string, override?: Values): ValuesPreview {
  const entry = catalogEntry(team, chart);
  const current = hostedCharts().installed.find((c) => c.team === team && c.name === chart);
  const own = override ?? current?.override_values ?? {};
  const fleet = current?.source === "fleet-default";
  const ownRole = fleet ? "fleet-target" : "cluster";
  const ownPath = current?.override_path ?? `${HOSTED_FOLDER}/${chart}/values.yaml`;
  const layer = (role: string, path: string, values: Values, exists = true): ValueLayer => ({
    role,
    path,
    exists,
    values,
    last_commit_id: exists ? "abc1234" : null,
    problem: null,
  });
  const layers = [
    layer("team", `operators/${chart}/values.yaml`, entry.default_values),
    layer("site", "sites/site1/values.yaml", {}, false),
    layer("fleet", `defaults/hosted-clusters/${chart}/values.yaml`, {}, fleet),
    layer(ownRole, ownPath, own, Boolean(current)),
  ];
  const revision = current?.version ?? entry.current_version;
  return {
    merged: deepMerge(entry.default_values, own),
    provenance: deepMerge(label(entry.default_values, "team"), label(own, ownRole)) as ValuesPreview["provenance"],
    chart_values: {},
    team_values: entry.default_values,
    cluster_values: fleet ? {} : own,
    addon_name: chart,
    team,
    version: revision,
    cluster: HOSTED_ID,
    installed: Boolean(current),
    source: current?.source ?? "cluster",
    ocp_version: "4.18.22",
    chart: { project: `helm-charts/${chart}`, revision, path: ".", problem: null },
    layers,
    deploy: {
      ...leaf(team, chart, revision),
      repo_url: entry.argocd_metadata.repourl,
      layers: [
        layer("team", `operators/${chart}/${chart}.yaml`, { targetRevision: entry.current_version }),
        layer("cluster", `${HOSTED_FOLDER}/${chart}/${chart}.yaml`, current?.pinned ? { targetRevision: revision } : {}, Boolean(current?.pinned)),
      ],
      provenance: { targetRevision: `operators/${chart}/${chart}.yaml` },
    },
    warnings: [],
  };
}

// ── Writes ───────────────────────────────────────────────────────────────────

let iid = 40;

export function changeResult(team: string, verb: string, chart: string, files: ChangeResult["files"], notes: string[]): ChangeResult {
  iid += 1;
  return {
    iid,
    title: `[Wingman/Day2] ${verb} addon ${team}/${chart} ${verb === "Remove" ? "from" : "on"} ${HOSTED_NAME}`,
    description: "",
    author: { username: "test-admin", name: "", avatar_url: null },
    state: "opened",
    created_at: "2026-11-07T10:00:00+00:00",
    updated_at: "2026-11-07T10:00:00+00:00",
    web_url: `https://gitlab.example.com/sigs/${team}/-/merge_requests/${iid}`,
    source_branch: `platform/test-admin/${verb.toLowerCase()}-${chart}`,
    target_branch: "main",
    labels: ["wingman", "day2", verb.toLowerCase()],
    repo: "day2",
    has_conflicts: null,
    team,
    project_id: 7,
    sha: "1234567890abcdef",
    gitlab_author: "wingman-bot",
    cluster: HOSTED_ID,
    files,
    app_names: [`${team}-${HOSTED_NAME}-${chart}-deploy`],
    warnings: [],
    notes,
  };
}

export const SYNC_NOTE = "After the merge, ArgoCD on mce-a generates the app, which is manual-sync: nothing is deployed until someone syncs it.";
export const ORPHAN_NOTE = `ArgoCD orphans the workload: cert-manager keeps running on ${HOSTED_NAME}.`;

/** An RFC 9457 problem response. */
export function problem(status: number, code: string, detail: string, details: Record<string, unknown> = {}) {
  return {
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({ type: `/problems/${code.toLowerCase()}`, title: code, status, detail, instance: "", code, request_id: "req_test", details }),
  };
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

/** Requests the page made, for assertions on what it sent. */
export interface Day2Requests {
  writes: { method: string; url: string; body: unknown }[];
}

/**
 * Route every day2 read and write of the scenario. Register test-specific
 * overrides after this: route mocks match last registered first.
 */
export async function mockDay2World(page: Page): Promise<Day2Requests> {
  const seen: Day2Requests = { writes: [] };
  const charts = hostedCharts();

  await page.route("**/api/day2/gitlab-info", (r) =>
    json(r, { gitlab_url: "https://gitlab.example.com", sigs_group_path: "sigs", sigs_group_url: "https://gitlab.example.com/groups/sigs" }),
  );
  await page.route("**/api/day2/addons", (r) => json(r, day2Catalog));
  await page.route("**/api/day2/lints**", (r) => json(r, lints));
  await page.route("**/api/day2/clusters", (r) => json(r, destinations));

  await page.route(/\/api\/day2\/clusters\/[^/?]+(\?.*)?$/, (r) => {
    const key = decodeURIComponent(new URL(r.request().url()).pathname.split("/").pop() ?? "");
    const found = destinations.filter((d) => d.id === key || d.name === key);
    if (found.length === 1) return json(r, found[0]);
    if (found.length > 1) return r.fulfill(problem(422, "VALIDATION_ERROR", `'${key}' names ${found.length} destinations; address one by its id`, { cluster: key, candidates: found.map((d) => d.id) }));
    return r.fulfill(problem(404, "NOT_FOUND", `no cluster named '${key}' in day1 or any team repo`));
  });

  await page.route(/\/api\/day2\/clusters\/[^/?]+\/addons(\?.*)?$/, (r) => {
    const key = decodeURIComponent(new URL(r.request().url()).pathname.split("/")[4] ?? "");
    if (key === HOSTED_ID || key === HOSTED_NAME) return json(r, charts);
    const found = destinations.filter((d) => d.id === key || d.name === key);
    if (found.length > 1) return r.fulfill(problem(422, "VALIDATION_ERROR", `'${key}' names ${found.length} destinations; address one by its id`, { cluster: key, candidates: found.map((d) => d.id) }));
    const d = found[0];
    if (!d) return r.fulfill(problem(404, "NOT_FOUND", `no cluster named '${key}' in day1 or any team repo`));
    return json(r, { ...charts, cluster: d.name, id: d.id, kind: d.kind, site: d.site, env: d.env, mce: d.mce, ocp_version: d.ocp_version, installed: [], excluded: [] });
  });

  await page.route(/\/api\/day2\/clusters\/[^/?]+\/addons\/[^/?]+\/[^/?]+(\?.*)?$/, (r) => {
    const parts = new URL(r.request().url()).pathname.split("/");
    const [team, chart] = [decodeURIComponent(parts[6]), decodeURIComponent(parts[7])];
    const method = r.request().method();
    if (method === "GET") return json(r, previewOf(team, chart));
    seen.writes.push({ method, url: r.request().url(), body: r.request().postDataJSON() });
    const folder = `${HOSTED_FOLDER}/${chart}`;
    if (method === "POST")
      return json(r, changeResult(team, "Install", chart, [{ action: "create", path: `${folder}/values.yaml` }], [SYNC_NOTE]), 201);
    if (method === "PUT")
      return json(r, changeResult(team, "Update", chart, [{ action: "update", path: `${folder}/values.yaml` }], [SYNC_NOTE]));
    return json(r, changeResult(team, "Remove", chart, [{ action: "delete", path: `${folder}/values.yaml` }], [ORPHAN_NOTE]));
  });

  await page.route("**/api/day2/merge-preview", (r) => {
    const body = r.request().postDataJSON() as MergePreviewBody;
    return json(r, previewOf(body.team, body.addon, body.override_values));
  });

  await page.route(/\/api\/day2\/clusters\/[^/?]+\/addons\/bulk$/, (r) => {
    const body = r.request().postDataJSON() as BulkBody;
    seen.writes.push({ method: "POST", url: r.request().url(), body });
    const teams = [...new Set(body.addons.map((a) => a.team))];
    const result: BulkResult = {
      merge_requests: teams.map((team) =>
        changeResult(
          team,
          "Install",
          body.addons.filter((a) => a.team === team).map((a) => a.addon).join(","),
          body.addons.filter((a) => a.team === team).map((a) => ({ action: "create", path: `${HOSTED_FOLDER}/${a.addon}/values.yaml` })),
          [SYNC_NOTE],
        ),
      ),
      failed: [],
    };
    return json(r, result, 201);
  });

  await page.route(/\/api\/day2\/clusters\/[^/?]+\/upgrade-check\?.*$/, (r) => {
    const to = new URL(r.request().url()).searchParams.get("to") ?? "";
    return json(r, {
      cluster: HOSTED_ID,
      from_version: "4.18.22",
      to_version: to,
      warnings: [
        finding({
          rule: "ocp-version-pin-missing",
          message: `prometheus is pinned for 4.18.22 but has no ocp-versions/${to}/: it would fall back to the team default`,
          team: "observability",
          path: "operators/prometheus/ocp-versions",
          cluster: HOSTED_ID,
          chart: "prometheus",
        }),
      ],
    });
  });

  return seen;
}
