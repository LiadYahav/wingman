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
  PlannedFileChange,
  RepoFile,
  ScopeDestination,
  ScopePanel,
  Team,
  ValueLayer,
  ValuesPreview,
} from "../../types/day2";

/**
 * The Operators pages' world (ADR-0053), shaped like the service's answers
 * (docs/notes/2026-11-12-operators-page-api.md), on top of fixtures/day2.ts
 * (the catalog, the destinations) and fixtures/authoring.ts (the teams, the
 * fleet defaults). platform/cert-manager is the rich one: a default on every
 * MCE with each destination state, an override, an own deploy config and an
 * exclusions file; every other operator is generated from the catalog and
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
            editable: true,
            problem: null,
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
        editable: true,
        problem: null,
        last_commit_id: "platform-exclusions-1",
      },
      unregistered: [{ id: MCE_UNREGISTERED, name: "ocp4-prod-mce-site9-z", site: "site9", env: "prod", mce: "ocp4-prod-mce-site9-z" }],
    },
  );
}

const RICH = (team: string, chart: string) => team === "platform" && chart === "cert-manager";

/** The destinations of a scope, and their state, for a generated operator. */
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
            editable: true,
            problem: null,
            last_commit_id: commitOf(team),
          },
  });
}

/** `GET /teams/{team}/operators/{op}`, or `null` (a 404). */
export function operatorDetail(team: string, chart: string): AddonDetail | null {
  const catalog = day2Catalog.find((e) => e.team === team && e.name === chart) ?? null;
  const fleet = FLEET_DEFAULTS.filter((f) => f.team === team && f.chart === chart);
  if (!catalog && fleet.length === 0) return null;
  const access = TEAMS.find((t) => t.name === team);
  const writable = access?.writable ?? true;
  const scopes = SCOPES.map((scope) => (RICH(team, chart) && scope === "mces" ? certManagerMces() : generatedPanel(team, chart, scope, catalog)));
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

/** `GET /teams/{team}/operators`: one per catalog entry, plus each fleet default without one. */
export function operatorsOf(team: string): AddonSummary[] {
  const names = new Set([
    ...day2Catalog.filter((e) => e.team === team).map((e) => e.name),
    ...FLEET_DEFAULTS.filter((f) => f.team === team).map((f) => f.chart),
  ]);
  return [...names].sort().map((name) => {
    const d = operatorDetail(team, name) as AddonDetail;
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
export function operatorPreview(body: MergePreviewBody): ValuesPreview {
  const detail = operatorDetail(body.team, body.addon) as AddonDetail;
  const scope = detail.scopes.find((s) => s.destinations.some((d) => d.id === body.cluster)) ?? detail.scopes[1];
  const dest = scope.destinations.find((d) => d.id === body.cluster);
  const team = detail.catalog?.default_values ?? {};
  const fleet = scope.values_file.values;
  const own = body.override_values ?? dest?.override?.values ?? {};
  const layer = (role: string, path: string, values: Values, exists = true): ValueLayer => ({ role, path, exists, values, last_commit_id: exists ? commitOf(body.team) : null, problem: null });
  const layers = [
    layer("team", `operators/${body.addon}/values.yaml`, team),
    layer("fleet", scope.values_file.path, fleet),
    layer("fleet-target", dest?.override?.path ?? `${scope.folder}/values-${dest?.name}.yaml`, own, Object.keys(own).length > 0),
  ];
  const merged = merge(merge(team, fleet), own);
  const provenance = merge(merge(roles(team, "team"), roles(fleet, "fleet")), roles(own, "fleet-target"));
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

const NOTE_ORPHAN = "ArgoCD orphans the workload where the Application goes: it keeps running, unmanaged.";

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
function operatorPlan(method: string, url: URL, body: Values, version: number): AuthoringPlan {
  const p = url.pathname.split("/").map(decodeURIComponent);
  const [team, chart, scope] = [p[4], p[5], p[7] as FleetScope | undefined];
  const detail = team && chart ? operatorDetail(team, chart) : null;
  const confirmOf = (i: DestinationImpact[]) => i.filter((x) => x.effect !== "added").map((x) => x.cluster);
  const finish = (plan: Omit<AuthoringPlan, "digest">): AuthoringPlan => ({ ...plan, digest:`digest-v${version}-${plan.action}-${chart ?? ""}-${scope ?? ""}` });

  if (detail && scope && p[8] === "exclusions") {
    const panelOf = detail.scopes.find((s) => s.scope === scope) as ScopePanel;
    const before = new Set(panelOf.destinations.filter((d) => d.state === "excluded" || d.state === "own-deploy").map((d) => d.id));
    const after = new Set((body.excluded as string[]) ?? []);
    const imp = [
      ...[...after].filter((id) => !before.has(id)).map((id) => impact(detail, id, "removed")),
      ...[...before].filter((id) => !after.has(id)).map((id) => impact(detail, id, "added")),
    ];
    const names = (e: string) => imp.filter((i) => i.effect === e).map((i) => i.name).join(", ");
    const title = imp.every((i) => i.effect === "removed")
      ? `[Wingman/Day2] Exclude addon ${team}/${chart} from ${names("removed")} (fleet default on ${LABEL[scope]})`
      : imp.every((i) => i.effect === "added")
        ? `[Wingman/Day2] Include addon ${team}/${chart} on ${names("added")} (fleet default on ${LABEL[scope]})`
        : `[Wingman/Day2] Update addon ${team}/${chart} exclusions (fleet default on ${LABEL[scope]})`;
    return finish({
      team,
      action: "set-exclusions",
      chart,
      scope,
      title,
      files: [file("update", `defaults/${scope}/exclusions.yaml`, `# kept off by hand\n${chart}:\n${[...after].map((id) => `- ${parts(id).name}`).join("\n")}\n`, `# kept off by hand\n${chart}:\n- ${MCE_EXCLUDED_NAME}\n`)],
      reach: panelOf.destinations.filter((d) => !after.has(d.id) && d.renders).map((d) => d.id),
      adopted: [],
      needs_confirmation: confirmOf(imp),
      warnings: [],
      notes: imp.some((i) => i.effect === "removed") ? [NOTE_ORPHAN] : [],
      impact: imp,
      excluded: [...after],
    });
  }

  if (detail && scope && p[8] === "destinations") {
    const cluster = p[9];
    const kind = p[10];
    const dest = detail.scopes.flatMap((s) => s.destinations).find((d) => d.id === cluster);
    const name = dest?.name ?? parts(cluster).name;
    if (kind === "values") {
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
    const deploy = body.deploy as Values | null;
    const keyOf: Record<string, string> = { target_revision: "targetRevision", repourl: "repourl", path: "path", project_namespace: "projectNamespace" };
    const changes: AdoptionChange[] = deploy
      ? Object.entries(deploy)
          .filter(([, v]) => v !== null)
          .map(([k, v]) => ({ stack: "deploy", key: keyOf[k] ?? k, before: null, after: v }))
      : Object.entries(dest?.own_deploy?.values ?? {}).map(([k, v]) => ({ stack: "deploy", key: k, before: v, after: null }));
    const own = dest?.own_folder ?? `sites/${dest?.site}/${dest?.env}/mces/${name}/in-cluster/${chart}`;
    return finish({
      team,
      action: "override-deploy",
      chart,
      scope,
      title: deploy
        ? `[Wingman/Day2] Override addon ${team}/${chart} deploy config on ${name} (fleet default on ${LABEL[scope]})`
        : `[Wingman/Day2] Override addon ${team}/${chart} deploy config on ${name}: back to the fleet default (fleet default on ${LABEL[scope]})`,
      files: deploy
        ? [
            file("create", `${own}/${chart}.yaml`, changes.map((c) => `${c.key}: ${String(c.after)}`).join("\n") + "\n", null),
            file("update", `defaults/${scope}/exclusions.yaml`, `${chart}:\n- ${name}\n`, `${chart}: []\n`),
          ]
        : [file("delete", `${own}/${chart}.yaml`, null, dest?.own_deploy?.text ?? "")],
      reach: [cluster],
      adopted: [],
      needs_confirmation: [cluster],
      warnings: [],
      notes: ["The Application keeps its name: both folders generate the same one, so ArgoCD keeps it."],
      impact: [impact(detail, cluster, "changed", changes)],
      excluded: [],
    });
  }

  // The 3.8 writes (create, team default, make default, fleet default), with 3.10's impact.
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
export interface OperatorRequests {
  writes: { method: string; path: string; dryRun: boolean; body: Values }[];
  previews: MergePreviewBody[];
}

const sorted = (ids: unknown) => (Array.isArray(ids) ? [...ids].map(String).sort() : []);

/**
 * Route the Operators reads (the list, one operator, merge-preview) and every
 * authoring write. Register after mockDay2World and mockAuthoring (route mocks
 * match last registered first). `planChangedOnce`: the repo moves before the
 * first real write, which answers 409 plan-changed.
 */
export async function mockOperators(
  page: Page,
  { teams, planChangedOnce = false }: { teams?: Team[]; planChangedOnce?: boolean } = {},
): Promise<OperatorRequests> {
  const seen: OperatorRequests = { writes: [], previews: [] };
  let version = 1;
  let moved = false;
  if (teams) await page.route("**/api/day2/teams", (r) => json(r, teams));
  await page.route(/\/api\/day2\/teams\/[^/?]+\/operators(\?.*)?$/, (r) =>
    json(r, operatorsOf(decodeURIComponent(new URL(r.request().url()).pathname.split("/")[4]))),
  );
  await page.route(/\/api\/day2\/teams\/[^/?]+\/operators\/[^/?]+(\?.*)?$/, (r) => {
    const p = new URL(r.request().url()).pathname.split("/").map(decodeURIComponent);
    const detail = operatorDetail(p[4], p[6]);
    if (!detail) return r.fulfill(problem(404, "NOT_FOUND", `${p[4]} has no operator ${p[6]}`));
    return json(r, detail);
  });
  await page.route("**/api/day2/merge-preview", (r) => {
    const body = r.request().postDataJSON() as MergePreviewBody;
    seen.previews.push(body);
    return json(r, operatorPreview(body));
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
    const plan = operatorPlan(method, url, body, version);
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
  await page.route(/\/api\/day2\/addons\/[^/?]+\/[^/?]+\/defaults\/[^/?]+\/exclusions(\?.*)?$/, write);
  await page.route(/\/api\/day2\/addons\/[^/?]+\/[^/?]+\/defaults\/[^/?]+\/destinations\/[^/?]+\/(values|deploy)(\?.*)?$/, write);
  return seen;
}
