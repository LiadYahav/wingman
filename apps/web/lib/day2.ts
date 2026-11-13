/**
 * The day2 service as the web app addresses it: paths, query keys, roles and
 * the problems its writes refuse with.
 *
 * A destination is addressed by its id (`hub`, `mce:<site>:<env>:<mce>`,
 * `hosted:<site>:<env>:<mce>:<cluster>`, `upi:<site>:<env>:<cluster>`) or by a
 * bare name that names exactly one destination, so links from the day1 pages
 * keep working (ADR-0020). `?mce=` narrows a bare name.
 */

import { AMBIGUOUS_WRITE_HINT, isAmbiguousWrite } from "@/lib/write-errors";
import type { CatalogEntry, DestinationKind, Finding, FleetScope, LayerRole, SyncSettings, Team } from "@/types/day2";

// ── Addressing ───────────────────────────────────────────────────────────────

export const KIND_LABEL: Record<DestinationKind, string> = {
  hub: "Hub",
  mce: "MCE",
  hosted: "Hosted",
  upi: "UPI",
};

/** True for an id; false for a bare name the service has to resolve. */
export function isDestinationId(key: string): boolean {
  return key === "hub" || key.includes(":");
}

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) search.set(k, v);
  const s = search.toString();
  return s ? `?${s}` : "";
}

/** `mce` only narrows a bare name; with an id it is noise. */
function narrow(key: string, mce?: string): string | undefined {
  return mce && !isDestinationId(key) ? mce : undefined;
}

const cluster = (key: string) => `/api/day2/clusters/${encodeURIComponent(key)}`;
const addon = (team: string, chart: string) =>
  `/api/day2/addons/${encodeURIComponent(team)}/${encodeURIComponent(chart)}`;
/** `?dry_run=true`: every check, nothing opened, the plan back (ADR-0043). */
const dry = (dryRun: boolean) => query({ dry_run: dryRun ? "true" : undefined });

export const day2Api = {
  catalog: "/api/day2/addons",
  /** The chart's own `values.yaml` at a chart repo branch (`HEAD` when omitted). */
  chartDefaults: (team: string, chart: string, version?: string) =>
    `/api/day2/addons/${encodeURIComponent(team)}/${encodeURIComponent(chart)}/values${query({ version })}`,
  gitlabInfo: "/api/day2/gitlab-info",
  mergePreview: "/api/day2/merge-preview",
  destinations: "/api/day2/clusters",
  lints: (team?: string) => `/api/day2/lints${query({ team })}`,
  destination: (key: string, mce?: string) => `${cluster(key)}${query({ mce: narrow(key, mce) })}`,
  charts: (key: string, mce?: string) => `${cluster(key)}/addons${query({ mce: narrow(key, mce) })}`,
  chart: (id: string, team: string, chart: string, version?: string) =>
    `${cluster(id)}/addons/${encodeURIComponent(team)}/${encodeURIComponent(chart)}${query({ version })}`,
  remove: (id: string, team: string, chart: string, lastCommitId?: string | null) =>
    `${cluster(id)}/addons/${encodeURIComponent(team)}/${encodeURIComponent(chart)}${query({
      last_commit_id: lastCommitId ?? undefined,
    })}`,
  bulk: (id: string) => `${cluster(id)}/addons/bulk`,
  history: (key: string, mce?: string) => `${cluster(key)}/history${query({ mce: narrow(key, mce) })}`,
  upgradeCheck: (id: string, to: string) => `${cluster(id)}/upgrade-check${query({ to })}`,
  teams: "/api/day2/teams",
  team: (team: string) => `/api/day2/teams/${encodeURIComponent(team)}`,
  /** What the New add-on form of a team starts from. */
  addonTemplate: (team: string) => `/api/day2/teams/${encodeURIComponent(team)}/addon-template`,
  fleetDefaults: (team?: string) => `/api/day2/fleet-defaults${query({ team })}`,
  /** POST: a new add-on in the team's catalog. */
  createAddon: (team: string, dryRun = false) => `/api/day2/addons/${encodeURIComponent(team)}${dry(dryRun)}`,
  /** PUT: Edit add-on, its deploy config and Sig values (the API's team default). */
  editAddon: (team: string, chart: string, dryRun = false) => `${addon(team, chart)}${dry(dryRun)}`,
  /** POST: make it a fleet default; PUT: edit that fleet default. */
  fleetDefault: (team: string, chart: string, scope: FleetScope, dryRun = false) =>
    `${addon(team, chart)}/defaults/${encodeURIComponent(scope)}${dry(dryRun)}`,
  /** A team's add-ons: its catalog and the fleet defaults built from it (ADR-0053). */
  teamAddons: (team: string) => `/api/day2/teams/${encodeURIComponent(team)}/addons`,
  /** One add-on: its files, OCP-version pins and one panel per fleet scope. */
  addonDetail: (team: string, chart: string) =>
    `/api/day2/teams/${encodeURIComponent(team)}/addons/${encodeURIComponent(chart)}`,
  /** PUT: one destination's `values-<name>.yaml` of a fleet default. */
  destinationValues: (team: string, chart: string, scope: FleetScope, cluster: string, dryRun = false) =>
    `${addon(team, chart)}/defaults/${encodeURIComponent(scope)}/destinations/${encodeURIComponent(cluster)}/values${dry(dryRun)}`,
  /** PUT: one env's `values-<env>.yaml` of a fleet default. */
  envValues: (team: string, chart: string, scope: FleetScope, env: string, dryRun = false) =>
    `${addon(team, chart)}/defaults/${encodeURIComponent(scope)}/envs/${encodeURIComponent(env)}/values${dry(dryRun)}`,
  /** POST: deploy the add-on on specific MCEs, one install MR per MCE (ADR-0053's amendment). */
  mceInstalls: (team: string, chart: string, dryRun = false) => `${addon(team, chart)}/mce-installs${dry(dryRun)}`,
};

