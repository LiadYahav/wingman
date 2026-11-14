/**
 * A server's History, as server-scan's server page shows it
 * (docs/notes/2026-11-13-server-scan-area-api.md §9.1): one sentence per
 * audit event from the `data` its writer records, a health change's reasons
 * on each side, a classification's matched rule, the data without legacy
 * keys, each type's tint, and the pages.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/features/events/describeEvent.ts`,
 * `EventTimeline.tsx` (the tints) and `EventList.tsx` (the pager).
 */

import type { AuditEvent, AuditEventPage } from "@/types/server-scan-record";
import { actorLabel } from "./actor";
import { isDonor } from "./rows";
import { SEVERITY_ORDER } from "./vocabulary";

/** The `event_type`s server-scan writes, in its filter menu's order. */
export const WRITTEN_EVENT_TYPES = [
  "SERVER_CREATED", "SERVER_RENAMED", "SERVER_PRUNED", "HEALTH_CHANGED", "CLASSIFICATION_CHANGED", "OPENSHIFT_STATE_CHANGED",
  "MAINTENANCE_ENABLED", "MAINTENANCE_UPDATED", "MAINTENANCE_DISABLED", "SERVER_RESERVED", "SERVER_RESERVATION_REFUSED",
  "SERVER_RELEASED", "IDRAC_RESET", "AUDIT_PURGED", "LOGIN_SUCCEEDED", "LOGIN_DENIED", "TOKEN_CREATED", "TOKEN_REVOKED",
  "JOB_TRIGGERED",
] as const;

