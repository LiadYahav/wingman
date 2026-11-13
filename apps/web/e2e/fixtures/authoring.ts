import type { Page } from "@playwright/test";
import { json } from "./api-handlers";
import { HOSTED_ID, HOSTED_NAME, MCE_ID, TWIN_IDS } from "./day2";
import type {
  AddonTemplate,
  Adoption,
  AuthoringChange,
  AuthoringPlan,
  DestinationImpact,
  FleetDefault,
  FleetScope,
  PlannedFileChange,
  SyncSettings,
  Team,
} from "../../types/day2";

/**
 * Add-on authoring and per-team write access (ADR-0043), shaped like the
 * service's answers (docs/notes/2026-11-12-day2-addon-authoring-api.md), on
 * top of the day2 world of fixtures/day2.ts: the same teams, catalog and
 * destinations. `security` is read-only: Wingman's account is a Reporter there.
 */

export const READ_ONLY_REASON =
  "security hasn't given Wingman write access to sigs/security: Wingman's GitLab account is a Reporter there, and opening a merge request needs Developer or higher. A maintainer of sigs/security turns writes on by adding the account to the project as a Developer.";

export const MANUAL: SyncSettings = { auto_sync: false, prune: false, self_heal: false, sync_options: ["CreateNamespace=true"] };

const KNOWN_SYNC_OPTIONS = [
  "CreateNamespace=true",
  "ServerSideApply=true",
  "PruneLast=true",
  "ApplyOutOfSyncOnly=true",
  "RespectIgnoreDifferences=true",
  "Replace=true",
  "Validate=false",
  "SkipDryRunOnMissingResource=true",
  "FailOnSharedResource=true",
  "PrunePropagationPolicy=foreground",
  "PrunePropagationPolicy=background",
  "PrunePropagationPolicy=orphan",
];

function team(name: string, id: number, level = 30): Team {
  const writable = level >= 30;
  const roles: Record<number, string> = { 0: "none", 10: "guest", 20: "reporter", 30: "developer", 40: "maintainer", 50: "owner" };
  return {
    name,
    project_id: id,
    path_with_namespace: `sigs/${name}`,
    web_url: `https://gitlab.example.com/sigs/${name}`,
    writable,
    access_level: level,
    access_role: roles[level] ?? "none",
    read_only_reason: writable ? null : READ_ONLY_REASON,
  };
}

export const TEAMS: Team[] = [
  team("networking", 4),
  team("observability", 3, 40),
  team("platform", 2),
  team("security", 5, 20),
];

const UPI_ID = "upi:site2:prep:ocp4-dok-site2";

const SCOPES: AddonTemplate["scopes"] = [
  { scope: "hosted-clusters", label: "every hosted cluster", destinations: [HOSTED_ID, ...TWIN_IDS] },
  { scope: "mces", label: "every MCE", destinations: [MCE_ID] },
  { scope: "hub", label: "the hub", destinations: ["hub"] },
  { scope: "upi", label: "every UPI cluster", destinations: [UPI_ID] },
];

function template(name: string): AddonTemplate {
  const found = TEAMS.find((t) => t.name === name);
  return {
    team: name,
    writable: found?.writable ?? true,
    read_only_reason: found?.read_only_reason ?? null,
    sync: MANUAL,
    sync_source: `the sync options most of sigs/${name}'s add-ons use (2 of 2)`,
    repourl_prefix: "https://gitlab.example.com/helm-charts/",
    known_sync_options: KNOWN_SYNC_OPTIONS,
    scopes: SCOPES,
  };
}

function fleetDefault(overrides: Partial<FleetDefault> & Pick<FleetDefault, "team" | "chart" | "scope">): FleetDefault {
  const scope = SCOPES.find((s) => s.scope === overrides.scope);
  const access = TEAMS.find((t) => t.name === overrides.team);
  return {
    scope_label: scope?.label ?? overrides.scope,
    path: `defaults/${overrides.scope}/${overrides.chart}`,
    in_catalog: true,
    values: {},
    values_exists: true,
    sync: MANUAL,
    sync_overridden: false,
    reach: scope?.destinations ?? [],
    excluded: [],
    tweaks: [],
    last_commit_id: `${overrides.team}-fleet-1`,
    writable: access?.writable ?? true,
    read_only_reason: access?.read_only_reason ?? null,
    warnings: [],
    ...overrides,
  };
}