/**
 * Query keys, all under `day2`, for the day2 pages and the day1 pages alike:
 * a day1 page that prefetches a destination's charts fills the entry its
 * charts page reads.
 */
export const day2Keys = {
  catalog: ["day2", "catalog"] as const,
  chartDefaults: (team: string, chart: string, version: string) =>
    ["day2", "chart-defaults", team, chart, version] as const,
  gitlabInfo: ["day2", "gitlab-info"] as const,
  destinations: ["day2", "destinations"] as const,
  lints: ["day2", "lints"] as const,
  charts: (key: string, mce?: string) => ["day2", "charts", key, narrow(key, mce) ?? ""] as const,
  history: (key: string, mce?: string) => ["day2", "history", key, narrow(key, mce) ?? ""] as const,
  preview: (id: string, team: string, chart: string, version: string, draft: string | null) =>
    ["day2", "preview", id, team, chart, version, draft] as const,
  upgradeCheck: (id: string, to: string) => ["day2", "upgrade-check", id, to] as const,
  teams: ["day2", "teams"] as const,
  addonTemplate: (team: string) => ["day2", "addon-template", team] as const,
  fleetDefaults: ["day2", "fleet-defaults"] as const,
  teamAddons: (team: string) => ["day2", "team-addons", team] as const,
  addonDetail: (team: string, chart: string) => ["day2", "team-addons", team, chart] as const,
  /** `merge-preview` of a destination with `override` (stable JSON) as `path` (its own file when `""`), or without one (`null`). */
  mergePreview: (id: string, team: string, chart: string, override: string | null, path = "") =>
    ["day2", "merge-preview", id, team, chart, override, path] as const,
};

/** The web page of a destination's charts. */
export function chartsHref(key: string, mce?: string): string {
  return `/clusters/${encodeURIComponent(key)}/addons${query({ mce: narrow(key, mce) })}`;
}

/**
 * The Addons pages (ADR-0053): the catalog, one team's part of it (`?team=`),
 * one add-on with its defaults and overrides, and a new add-on's form
 * (`/addons/new?team=`: a query, so an add-on may be named `new`).
 */
export function teamAddonsHref(team: string): string {
  return `/addons${query({ team })}`;
}

export function addonHref(team: string, chart: string): string {
  return `/addons/${encodeURIComponent(team)}/${encodeURIComponent(chart)}`;
}

export function newAddonHref(team: string): string {
  return `/addons/new${query({ team })}`;
}

// ── Catalog ──────────────────────────────────────────────────────────────────

/**
 * The revisions a chart can be asked for: the add-on's first (`HEAD`, the
 * chart repo's default branch, when the add-on sets none), then the
 * branches, default branch first. `also` keeps a revision already chosen
 * (a spec's) on the list, last, when the repo no longer has it.
 */
export function chartRevisions(
  entry: Pick<CatalogEntry, "current_version" | "available_versions"> | undefined,
  also?: string,
): string[] {
  const revisions = [entry?.current_version, ...(entry?.available_versions ?? []), also];
  return [...new Set(revisions.filter((v): v is string => Boolean(v)))];
}

/** A route param back to the key (Next may or may not have decoded it). */
export function keyFromParam(param: string): string {
  try {
    return decodeURIComponent(param);
  } catch {
    return param;
  }
}

// ── Layer roles (ADR-0021) ───────────────────────────────────────────────────

export interface RoleStyle {
  label: string;
  description: string;
  /** Tailwind classes for the chip: a tint and readable text. */
  chip: string;
  /** Tailwind class for a row's left edge. */
  edge: string;
}

