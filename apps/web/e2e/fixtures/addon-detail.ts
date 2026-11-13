import type { Page, Route } from "@playwright/test";
import { json } from "./api-handlers";
import { FLEET_DEFAULTS, MANUAL, TEAMS, changeOf, planFor } from "./authoring";
import { HOSTED_ID, MCE_ID, TWIN_IDS, day2Catalog, problem } from "./day2";
import type {
  AdoptionChange,
  AuthoringPlan,
  CatalogEntry,
  DestinationImpact,
  DestinationState,
  FleetScope,
  MergePreviewBody,
  AddonDetail,
  AddonSummary,
  MceInstalls,
  PlannedFileChange,
  RepoFile,
  ScopeDestination,
  ScopePanel,
  Team,
  ValueLayer,
  ValuesPreview,
} from "../../types/day2";

/**
 * The world of an add-on's page (ADR-0053), shaped like the service's answers
 * (docs/notes/2026-11-12-operators-page-api.md), on top of fixtures/day2.ts
 * (the catalog, the destinations) and fixtures/authoring.ts (the teams, the
 * fleet defaults). platform/cert-manager is the rich one: a default on every
 * MCE with each destination state, an override, an own deploy config and an
 * exclusions file; every other add-on is generated from the catalog and
 * the fleet defaults.
 *
 * Writes follow the 3.10 contract: a dry run answers the plan with its
 * `digest`; a real write must repeat `needs_confirmation` in
 * `confirm_changes` and the digest in `expected_digest` (422 and 409
 * `plan-changed` otherwise, as the service does).
 */

const SCOPES: FleetScope[] = ["hosted-clusters", "mces", "hub", "upi"];
const LABEL: Record<FleetScope, string> = {
  "hosted-clusters": "every hosted cluster",
  mces: "every MCE",
  hub: "the hub",
  upi: "every UPI cluster",
};
const NOUN: Record<FleetScope, string> = { "hosted-clusters": "hosted cluster(s)", mces: "MCE(s)", hub: "hub", upi: "UPI cluster(s)" };
const UPI_ID = "upi:site2:prep:ocp4-dok-site2";

export const MCE_A = "mce:site1:prep:ocp4-prep-mce-site1-a";
export const MCE_A_NAME = "ocp4-prep-mce-site1-a";
export const MCE_EXCLUDED = "mce:site1:prod:ocp4-prod-mce-site1-a";
export const MCE_EXCLUDED_NAME = "ocp4-prod-mce-site1-a";
export const MCE_OWN = "mce:site2:prod:ocp4-prod-mce-site2-b";
export const MCE_OWN_NAME = "ocp4-prod-mce-site2-b";
export const MCE_OVERRIDE = "mce:site2:test:ocp4-test-mce-site2-c";
export const MCE_OVERRIDE_NAME = "ocp4-test-mce-site2-c";
export const MCE_UNRENDERED = "mce:site3:prep:ocp4-prep-mce-site3-d";
export const MCE_UNREGISTERED = "mce:site9:prod:ocp4-prod-mce-site9-z";

/** The commit every read of a team repo is at. */
export const commitOf = (team: string) => `${team}-repo-1`;

/** The deploy config of platform/cert-manager, comments and all: the page shows the text, not a re-rendering. */
export const CERT_MANAGER_YAML =
  "# Manual sync: cert-manager owns the cluster's CRDs, nobody syncs it by accident.\nrepourl: https://gitlab.example.com/helm-charts/cert-manager.git\nprojectNamespace: cert-manager\nsyncPolicy:\n  syncOptions:\n  - CreateNamespace=true\n";

function repoFile(team: string, path: string, text: string | null, values: Record<string, unknown> = {}): RepoFile {
  return { path, exists: text !== null, text, values, last_commit_id: text !== null ? commitOf(team) : null, problem: null };
}

