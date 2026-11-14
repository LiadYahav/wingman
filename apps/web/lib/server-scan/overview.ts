/**
 * The Overview tab's rules, as server-scan's server page has them
 * (docs/notes/2026-11-13-server-scan-area-api.md §9.1): which health
 * categories a server can be judged on, the profile template under its
 * vendor's own name, why a BMC could not be read, the matched rule, an
 * install lock's details and a maintenance in words.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/features/servers/OverviewTab.tsx` and
 * `frontend/src/components/ReservationBadge.tsx`.
 */

import type { HealthSeverity } from "@/types/server-scan";
import type {
  Classification, HealthSummary, RaidDetection, RecordMaintenance, ServerRecord, UnreachableReason,
} from "@/types/server-scan-record";
import type { ReservationState } from "@/types/server-scan-servers";
import { actorIdLabel } from "./actor";
import { formatTimestamp } from "./datetime";

/** Each vendor's own name for a profile template; a standalone BMC and a VM have none, so no row. */
const PROFILE_TEMPLATE_LABELS: Record<string, string> = {
  UCS_CENTRAL: "Service profile template",
  INTERSIGHT: "Server profile template",
  ONEVIEW: "Server profile template",
  OPENMANAGE: "Deployment template",
};

/** The template row's label for this collector, or `null`: no row. */
export function profileTemplateLabel(sourceProvider: string | null): string | null {
  return sourceProvider ? (PROFILE_TEMPLATE_LABELS[sourceProvider] ?? null) : null;
}

const UNREACHABLE_LABELS: Record<UnreachableReason, string> = {
  network_unreachable: "Unreachable",
  auth_rejected: "Wrong credentials",
  tls_error: "TLS error",
  timeout: "Timed out",
  protocol_error: "Protocol error",
  not_an_idrac: "Not an iDRAC",
};

/** "Wrong credentials since <time>": why the last collection could not read the BMC. */
export function collectionText(reason: UnreachableReason | null, since: string | null): string {
  const what = reason ? (UNREACHABLE_LABELS[reason] ?? reason) : "Unreachable";
  return since ? `${what} since ${formatTimestamp(since)}` : what;
}

/** "<rule> (<field> ~ <pattern>)"; `null` for a legacy classification with no rule's name. */
export function matchedRuleText(c: Classification): string | null {
  if (!c.matched_rule_name) return null;
  return c.matched_field && c.matched_pattern ? `${c.matched_rule_name} (${c.matched_field} ~ ${c.matched_pattern})` : c.matched_rule_name;
}

type Category = Exclude<keyof HealthSummary, "overall" | "reasons">;

/** The categories behind "Overall health", in server-scan's order. */
const HEALTH_CATEGORIES: readonly { key: Category; label: string }[] = [
  { key: "memory", label: "Memory" },
  { key: "storage", label: "Storage" },
  { key: "raid", label: "RAID" },
  { key: "network", label: "Network" },
  { key: "connectivity", label: "Connectivity" },
  { key: "power", label: "Power" },
  { key: "gpu", label: "GPU" },
  { key: "bmc", label: "BMC" },
  { key: "name", label: "Name" },
];

/** Cisco behind its fabric interconnects is never probed, and a VM has no BMC: only "Unknown" there. */
const BMC_UNCHECKED = new Set(["UCS_CENTRAL", "UCS_MANAGER", "INTERSIGHT", "KUBEVIRT"]);
/** A VM has no power supply. */
const POWER_UNCHECKED = new Set(["KUBEVIRT"]);
/** Only the fabric-managed Cisco collectors check fabric paths. */
const FABRIC_PROVIDERS = new Set(["UCS_CENTRAL", "UCS_MANAGER", "INTERSIGHT"]);
/** RAID is judged for OpenManage, standalone Redfish and Cisco UCS. */
const RAID_PROVIDERS = new Set(["OPENMANAGE", "REDFISH_STANDALONE", "UCS_CENTRAL", "UCS_MANAGER"]);

function judged(key: Category, record: Pick<ServerRecord, "source_provider" | "health" | "hardware">): boolean {
  const provider = record.source_provider ?? "";
  switch (key) {
    case "bmc":
      return !BMC_UNCHECKED.has(provider);
    case "power":
      return !POWER_UNCHECKED.has(provider);
    case "connectivity":
      return FABRIC_PROVIDERS.has(provider);
    case "raid":
      return RAID_PROVIDERS.has(provider);
    case "gpu":
      return record.hardware.gpus.length > 0;
    case "name":
      return record.health.name !== "UNKNOWN";
    default:
      return true;
  }
}

/** The breakdown's badges: each category only where server-scan can judge it, so none could only say "Unknown". */
export function healthCategories(
  record: Pick<ServerRecord, "source_provider" | "health" | "hardware">
): { key: Category; label: string; severity: HealthSeverity }[] {
  return HEALTH_CATEGORIES.filter(({ key }) => judged(key, record)).map(({ key, label }) => ({ key, label, severity: record.health[key] }));
}

/** A reason's category in the breakdown's words ("storage" → "Storage"); one it does not name, as sent. */
export function categoryLabel(category: string): string {
  return HEALTH_CATEGORIES.find((c) => c.key === category)?.label ?? category;
}

/** Which BMC and method answered the RAID check, and why it is Unknown when it could not tell. */
export function raidNote(raid: RaidDetection | null): string | null {
  if (!raid) return null;
  const source = [raid.bmc, raid.method].filter(Boolean).join(" · ");
  const why = raid.state === "UNKNOWN" ? raid.reason : null;
  const note = [source, why].filter(Boolean).join(" — ");
  return note || null;
}

/** Everything known about an install lock, for its tooltip: where, which InfraEnv, by whom, until when. */
export function reservationDetail(lock: ReservationState): string {
  const target = lock.mce_cluster ?? "an unnamed MCE";
  return [
    `Installing to ${target}`,
    lock.infra_env ? `InfraEnv ${lock.infra_env}` : null,
    lock.holder ? `held by ${lock.holder}` : null,
    lock.expires_at ? `lock expires ${formatTimestamp(lock.expires_at)}` : "lock has no expiry",
  ]
    .filter(Boolean)
    .join(" · ");
}

/** "<reason> - by <who>", as server-scan's Maintenance field reads; `null` when not in maintenance. */
export function maintenanceText(m: RecordMaintenance): string | null {
  if (!m.enabled) return null;
  return `${m.reason ?? "Enabled"}${m.created_by ? ` - by ${actorIdLabel(m.created_by)}` : ""}`;
}

/** Since when, and until when it should last: the maintenance's tooltip; `null` when neither is known. */
export function maintenanceWhen(m: RecordMaintenance): string | null {
  const parts = [
    m.created_at ? `Since ${formatTimestamp(m.created_at)}` : null,
    m.expected_end ? `expected to end ${formatTimestamp(m.expected_end)}` : null,
  ].filter(Boolean);
  return m.enabled && parts.length > 0 ? parts.join(", ") : null;
}