const ORIGIN = {
  chip: "bg-muted text-muted-foreground border-border",
  edge: "border-l-transparent",
};
const TEAM = {
  chip: "bg-status-ready/12 text-status-ready-fg border-status-ready/25",
  edge: "border-l-status-ready/60",
};
const PLACE = {
  chip: "bg-status-provisioning/12 text-status-provisioning-fg border-status-provisioning/25",
  edge: "border-l-status-provisioning/60",
};
const FLEET = {
  chip: "bg-chart-5/12 text-chart-5 border-chart-5/25",
  edge: "border-l-chart-5/60",
};
const OWN = {
  chip: "bg-primary/12 text-primary border-primary/30",
  edge: "border-l-primary",
};

const ROLES: Record<string, RoleStyle> = {
  chart: { label: "chart", description: "The chart's own values.yaml", ...ORIGIN },
  hub: { label: "hub", description: "Every chart on the hub", ...PLACE },
  // The day2 role `team` is the user's Sig values (ADR-0043's amendment); the API name stays.
  team: { label: "sig values", description: "The Sig values (operators/<chart>/values.yaml)", ...TEAM },
  "team-ocp-version": {
    label: "sig values · ocp",
    description: "The Sig values for this OCP version (operators/<chart>/ocp-versions/<v>/)",
    ...TEAM,
  },
  site: { label: "site", description: "Every chart of the team on the site", ...PLACE },
  "site-env": { label: "site · env", description: "Every chart of the team in the site's env", ...PLACE },
  fleet: { label: "fleet", description: "The fleet default (defaults/<scope>/<chart>/values.yaml)", ...FLEET },
  "fleet-env": { label: "fleet · env", description: "The fleet default for the env", ...FLEET },
  "fleet-target": {
    label: "fleet · this cluster",
    description: "The fleet default's file for this cluster (values-<cluster>.yaml)",
    ...FLEET,
  },
  mce: { label: "mce", description: "Every chart of the team on the MCE's clusters", ...PLACE },
  "upi-wide": { label: "upi-wide", description: "Every chart of the team on UPI clusters", ...PLACE },
  "cluster-wide": { label: "cluster-wide", description: "Every chart of the team on this cluster", ...PLACE },
  cluster: { label: "cluster", description: "This chart on this cluster (its folder's values.yaml)", ...OWN },
};

/** How a layer role looks; an unknown role is shown as-is, never hidden. */
export function roleStyle(role: LayerRole | undefined): RoleStyle {
  if (!role) return { label: "unknown", description: "The service did not say which layer set this", ...ORIGIN };
  return ROLES[role] ?? { label: role, description: `Layer "${role}"`, ...ORIGIN };
}

// ── Findings ─────────────────────────────────────────────────────────────────

const SEVERITY_ORDER: Record<string, number> = { error: 0, warning: 1, info: 2 };

export function bySeverity(a: Finding, b: Finding): number {
  return (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3);
}

export function worstSeverity(findings: readonly Finding[]): Finding["severity"] | undefined {
  return [...findings].sort(bySeverity)[0]?.severity;
}