function parts(id: string): Pick<ScopeDestination, "kind" | "site" | "env" | "mce" | "name"> {
  if (id === "hub") return { kind: "hub", site: "", env: "", mce: "", name: "hub" };
  const [kind, site = "", env = "", ...rest] = id.split(":");
  const name = rest[rest.length - 1] ?? "";
  return { kind: kind as ScopeDestination["kind"], site, env, mce: kind === "hosted" ? rest[0] : kind === "mce" ? name : "", name };
}

function destination(team: string, chart: string, scope: FleetScope, id: string, state: DestinationState, extra: Partial<ScopeDestination> = {}): ScopeDestination {
  const p = parts(id);
  const deployed = ["default", "own-deploy", "duplicate", "own-folder"].includes(state);
  return {
    id,
    ...p,
    ocp_version: state === "not-rendered" ? null : "4.18.22",
    renders: state !== "not-rendered",
    state,
    deployed,
    app_name: deployed ? `${team}-${p.name}-${chart}-deploy` : null,
    override: scope === "hub" ? null : repoFile(team, `defaults/${scope}/${chart}/values-${p.name}.yaml`, null),
    override_shared_with: [],
    own_folder: null,
    own_deploy: null,
    ...extra,
  };
}

function panel(
  team: string,
  chart: string,
  scope: FleetScope,
  isDefault: boolean,
  destinations: ScopeDestination[],
  extra: Partial<ScopePanel> = {},
): ScopePanel {
  const folder = `defaults/${scope}/${chart}`;
  return {
    scope,
    label: LABEL[scope],
    noun: NOUN[scope],
    is_default: isDefault,
    folder,
    values_file: repoFile(team, `${folder}/values.yaml`, isDefault ? "{}\n" : null),
    deploy_config: repoFile(team, `${folder}/${chart}.yaml`, null),
    sync: MANUAL,
    sync_overridden: false,
    env_files: [],
    exclusions:
      scope === "hub"
        ? null
        : {
            path: `defaults/${scope}/exclusions.yaml`,
            exists: false,
            names: [],
            unknown_names: [],
            last_commit_id: commitOf(team),
          },
    destinations,
    unregistered: [],
    last_commit_id: commitOf(team),
    ...extra,
  };
}

/** platform/cert-manager on every MCE: one destination in each state the page shows. */
function certManagerMces(): ScopePanel {
  const t = "platform";
  const c = "cert-manager";
  const d = (id: string, state: DestinationState, extra: Partial<ScopeDestination> = {}) => destination(t, c, "mces", id, state, extra);
  return panel(
    t,
    c,
    "mces",
    true,
    [
      d(MCE_A, "default"),
      d(MCE_EXCLUDED, "excluded"),
      d(MCE_OWN, "own-deploy", {
        own_folder: `sites/site2/prod/mces/${MCE_OWN_NAME}/in-cluster/${c}`,
        own_deploy: repoFile(t, `sites/site2/prod/mces/${MCE_OWN_NAME}/in-cluster/${c}/${c}.yaml`, "# pinned while 1.13 is tested\ntargetRevision: 1.11.0\n", {
          targetRevision: "1.11.0",
        }),
      }),
      d(MCE_OVERRIDE, "default", {
        override: repoFile(t, `defaults/mces/${c}/values-${MCE_OVERRIDE_NAME}.yaml`, "# a test MCE needs more\nreplicas: 3\n", { replicas: 3 }),
      }),
      d(MCE_UNRENDERED, "not-rendered"),
    ],
    {
      values_file: repoFile(t, `defaults/mces/${c}/values.yaml`, "# the MCEs bring their own CRDs\ninstallCRDs: false\n", { installCRDs: false }),
      exclusions: {
        path: "defaults/mces/exclusions.yaml",
        exists: true,
        names: [MCE_EXCLUDED_NAME, MCE_OWN_NAME, "ocp4-old-mce"],
        unknown_names: ["ocp4-old-mce"],
        last_commit_id: "platform-exclusions-1",
      },
      unregistered: [{ id: MCE_UNREGISTERED, name: "ocp4-prod-mce-site9-z", site: "site9", env: "prod", mce: "ocp4-prod-mce-site9-z" }],
    },
  );
}

const RICH = (team: string, chart: string) => team === "platform" && chart === "cert-manager";