export const FLEET_DEFAULTS: FleetDefault[] = [
  fleetDefault({
    team: "platform",
    chart: "external-secrets",
    scope: "hosted-clusters",
    values: { replicaCount: 2 },
    sync: { auto_sync: true, prune: false, self_heal: true, sync_options: ["CreateNamespace=true"] },
    sync_overridden: true,
    tweaks: [`defaults/hosted-clusters/external-secrets/values-${HOSTED_NAME}.yaml`],
  }),
  fleetDefault({
    team: "observability",
    chart: "grafana",
    scope: "hosted-clusters",
    reach: TWIN_IDS,
    excluded: [HOSTED_ID],
  }),
  fleetDefault({ team: "security", chart: "kyverno", scope: "mces" }),
  // A fleet default whose chart is not in the catalog (no operators/node-tuning/).
  fleetDefault({ team: "platform", chart: "node-tuning", scope: "upi", in_catalog: false }),
];

/** The cluster the make-default plan moves into the default with a change, and one it moves unchanged. */
const ADOPTED: Adoption[] = [
  {
    cluster: HOSTED_ID,
    name: HOSTED_NAME,
    moved: [
      {
        from: `sites/site1/prod/mces/mce-a/${HOSTED_NAME}/cert-manager/values.yaml`,
        to: `defaults/hosted-clusters/cert-manager/values-${HOSTED_NAME}.yaml`,
      },
    ],
    deleted: [`sites/site1/prod/mces/mce-a/${HOSTED_NAME}/cert-manager/cert-manager.yaml`],
    gitkeep: null,
    changes: [{ stack: "deploy", key: "projectNamespace", before: "certs", after: "cert-manager" }],
  },
  {
    cluster: TWIN_IDS[0],
    name: "twin",
    moved: [],
    deleted: ["sites/site1/prod/mces/mce-a/twin/cert-manager/values.yaml"],
    gitkeep: "sites/site1/prod/mces/mce-a/twin/.gitkeep",
    changes: [],
  },
];

export const AUTHORING_NOTE = "After the merge, ArgoCD generates the apps, which are manual-sync: nothing is deployed until someone syncs them.";

function file(action: PlannedFileChange["action"], path: string, content: string | null, previous: string | null): PlannedFileChange {
  return { action, path, content, previous };
}