/** The same finding can be reported on a chart and on its cluster; show it once. */
export function uniqueFindings(findings: readonly Finding[]): Finding[] {
  const seen = new Set<string>();
  return findings.filter((f) => {
    const key = `${f.rule}|${f.path}|${f.message}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// ── Problems (RFC 9457, ADR-0004) ────────────────────────────────────────────

/**
 * What a refused request says, read from whatever `lib/api-client` threw:
 * the members the day2 pages act on, not the whole RFC 9457 document
 * (`Problem` in types/problem.ts).
 */
export interface ProblemSummary {
  status?: number;
  code?: string;
  detail: string;
  details: Record<string, unknown>;
  requestId?: string;
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : undefined;
}

/**
 * The problem behind a thrown error. Reads the RFC 9457 members (`status`,
 * `code`, `detail`, `details`, `request_id`) from the error itself or from a
 * `problem`/`body` member on it, so it works with any client that keeps them;
 * a plain `Error` gives just its message.
 */
export function problemOf(error: unknown): ProblemSummary {
  const outer = record(error) ?? {};
  const doc = record(outer.problem) ?? record(outer.body) ?? outer;
  const pick = (key: string) => doc[key] ?? outer[key];
  const status = pick("status");
  const code = pick("code");
  const detail = pick("detail");
  const requestId = pick("request_id") ?? pick("requestId");
  return {
    status: typeof status === "number" ? status : undefined,
    code: typeof code === "string" ? code : undefined,
    detail:
      typeof detail === "string" && detail
        ? detail
        : error instanceof Error
          ? error.message
          : String(error),
    details: record(pick("details")) ?? {},
    requestId: typeof requestId === "string" ? requestId : undefined,
  };
}

/** A stale `last_commit_id`: someone changed the file since it was read. */
export function isRevisionConflict(problem: ProblemSummary): boolean {
  return problem.code === "REVISION_CONFLICT";
}

/** `details.candidates` of an ambiguous bare name: the ids it could mean. */
export function candidatesOf(problem: ProblemSummary): string[] {
  const candidates = problem.details.candidates;
  return Array.isArray(candidates) ? candidates.filter((c): c is string => typeof c === "string") : [];
}

/** One item a bulk install refused (`details.problems`). */
export interface BulkProblem {
  team: string;
  chart: string;
  detail: string;
}

export function bulkProblemsOf(problem: ProblemSummary): BulkProblem[] {
  const items = problem.details.problems;
  if (!Array.isArray(items)) return [];
  return items.map((item) => {
    const r = record(item) ?? {};
    return { team: String(r.team ?? ""), chart: String(r.chart ?? ""), detail: String(r.detail ?? "") };
  });
}

/** The sentence to show for a refused write; an unconfirmed one says it may have happened. */
export function writeErrorMessage(problem: ProblemSummary): string {
  return isAmbiguousWrite(problem) ? `${AMBIGUOUS_WRITE_HINT} ${problem.detail}` : problem.detail;
}

/** A team's write access refused the request (ADR-0043): its detail is the reason to show. */
export function isTeamReadOnly(problem: ProblemSummary): boolean {
  return problem.code === "TEAM_READ_ONLY";
}

/**
 * The repo moved since the preview, so the plan is no longer the one the user
 * saw (`409 REVISION_CONFLICT`, `details.rule = "plan-changed"`, ADR-0053):
 * nothing was opened. Preview again and show the new plan; never submit it unseen.
 */
export function isPlanChanged(problem: ProblemSummary): boolean {
  return problem.code === "REVISION_CONFLICT" && problem.details.rule === "plan-changed";
}

// ── Teams and write access (ADR-0043) ────────────────────────────────────────

export interface TeamAccess {
  writable: boolean;
  /** Why not, as a sentence to show; `null` when writable. */
  reason: string | null;
  /** False while there is no teams list (not answered yet, or failed). */
  known: boolean;
}

/**
 * Whether the web may offer writes to `team`, and why not. Fails closed: a
 * team the list does not have (not loaded yet, failed, or missing) is not
 * writable, and neither is one whose access the service could not read
 * (`access_role: "unknown"`). The service refuses a read-only team's write
 * anyway; the page says why before anyone tries.
 */
export function teamAccess(teams: readonly Team[] | undefined, team: string): TeamAccess {
  const found = teams?.find((t) => t.name === team);
  if (!found) return { writable: false, reason: `Wingman could not read ${team}'s write access yet.`, known: teams !== undefined };
  if (found.writable && found.access_role !== "unknown") return { writable: true, reason: null, known: true };
  return { writable: false, reason: found.read_only_reason ?? `${team} is read-only in Wingman.`, known: true };
}

// ── Fleet scopes and sync options (ADR-0043) ─────────────────────────────────

export const FLEET_SCOPES: readonly FleetScope[] = ["hosted-clusters", "mces", "hub", "upi"];

/** How a scope reads in a sentence ("a default on every hosted cluster"). */
export const SCOPE_LABEL: Record<FleetScope, string> = {
  "hosted-clusters": "every hosted cluster",
  mces: "every MCE",
  hub: "the hub",
  upi: "every UPI cluster",
};

export function scopeLabel(scope: string): string {
  return SCOPE_LABEL[scope as FleetScope] ?? scope;
}

/** A sync option is `Name=value` (the service refuses anything else, rule `sync-option-invalid`). */
export const SYNC_OPTION_PATTERN = /^[A-Za-z][A-Za-z0-9]*=[A-Za-z0-9._-]+$/;

/** The platform's default for a leaf app: manual sync, the namespace created. */
export const DEFAULT_SYNC: SyncSettings = { auto_sync: false, prune: false, self_heal: false, sync_options: ["CreateNamespace=true"] };

export function sameSync(a: SyncSettings, b: SyncSettings): boolean {
  return (
    a.auto_sync === b.auto_sync &&
    a.prune === b.prune &&
    a.self_heal === b.self_heal &&
    a.sync_options.length === b.sync_options.length &&
    a.sync_options.every((o, i) => o === b.sync_options[i])
  );
}

/** One line: "manual sync · CreateNamespace=true" or "auto-sync (prune, self-heal) · none". */
export function syncSummary(sync: SyncSettings): string {
  const flags = [sync.prune && "prune", sync.self_heal && "self-heal"].filter(Boolean).join(", ");
  const mode = sync.auto_sync ? `auto-sync${flags ? ` (${flags})` : ""}` : "manual sync";
  return `${mode} · ${sync.sync_options.length > 0 ? sync.sync_options.join(", ") : "no sync options"}`;
}