/** platform/external-secrets on the MCEs: no default; installed on one MCE, others to deploy on. */
function externalSecretsMces(): ScopePanel {
  const t = "platform";
  const c = "external-secrets";
  const d = (id: string, state: DestinationState, extra: Partial<ScopeDestination> = {}) => destination(t, c, "mces", id, state, extra);
  return panel(
    t,
    c,
    "mces",
    false,
    [
      d(MCE_A, "none"),
      d(MCE_EXCLUDED, "own-folder", {
        own_folder: `sites/site1/prod/mces/${MCE_EXCLUDED_NAME}/in-cluster/${c}`,
        app_name: `${t}-in-cluster-${c}-deploy`,
      }),
      d(MCE_UNRENDERED, "not-rendered"),
    ],
    { unregistered: [{ id: MCE_UNREGISTERED, name: "ocp4-prod-mce-site9-z", site: "site9", env: "prod", mce: "ocp4-prod-mce-site9-z" }] },
  );
}

/** platform/external-secrets on every hosted cluster: one cluster with its own values, and a prod env file. */
function externalSecretsHosted(catalog: CatalogEntry | null): ScopePanel {
  const base = generatedPanel("platform", "external-secrets", "hosted-clusters", catalog);
  const folder = base.folder;
  return {
    ...base,
    env_files: [{ env: "prod", file: repoFile("platform", `${folder}/values-prod.yaml`, "# prod clusters poll less\nrefreshInterval: 5m\n", { refreshInterval: "5m" }) }],
    destinations: base.destinations.map((d) =>
      d.id === HOSTED_ID
        ? { ...d, override: repoFile("platform", `${folder}/values-${d.name}.yaml`, "# a noisy cluster\nreplicaCount: 3\n", { replicaCount: 3 }) }
        : d,
    ),
  };
}

const MCE_PANEL = (team: string, chart: string) =>
  RICH(team, chart) ? certManagerMces() : team === "platform" && chart === "external-secrets" ? externalSecretsMces() : null;

/** The destinations of a scope, and their state, for a generated add-on. */
function generatedPanel(team: string, chart: string, scope: FleetScope, catalog: CatalogEntry | null): ScopePanel {
  const fd = FLEET_DEFAULTS.find((f) => f.team === team && f.chart === chart && f.scope === scope);
  const isDefault = Boolean(fd) || Boolean(catalog?.fleet_defaults.includes(scope));
  const ids = scope === "hosted-clusters" ? [HOSTED_ID, ...TWIN_IDS] : scope === "mces" ? [MCE_ID] : scope === "hub" ? ["hub"] : [UPI_ID];
  const destinations = ids.map((id) => {
    let state: DestinationState = isDefault ? "default" : "none";
    if (isDefault && fd?.excluded.includes(id)) state = "excluded";
    // The clusters the make-default plan adopts have the chart in their own folder.
    if (!isDefault && RICH(team, chart) && scope === "hosted-clusters" && (id === HOSTED_ID || id === TWIN_IDS[0])) state = "own-folder";
    const shared = scope === "hosted-clusters" && TWIN_IDS.includes(id) ? TWIN_IDS.filter((t) => t !== id) : [];
    return destination(team, chart, scope, id, state, { override_shared_with: shared });
  });
  const folder = `defaults/${scope}/${chart}`;
  const values = fd?.values ?? {};
  return panel(team, chart, scope, isDefault, destinations, {
    values_file: { ...repoFile(team, `${folder}/values.yaml`, isDefault ? (Object.keys(values).length ? "replicaCount: 2\n" : "{}\n") : null, values), last_commit_id: fd?.last_commit_id ?? commitOf(team) },
    deploy_config: repoFile(team, `${folder}/${chart}.yaml`, fd?.sync_overridden ? "syncPolicy:\n  automated:\n    selfHeal: true\n" : null),
    sync: fd?.sync ?? catalog?.sync ?? MANUAL,
    sync_overridden: fd?.sync_overridden ?? false,
    exclusions:
      scope === "hub"
        ? null
        : {
            path: `defaults/${scope}/exclusions.yaml`,
            exists: Boolean(fd?.excluded.length),
            names: fd?.excluded.map((id) => parts(id).name) ?? [],
            unknown_names: [],
            last_commit_id: commitOf(team),
          },
  });
}