function str(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function count(value: unknown): string {
  return typeof value === "number" ? String(value) : "?";
}

/** " (x)" for a non-empty string, else "". */
function paren(value: unknown): string {
  const s = str(value);
  return s ? ` (${s})` : "";
}

function change(label: string, data: Record<string, unknown>): string {
  return `${label} ${str(data.from) ?? "?"} -> ${str(data.to) ?? "?"}`;
}

const RESET_TRIGGER: Record<string, string> = { disks: "every disk", nics: "every NIC", both: "every disk and every NIC" };

/** An IDRAC_RESET: what triggered it and how the restart went. */
function idracReset(d: Record<string, unknown>): string {
  const why = `${RESET_TRIGGER[str(d.trigger) ?? ""] ?? "disks or NICs"} UNKNOWN`;
  const detail = str(d.detail);
  const before = str(d.power_state);
  const on = d.powered_on === true ? "Host was off: powered on, then " : before === "On" ? "Host was already on: only the " : "";
  switch (str(d.outcome)) {
    case "requested":
      return `${on}iDRAC restart requested: ${why}`;
    case "unconfirmed":
      return `${on}iDRAC restart sent, no reply (the iDRAC dropped the connection): ${why}`;
    default:
      if (d.powered_on === true && !detail?.includes("maintenance")) {
        return `Host was off: power-on sent, iDRAC not restarted${detail ? ` (${detail})` : ""}: ${why}`;
      }
      return `${on}iDRAC restart failed${detail ? ` (${detail})` : ""}: ${why}`;
  }
}

export interface EventReason {
  policy_key: string | null;
  policy_name: string | null;
  category: string | null;
  severity: string | null;
  message: string | null;
}

/** `data[key]` as reasons, or null when it is not a list (that side was not recorded). */
function reasonsAt(data: Record<string, unknown>, key: string): EventReason[] | null {
  const v = data[key];
  if (!Array.isArray(v)) return null;
  return v
    .filter((x): x is Record<string, unknown> => typeof x === "object" && x !== null)
    .map((r) => ({
      policy_key: str(r.policy_key),
      policy_name: str(r.policy_name),
      category: str(r.category),
      severity: str(r.severity),
      message: str(r.message),
    }));
}

/** The reasons behind each side of a HEALTH_CHANGED; older events carried only `reasons` (the TO side). */
export function healthSections(data: Record<string, unknown>): { from: EventReason[] | null; to: EventReason[] | null } {
  return { from: reasonsAt(data, "from_reasons"), to: reasonsAt(data, "to_reasons") ?? reasonsAt(data, "reasons") };
}

/** The most severe reason; on a tie, the first recorded. `null` when there is none. */
export function topReason(reasons: EventReason[]): EventReason | null {
  const rank = (r: EventReason): number => {
    const i = SEVERITY_ORDER.findIndex((s) => s === r.severity);
    return i === -1 ? SEVERITY_ORDER.length : i;
  };
  let best: EventReason | null = null;
  for (const r of reasons) if (best === null || rank(r) < rank(best)) best = r;
  return best;
}

/** "FROM → TO" for a status change; "?" for a missing side. */
export function transition(d: Record<string, unknown>): string {
  return `${str(d.from) ?? "?"} → ${str(d.to) ?? "?"}`;
}

/** Both sides of a status change, or `null` for an event that has none. */
export function transitionSides(d: Record<string, unknown>): [from: string, to: string] | null {
  return typeof d.from === "string" && typeof d.to === "string" ? [d.from || "?", d.to || "?"] : null;
}

function maintenanceSentence(event: AuditEvent): string {
  const reason = str(event.data.reason);
  const prefix = event.event_type === "MAINTENANCE_ENABLED" ? "Put into" : "Updated";
  const by = ` by ${actorLabel(event.actor).label}`;
  if (isDonor({ enabled: true, reason })) return `Marked as parts donor${by}: ${reason ?? ""}`;
  return `${prefix} maintenance${by}${reason ? `: ${reason}` : ""}`;
}

function reservationRefused(d: Record<string, unknown>): string {
  const why = str(d.reason) ?? (str(d.held_by) ? `held by ${str(d.held_by)}` : null);
  return `Reservation by ${str(d.requested_by) ?? "?"} refused${why ? `: ${why}` : ""}`;
}

function classificationChanged(d: Record<string, unknown>): string {
  const renamed = str(d.name_from) && str(d.name_to) ? ` (renamed ${str(d.name_from)} -> ${str(d.name_to)})` : "";
  return `${change("Classification", d)}${renamed}`;
}

type Sentence = (event: AuditEvent, d: Record<string, unknown>) => string;

/** Each written type's sentence, from the keys its writer records. */
const SENTENCES: Record<string, Sentence> = {
  SERVER_CREATED: () => "Server discovered",
  SERVER_RENAMED: (_, d) => `Renamed ${str(d.name_from) ?? "?"} → ${str(d.name_to) ?? "?"}`,
  SERVER_PRUNED: () => "Pruned: no longer listed by its manager",
  LOGIN_SUCCEEDED: (_, d) => `Logged in as ${str(d.role)?.toLowerCase() ?? "?"}`,
  LOGIN_DENIED: () => "Login refused: authenticated, but in no admin, auditor or viewer list",
  TOKEN_CREATED: (_, d) =>
    `Created a personal API token (${str(d.role)?.toLowerCase() ?? "?"}, expires ${str(d.expires_at)?.slice(0, 10) ?? "?"})`,
  TOKEN_REVOKED: (_, d) =>
    d.by_admin === true ? `Personal API token of ${str(d.user) ?? "?"} revoked by an admin` : "Revoked their personal API token",
  JOB_TRIGGERED: (_, d) => `Ran CronJob ${str(d.cronjob) ?? "?"} by hand as Job ${str(d.job) ?? "?"}`,
  AUDIT_PURGED: (_, d) => `Purged ${count(d.deleted)} audit events older than ${count(d.retention_days)} days`,
  HEALTH_CHANGED: (_, d) => transition(d),
  CLASSIFICATION_CHANGED: (_, d) => classificationChanged(d),
  IDRAC_RESET: (_, d) => idracReset(d),
  OPENSHIFT_STATE_CHANGED: (_, d) => `${change("OpenShift state", d)}${paren(d.cluster_name)}`,
  MAINTENANCE_ENABLED: (event) => maintenanceSentence(event),
  MAINTENANCE_UPDATED: (event) => maintenanceSentence(event),
  MAINTENANCE_DISABLED: () => "Maintenance ended",
  SERVER_RESERVED: (_, d) => `Reserved by ${str(d.holder) ?? "?"}${str(d.mce_cluster) ? ` for ${str(d.mce_cluster)}` : ""}`,
  SERVER_RESERVATION_REFUSED: (_, d) => reservationRefused(d),
  SERVER_RELEASED: (_, d) => `Released from ${str(d.holder) ?? "?"}${paren(d.mce_cluster)}`,
};

/** One sentence for an audit event (with who, for maintenance); a type it does not know is its name. */
export function describeEvent(event: AuditEvent): string {
  const sentence = SENTENCES[event.event_type];
  return sentence ? sentence(event, event.data) : event.event_type;
}

const LEGACY_DATA_KEYS = ["ticket", "matched_rule_id"];

/** The event's data without legacy keys (a removed ticket, an internal rule id); the event is untouched. */
export function visibleData(event: AuditEvent): Record<string, unknown> {
  return Object.fromEntries(Object.entries(event.data).filter(([k]) => !LEGACY_DATA_KEYS.includes(k)));
}

/** A CLASSIFICATION_CHANGED's rule, readable; `null` for a legacy or unmatched one. */
export function matchedRule(data: Record<string, unknown>): { name: string; on: string | null } | null {
  const name = str(data.matched_rule);
  if (name === null) return null;
  const field = str(data.matched_field);
  const pattern = str(data.matched_pattern);
  return { name, on: field && pattern ? `${field} ~ ${pattern}` : null };
}

/** The tint of an event's type pill: what kind of change it is. */
export type EventTone = "warning" | "maintenance" | "critical" | "neutral" | "info" | "major" | "healthy";

/** First matching prefix wins, as server-scan's `TYPE_TINT`. */
const TYPE_TONE: [prefix: string, tone: EventTone][] = [
  ["HEALTH_", "warning"],
  ["MAINTENANCE_", "maintenance"],
  ["SERVER_PRUNED", "critical"],
  ["AUDIT_PURGED", "neutral"],
  ["IDRAC_RESET", "warning"],
  ["LOGIN_DENIED", "critical"],
  ["LOGIN_", "info"],
  ["TOKEN_", "info"],
  ["JOB_", "warning"],
  ["SERVER_RESERVATION_REFUSED", "critical"],
  ["SERVER_RES", "info"],
  ["SERVER_RELEASED", "info"],
  ["OPENSHIFT_", "info"],
  ["CLASSIFICATION_", "major"],
  ["SERVER_RENAMED", "info"],
  ["SERVER_CREATED", "healthy"],
];

export function eventTone(eventType: string): EventTone {
  return TYPE_TONE.find(([prefix]) => eventType.startsWith(prefix))?.[1] ?? "neutral";
}

/**
 * The pager over the pages read so far: "Page X of Y" (from the first page's
 * total when server-scan sent one, else the pages read and one more while
 * there are more), and whether Next has somewhere to go.
 */
export function historyPager(pages: readonly AuditEventPage[], index: number, hasNextPage: boolean): { pageCount: number; canNext: boolean } {
  const first = pages[0]?.page;
  const pageCount = first?.total ? Math.max(1, Math.ceil(first.total / first.page_size)) : pages.length + (hasNextPage ? 1 : 0);
  return { pageCount, canNext: index + 1 < pages.length || hasNextPage };
}