/** The plan the service answers a dry run with, for the request at `url`. */
export function planFor(method: string, url: URL, body: Record<string, unknown>): AuthoringPlan {
  const parts = url.pathname.split("/").map(decodeURIComponent);
  const [teamName, chart, , scope] = [parts[4], parts[5], parts[6], parts[7]];
  const base = {
    team: teamName,
    warnings: [],
    notes: [AUTHORING_NOTE],
    adopted: [] as Adoption[],
    needs_confirmation: [] as string[],
    impact: [] as DestinationImpact[],
    excluded: [] as string[],
    digest: `digest-${method}-${url.pathname}`,
  };
  if (method === "POST" && parts.length === 5) {
    const name = String(body.name);
    const defaultScope = (body.default_scope as FleetScope | null) ?? null;
    const files = [
      file("create", `operators/${name}/${name}.yaml`, `repourl: ${String(body.repourl)}\nprojectNamespace: ${name}\n`, null),
      file("create", `operators/${name}/values.yaml`, "{}\n", null),
    ];
    if (defaultScope) files.push(file("create", `defaults/${defaultScope}/${name}/values.yaml`, "{}\n", null));
    return {
      ...base,
      action: "create-addon",
      chart: name,
      scope: defaultScope,
      title: `[Wingman/Day2] Create addon ${teamName}/${name} in the team catalog`,
      files,
      reach: defaultScope ? (SCOPES.find((s) => s.scope === defaultScope)?.destinations ?? []) : [],
    };
  }
  if (scope && method === "POST") {
    return {
      ...base,
      action: "make-default",
      chart,
      scope: scope as FleetScope,
      title: `[Wingman/Day2] Promote addon ${teamName}/${chart} to a fleet default on every hosted cluster`,
      files: [
        file("create", `defaults/${scope}/${chart}/values.yaml`, "{}\n", null),
        file("delete", ADOPTED[0].deleted[0], null, "projectNamespace: certs\n"),
        file("create", ADOPTED[0].moved[0].to, "replicas: 2\n", null),
      ],
      reach: SCOPES.find((s) => s.scope === scope)?.destinations ?? [],
      adopted: ADOPTED,
      needs_confirmation: [HOSTED_ID],
    };
  }
  if (scope) {
    return {
      ...base,
      action: "update-fleet-default",
      chart,
      scope: scope as FleetScope,
      title: `[Wingman/Day2] Update addon ${teamName}/${chart} fleet default on every hosted cluster`,
      files: [file("update", `defaults/${scope}/${chart}/${chart}.yaml`, "projectNamespace: eso\n", "projectNamespace: eso\nsyncPolicy:\n  automated:\n    selfHeal: true\n")],
      reach: SCOPES.find((s) => s.scope === scope)?.destinations ?? [],
    };
  }
  return {
    ...base,
    action: "update-team-default",
    chart,
    scope: null,
    title: `[Wingman/Day2] Update addon ${teamName}/${chart} Sig values`,
    files: [
      file(
        "update",
        `operators/${chart}/${chart}.yaml`,
        "# the team default\nrepourl: https://gitlab.example.com/helm-charts/prometheus.git\nsyncPolicy:\n  automated:\n    prune: false\n    selfHeal: true\n  syncOptions:\n  - CreateNamespace=true\n",
        "# the team default\nrepourl: https://gitlab.example.com/helm-charts/prometheus.git\nsyncPolicy:\n  syncOptions:\n  - CreateNamespace=true\n",
      ),
    ],
    reach: [HOSTED_ID],
  };
}

let iid = 80;

export function changeOf(plan: AuthoringPlan): AuthoringChange {
  iid += 1;
  return {
    iid,
    title: plan.title,
    description: "",
    author: { username: "test-admin", name: "", avatar_url: null },
    state: "opened",
    created_at: "2026-11-12T10:00:00+00:00",
    updated_at: "2026-11-12T10:00:00+00:00",
    web_url: `https://gitlab.example.com/sigs/${plan.team}/-/merge_requests/${iid}`,
    source_branch: `platform/test-admin/${plan.action}-${plan.chart}`,
    target_branch: "main",
    labels: ["wingman", "day2", plan.action],
    repo: "day2",
    has_conflicts: null,
    team: plan.team,
    project_id: 2,
    sha: "abcdef1234567890",
    gitlab_author: "wingman-bot",
    action: plan.action,
    chart: plan.chart,
    scope: plan.scope,
    files: plan.files.map((f) => ({ action: f.action, path: f.path })),
    reach: plan.reach,
    adopted: plan.adopted,
    warnings: plan.warnings,
    notes: plan.notes,
  };
}

/**
 * Route the teams, the New add-on template and the fleet defaults. Register
 * after mockDay2World (route mocks match last registered first); the writes,
 * with their plans (`planFor`, here), are routed by mockAddonDetail
 * (fixtures/addon-detail.ts), which also checks what a real write confirms.
 */
export async function mockAuthoring(page: Page, { teams = TEAMS }: { teams?: Team[] } = {}): Promise<void> {
  await page.route("**/api/day2/teams", (r) => json(r, teams));
  await page.route(/\/api\/day2\/teams\/[^/?]+\/addon-template$/, (r) =>
    json(r, template(decodeURIComponent(new URL(r.request().url()).pathname.split("/")[4]))),
  );
  await page.route("**/api/day2/fleet-defaults**", (r) => json(r, FLEET_DEFAULTS));
}