/** `GET /teams/{team}/addons/{addon}`, or `null` (a 404). */
export function addonDetailOf(team: string, chart: string): AddonDetail | null {
  const catalog = day2Catalog.find((e) => e.team === team && e.name === chart) ?? null;
  const fleet = FLEET_DEFAULTS.filter((f) => f.team === team && f.chart === chart);
  if (!catalog && fleet.length === 0) return null;
  const access = TEAMS.find((t) => t.name === team);
  const writable = access?.writable ?? true;
  const scopes = SCOPES.map(
    (scope) =>
      (scope === "mces" && MCE_PANEL(team, chart)) ||
      (scope === "hosted-clusters" && team === "platform" && chart === "external-secrets" && externalSecretsHosted(catalog)) ||
      generatedPanel(team, chart, scope, catalog),
  );
  const op = `operators/${chart}`;
  return {
    team,
    name: chart,
    in_catalog: Boolean(catalog),
    writable,
    read_only_reason: writable ? null : (access?.read_only_reason ?? null),
    catalog: catalog ? { ...catalog, writable, read_only_reason: writable ? null : (access?.read_only_reason ?? null) } : null,
    deploy_config: RICH(team, chart)
      ? repoFile(team, `${op}/${chart}.yaml`, CERT_MANAGER_YAML, { repourl: catalog?.argocd_metadata.repourl })
      : repoFile(team, `${op}/${chart}.yaml`, catalog ? `repourl: ${catalog.argocd_metadata.repourl}\n` : null),
    values_file: repoFile(team, `${op}/values.yaml`, catalog ? "# the team's values\nreplicas: 1\n" : null, catalog?.default_values ?? {}),
    ocp_versions: (catalog?.ocp_version_pins ?? []).map((pin) => ({
      version: pin.version,
      target_revision: pin.target_revision,
      deploy_config: repoFile(team, `${op}/ocp-versions/${pin.version}/${chart}.yaml`, `targetRevision: ${pin.target_revision}\n`),
      values_file: repoFile(team, `${op}/ocp-versions/${pin.version}/values.yaml`, null),
    })),
    scopes,
    warnings: catalog?.warnings ?? [],
  };
}

/** `GET /teams/{team}/addons`: one per catalog entry, plus each fleet default without one. */
export function teamAddonsOf(team: string): AddonSummary[] {
  const names = new Set([
    ...day2Catalog.filter((e) => e.team === team).map((e) => e.name),
    ...FLEET_DEFAULTS.filter((f) => f.team === team).map((f) => f.chart),
  ]);
  return [...names].sort().map((name) => {
    const d = addonDetailOf(team, name) as AddonDetail;
    return {
      team,
      name,
      in_catalog: d.in_catalog,
      repourl: d.catalog?.argocd_metadata.repourl ?? "",
      target_revision: d.catalog?.current_version ?? "HEAD",
      sync: d.catalog?.sync ?? MANUAL,
      ocp_versions: d.ocp_versions.map((p) => p.version),
      defaults: d.scopes
        .filter((s) => s.is_default)
        .map((s) => ({
          scope: s.scope,
          label: s.label,
          reach: s.destinations.filter((x) => x.state === "default" || x.state === "duplicate").length,
          excluded: s.destinations.filter((x) => x.state === "excluded" || x.state === "own-deploy").length,
        })),
      installed_on: name === "cert-manager" ? 2 : 0,
      warnings: d.warnings.length,
      writable: d.writable,
      read_only_reason: d.read_only_reason,
    };
  });
}

// ── merge-preview ────────────────────────────────────────────────────────────

type Values = Record<string, unknown>;

/** Helm's merge: mappings merge, a null deletes the key. */
function merge(base: Values, top: Values): Values {
  const out: Values = { ...base };
  for (const [k, v] of Object.entries(top)) {
    if (v === null) delete out[k];
    else if (v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object" && !Array.isArray(out[k]))
      out[k] = merge(out[k] as Values, v as Values);
    else out[k] = v;
  }
  return out;
}

function roles(values: Values, role: string): Values {
  return Object.fromEntries(
    Object.entries(values)
      .filter(([, v]) => v !== null)
      .map(([k, v]) => [k, v && typeof v === "object" && !Array.isArray(v) ? roles(v as Values, role) : role]),
  );
}

/** `POST /merge-preview` of a fleet default's destination: team, fleet, then its `values-<name>.yaml`. */
export function addonPreview(body: MergePreviewBody): ValuesPreview {
  const detail = addonDetailOf(body.team, body.addon) as AddonDetail;
  const scope = detail.scopes.find((s) => s.destinations.some((d) => d.id === body.cluster)) ?? detail.scopes[1];
  const dest = scope.destinations.find((d) => d.id === body.cluster);
  const team = detail.catalog?.default_values ?? {};
  const fleet = scope.values_file.values;
  const envPath = `${scope.folder}/values-${dest?.env}.yaml`;
  const editsEnv = body.override_path === envPath;
  const envFile = scope.env_files.find((e) => e.env === dest?.env)?.file;
  const envValues = editsEnv ? (body.override_values ?? {}) : (envFile?.values ?? {});
  const own = (editsEnv ? undefined : body.override_values) ?? dest?.override?.values ?? {};
  const layer = (role: string, path: string, values: Values, exists = true): ValueLayer => ({ role, path, exists, values, last_commit_id: exists ? commitOf(body.team) : null, problem: null });
  const layers = [
    layer("team", `operators/${body.addon}/values.yaml`, team),
    layer("fleet", scope.values_file.path, fleet),
    layer("fleet-env", envPath, envValues, Object.keys(envValues).length > 0),
    layer("fleet-target", dest?.override?.path ?? `${scope.folder}/values-${dest?.name}.yaml`, own, Object.keys(own).length > 0),
  ];
  const merged = merge(merge(merge(team, fleet), envValues), own);
  const provenance = merge(merge(merge(roles(team, "team"), roles(fleet, "fleet")), roles(envValues, "fleet-env")), roles(own, "fleet-target"));
  return {
    merged,
    provenance: provenance as ValuesPreview["provenance"],
    chart_values: {},
    team_values: team,
    cluster_values: own,
    addon_name: body.addon,
    team: body.team,
    version: detail.catalog?.current_version ?? "HEAD",
    cluster: body.cluster,
    installed: Boolean(dest?.deployed),
    source: "fleet-default",
    ocp_version: dest?.ocp_version ?? null,
    chart: { project: `helm-charts/${body.addon}`, revision: detail.catalog?.current_version ?? "HEAD", path: ".", problem: null },
    layers,
    deploy: {
      app_name: dest?.app_name ?? `${body.team}-${dest?.name}-${body.addon}-deploy`,
      argo: "hub",
      namespace: `gitops-${body.team}`,
      repo_url: detail.catalog?.argocd_metadata.repourl ?? "",
      target_revision: detail.catalog?.current_version ?? "HEAD",
      path: ".",
      release_name: body.addon,
      destination: dest?.name ?? body.cluster,
      destination_namespace: body.addon,
      sync_policy: {},
      auto_sync: false,
      layers: [],
      provenance: {},
    },
    warnings: [],
  };
}

// ── Writes ───────────────────────────────────────────────────────────────────


function file(action: PlannedFileChange["action"], path: string, content: string | null, previous: string | null): PlannedFileChange {
  return { action, path, content, previous };
}

function impact(detail: AddonDetail, id: string, effect: DestinationImpact["effect"], changes: AdoptionChange[] = []): DestinationImpact {
  const d = detail.scopes.flatMap((s) => s.destinations).find((x) => x.id === id);
  const name = d?.name ?? parts(id).name;
  return {
    cluster: id,
    name,
    kind: d?.kind ?? parts(id).kind,
    effect,
    app_name: `${detail.team}-${name}-${detail.name}-deploy`,
    changes,
    orphaned: effect === "removed",
  };
}

/** The plan of a write at `url` with `body`, at repo `version` (a plan-changed bumps it). */
function addonPlan(method: string, url: URL, body: Values, version: number): AuthoringPlan {
  const p = url.pathname.split("/").map(decodeURIComponent);
  const [team, chart, scope] = [p[4], p[5], p[7] as FleetScope | undefined];
  const detail = team && chart ? addonDetailOf(team, chart) : null;
  const confirmOf = (i: DestinationImpact[]) => i.filter((x) => x.effect !== "added").map((x) => x.cluster);
  const finish = (plan: Omit<AuthoringPlan, "digest">): AuthoringPlan => ({ ...plan, digest:`digest-v${version}-${plan.action}-${chart ?? ""}-${scope ?? ""}` });

  if (detail && scope && p[8] === "envs") {
    const env = p[9];
    const values = body.values as Values | null;
    const panelOf = detail.scopes.find((x) => x.scope === scope) as ScopePanel;
    const current = panelOf.env_files.find((e) => e.env === env)?.file;
    const path = current?.path ?? `${panelOf.folder}/values-${env}.yaml`;
    const changes: AdoptionChange[] = Object.entries(values ?? current?.values ?? {}).map(([key, v]) => ({
      stack: "values",
      key,
      before: values ? (current?.values[key] ?? null) : v,
      after: values ? v : null,
    }));
    const reached = panelOf.destinations.filter((d) => d.env === env && d.state === "default");
    const imp = reached.map((d) => impact(detail, d.id, "changed", changes));
    return finish({
      team,
      action: "override-values",
      chart,
      scope,
      title: values
        ? `[Wingman/Day2] Override addon ${team}/${chart} values for ${env} (fleet default on ${LABEL[scope]})`
        : `[Wingman/Day2] Override addon ${team}/${chart} values for ${env}: back to the fleet default (fleet default on ${LABEL[scope]})`,
      files: [
        values
          ? file(current?.exists ? "update" : "create", path, Object.entries(values).map(([k, v]) => `${k}: ${String(v)}`).join("\n") + "\n", current?.text ?? null)
          : file("delete", path, null, current?.text ?? ""),
      ],
      reach: reached.map((d) => d.id),
      adopted: [],
      needs_confirmation: confirmOf(imp),
      warnings: [],
      notes: [],
      impact: imp,
      excluded: [],
    });
  }

  if (detail && scope && p[8] === "destinations") {
    const cluster = p[9];
    const dest = detail.scopes.flatMap((s) => s.destinations).find((d) => d.id === cluster);
    const name = dest?.name ?? parts(cluster).name;
    // Values of one destination: the only per-destination write (no exclusions, no own deploy config).
    {
      const values = body.values as Values | null;
      const team_values = detail.catalog?.default_values ?? {};
      const changes: AdoptionChange[] = Object.entries(values ?? dest?.override?.values ?? {}).map(([key, v]) => ({
        stack: "values",
        key,
        before: values ? (dest?.override?.values[key] ?? team_values[key] ?? null) : v,
        after: values ? v : (team_values[key] ?? null),
      }));
      const imp = [impact(detail, cluster, "changed", changes), ...(dest?.override_shared_with ?? []).map((id) => impact(detail, id, "changed", changes))];
      const path = dest?.override?.path ?? `defaults/${scope}/${chart}/values-${name}.yaml`;
      return finish({
        team,
        action: "override-values",
        chart,
        scope,
        title: values
          ? `[Wingman/Day2] Override addon ${team}/${chart} values on ${name} (fleet default on ${LABEL[scope]})`
          : `[Wingman/Day2] Override addon ${team}/${chart} values on ${name}: back to the fleet default (fleet default on ${LABEL[scope]})`,
        files: [
          values
            ? file(dest?.override?.exists ? "update" : "create", path, Object.entries(values).map(([k, v]) => `${k}: ${String(v)}`).join("\n") + "\n", dest?.override?.text ?? null)
            : file("delete", path, null, dest?.override?.text ?? ""),
        ],
        reach: [cluster],
        adopted: [],
        needs_confirmation: confirmOf(imp),
        warnings: [],
        notes: [],
        impact: imp,
        excluded: [],
      });
    }
  }

  // The 3.8 writes (create, edit the add-on: the API's update-team-default, make default, fleet default), with 3.10's impact.
  const plan = planFor(method, url, body);
  if (detail && plan.action === "update-team-default" && RICH(team, chart)) {
    const imp = [
      impact(detail, MCE_A, "changed", [
        { stack: "values", key: "replicas", before: 1, after: 2, after_null: false },
        // A Helm null: it deletes the chart's own default.
        { stack: "values", key: "resources.limits.cpu", before: "500m", after: null, after_null: true },
        // No longer set: not a null.
        { stack: "values", key: "installCRDs", before: true, after: null, after_null: false },
      ]),
      // The repo moved: the new plan reaches one more destination.
      ...(version > 1 ? [impact(detail, MCE_OVERRIDE, "changed", [{ stack: "deploy", key: "projectNamespace", before: "cert-manager", after: "certs" }])] : []),
    ];
    return finish({ ...plan, impact: imp, needs_confirmation: confirmOf(imp), reach: [MCE_A, MCE_OVERRIDE] });
  }
  return finish(plan);
}

/** What the page sent. */
export interface AddonRequests {
  writes: { method: string; path: string; dryRun: boolean; body: Values }[];
  previews: MergePreviewBody[];
}

const sorted = (ids: unknown) => (Array.isArray(ids) ? [...ids].map(String).sort() : []);

/**
 * Route the add-on reads (the list, one add-on, merge-preview) and every
 * authoring write. Register after mockDay2World and mockAuthoring (route mocks
 * match last registered first). `planChangedOnce`: the repo moves before the
 * first real write, which answers 409 plan-changed.
 */
export async function mockAddonDetail(
  page: Page,
  {
    teams,
    planChangedOnce = false,
    failMce = null,
  }: {
    teams?: Team[];
    planChangedOnce?: boolean;
    /** An MCE whose install MR GitLab refuses (the others open). */
    failMce?: string | null;
  } = {},
): Promise<AddonRequests> {
  const seen: AddonRequests = { writes: [], previews: [] };
  let version = 1;
  let moved = false;
  if (teams) await page.route("**/api/day2/teams", (r) => json(r, teams));
  await page.route(/\/api\/day2\/teams\/[^/?]+\/addons(\?.*)?$/, (r) =>
    json(r, teamAddonsOf(decodeURIComponent(new URL(r.request().url()).pathname.split("/")[4]))),
  );
  await page.route(/\/api\/day2\/teams\/[^/?]+\/addons\/[^/?]+(\?.*)?$/, (r) => {
    const p = new URL(r.request().url()).pathname.split("/").map(decodeURIComponent);
    const detail = addonDetailOf(p[4], p[6]);
    if (!detail) return r.fulfill(problem(404, "NOT_FOUND", `${p[4]} has no add-on ${p[6]}`));
    return json(r, detail);
  });
  await page.route("**/api/day2/merge-preview", (r) => {
    const body = r.request().postDataJSON() as MergePreviewBody;
    seen.previews.push(body);
    return json(r, addonPreview(body));
  });

  const write = async (r: Route) => {
    const request = r.request();
    const method = request.method();
    if (method === "GET") return r.fallback();
    const url = new URL(request.url());
    const dryRun = url.searchParams.get("dry_run") === "true";
    const body = (request.postDataJSON() ?? {}) as Values;
    seen.writes.push({ method, path: url.pathname, dryRun, body });
    if (!dryRun && planChangedOnce && !moved) {
      moved = true;
      version += 1;
    }
    const plan = addonPlan(method, url, body, version);
    if (dryRun) return json(r, plan);
    if (plan.needs_confirmation.length > 0 && !body.expected_digest)
      return r.fulfill(problem(422, "VALIDATION_ERROR", "confirm against a preview: send its digest", { rule: "confirm-against-preview" }));
    if (body.expected_digest && body.expected_digest !== plan.digest)
      return r.fulfill(
        problem(409, "REVISION_CONFLICT", "The repo changed since the preview: the plan is no longer the one previewed.", {
          rule: "plan-changed",
          digest: plan.digest,
        }),
      );
    if (JSON.stringify(sorted(body.confirm_changes)) !== JSON.stringify(sorted(plan.needs_confirmation)))
      return r.fulfill(problem(422, "VALIDATION_ERROR", "confirm exactly the destinations the plan lists", { rule: "confirm-changes", needs_confirmation: plan.needs_confirmation }));
    return json(r, { ...changeOf(plan), impact: plan.impact, excluded: plan.excluded, digest: plan.digest, needs_confirmation: plan.needs_confirmation }, method === "POST" ? 201 : 200);
  };
  await page.route(/\/api\/day2\/addons\/[^/?]+(\?.*)?$/, write);
  await page.route(/\/api\/day2\/addons\/[^/?]+\/[^/?]+(\?.*)?$/, write);
  await page.route(/\/api\/day2\/addons\/[^/?]+\/[^/?]+\/defaults\/[^/?]+(\?.*)?$/, write);
  await page.route(/\/api\/day2\/addons\/[^/?]+\/[^/?]+\/defaults\/[^/?]+\/destinations\/[^/?]+\/values(\?.*)?$/, write);
  await page.route(/\/api\/day2\/addons\/[^/?]+\/[^/?]+\/defaults\/[^/?]+\/envs\/[^/?]+\/values(\?.*)?$/, write);
  await page.route(/\/api\/day2\/addons\/[^/?]+\/[^/?]+\/mce-installs(\?.*)?$/, (r) => {
    const url = new URL(r.request().url());
    const dryRun = url.searchParams.get("dry_run") === "true";
    const body = (r.request().postDataJSON() ?? {}) as Values;
    seen.writes.push({ method: "POST", path: url.pathname, dryRun, body });
    const [team, chart] = url.pathname.split("/").map(decodeURIComponent).slice(4, 6);
    const result = mceInstalls(team, chart, (body.clusters as string[]) ?? [], dryRun, failMce);
    return json(r, result, !dryRun && result.installs.some((i: MceInstalls["installs"][number]) => i.status === "opened") ? 201 : 200);
  });
  return seen;
}

let installIid = 40;

/** `POST /addons/{team}/{addon}/mce-installs`: one install per MCE; a site3 one renders nothing. */
export function mceInstalls(team: string, chart: string, clusters: string[], dryRun: boolean, failMce: string | null = null): MceInstalls {
  return {
    team,
    chart,
    installs: clusters.map((id) => {
      const { name, site, env } = parts(id);
      const path = `sites/${site}/${env}/mces/${name}/in-cluster/${chart}/values.yaml`;
      const base = {
        cluster: id,
        name,
        files: [{ action: "create", path }],
        notes: [`After the merge, ArgoCD on ${name} generates ${team}-in-cluster-${chart}-deploy, which is manual-sync.`],
        warnings: [],
        merge_request: null,
        detail: null,
        rule: null,
      };
      if (site === "site3")
        return { ...base, files: [], notes: [], status: "refused" as const, detail: `day1 has no mastertag for ${name}`, rule: "day1-version-missing" };
      if (dryRun) return { ...base, status: "planned" as const };
      if (id === failMce) return { ...base, status: "failed" as const, detail: "GitLab refused the branch" };
      installIid += 1;
      const mr = changeOf({
        team,
        action: "create-addon",
        chart,
        scope: null,
        title: `[Wingman/Day2] Install addon ${team}/${chart} on ${name}`,
        files: [],
        reach: [],
        adopted: [],
        needs_confirmation: [],
        warnings: [],
        notes: [],
        impact: [],
        excluded: [],
        digest: "",
      });
      return { ...base, status: "opened" as const, merge_request: { ...mr, iid: installIid, web_url: `https://gitlab.example.com/sigs/${team}/-/merge_requests/${installIid}` } };
    }),
  };
}

