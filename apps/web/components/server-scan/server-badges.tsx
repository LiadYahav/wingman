import { formatAge } from "@/lib/server-scan/format";
import { isDonor } from "@/lib/server-scan/rows";
import { SEVERITY_GLYPH } from "@/lib/server-scan/vocabulary";
import { cn, formatDateTime } from "@/lib/utils";
import type { HealthSeverity, OpenShiftState } from "@/types/server-scan";
import type { ServerRow } from "@/types/server-scan-servers";

/**
 * The Servers table's badges, server-scan's words and rules in Wingman's
 * colours (team-redbull/server-scan at 92146d3: `InstallationBadge.tsx`,
 * `ReservationBadge.tsx`, `StateBadge.tsx`, decision 18). The explanation is
 * each badge's tooltip.
 */

const pill = "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-px text-xs font-medium";

const INSTALLATION: Record<OpenShiftState, { label: string; tone: string; title: string }> = {
  AVAILABLE: { label: "Available", tone: "bg-status-ready/15 text-status-ready-fg", title: "No cluster holds it" },
  INSTALLED: { label: "Installed", tone: "bg-primary/12 text-primary", title: "A cluster's node" },
  INSTALLED_TO_INVENTORY: {
    label: "In inventory",
    tone: "bg-status-provisioning/15 text-status-provisioning-fg",
    title: "An MCE's Agent, in no cluster yet",
  },
};

/** Whether a cluster uses the server, and under it which MCE an install is taking it to. */
export function InstallationCell({ row }: { row: ServerRow }) {
  const state = INSTALLATION[row.openshift_state] ?? { label: row.openshift_state, tone: "bg-muted text-muted-foreground", title: "" };
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <span className={cn(pill, state.tone)} title={state.title}>
        {state.label}
      </span>
      <ReservationBadge row={row} />
    </span>
  );
}

/**
 * "→ <MCE>" while an install holds the server: under the state, not in its
 * place, since a server mid-install is still Available to the collectors.
 * Nothing when no lock is held (nearly every row).
 */
function ReservationBadge({ row }: { row: ServerRow }) {
  const lock = row.reservation;
  if (!lock.held) return null;
  const target = lock.mce_cluster ?? "an unnamed MCE";
  const detail = [
    `Installing to ${target}`,
    lock.infra_env ? `InfraEnv ${lock.infra_env}` : null,
    lock.holder ? `held by ${lock.holder}` : null,
    lock.expires_at ? `lock expires ${formatDateTime(lock.expires_at)}` : "lock has no expiry",
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <span title={detail} aria-label={detail} data-testid="ss-reservation" className={cn(pill, "bg-status-provisioning/15 text-status-provisioning-fg")}>
      <span aria-hidden>→</span>
      {target}
    </span>
  );
}

const SEVERITY: Record<HealthSeverity, { label: string; tone: string }> = {
  CRITICAL: { label: "Critical", tone: "bg-status-error/15 text-status-error-fg" },
  MAJOR: { label: "Major", tone: "bg-status-error/10 text-status-error-fg" },
  WARNING: { label: "Warning", tone: "bg-status-warning/15 text-status-warning-fg" },
  HEALTHY: { label: "Healthy", tone: "bg-status-ready/15 text-status-ready-fg" },
  UNKNOWN: { label: "Unknown", tone: "bg-muted text-muted-foreground" },
};

/** Who put it in maintenance: a static token reads "API token (admin)", anything else as it is. */
function actorLabel(id: string): string {
  const personal = /^token:(.+)$/.exec(id);
  if (personal) return `${personal[1]} (personal token)`;
  const token = /^api-token-(.+)$/.exec(id);
  return token ? `API token (${token[1]})` : id;
}

/**
 * The health with its glyph, then what it does not say alone: in maintenance
 * (or a parts donor), stale with its age, OpenShift naming it otherwise.
 */
export function StateCell({ row }: { row: ServerRow }) {
  const severity = SEVERITY[row.health] ?? SEVERITY.UNKNOWN;
  const { maintenance } = row;
  const donor = isDonor(maintenance);
  const why = [maintenance.reason, maintenance.created_by ? `by ${actorLabel(maintenance.created_by)}` : null].filter(Boolean).join(" - ");
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5" data-testid="ss-state">
      <span className={cn(pill, severity.tone)} data-health={row.health}>
        <span aria-hidden className="text-[0.7em] leading-none">
          {SEVERITY_GLYPH[row.health] ?? SEVERITY_GLYPH.UNKNOWN}
        </span>
        {severity.label}
      </span>
      {maintenance.enabled && (
        <span
          title={why || undefined}
          data-testid="ss-maint-chip"
          className={cn(pill, donor ? "bg-muted text-foreground/80" : "bg-status-provisioning/15 text-status-provisioning-fg")}
        >
          <span aria-hidden className="text-[0.7em] leading-none">
            {donor ? "◇" : "⏸"}
          </span>
          {donor ? "Donor" : "Maint"}
        </span>
      )}
      {row.stale && (
        <span title={row.last_seen_at ? `Last seen ${formatDateTime(row.last_seen_at)}` : "Never successfully collected"} className={cn(pill, "bg-muted text-muted-foreground")}>
          Stale{row.last_seen_at ? ` ${formatAge(row.last_seen_at)}` : ""}
        </span>
      )}
      {row.openshift_reported_name && (
        <span title={`OpenShift reports this node as "${row.openshift_reported_name}"`} className={cn(pill, "bg-status-warning/15 text-status-warning-fg")}>
          Name mismatch
        </span>
      )}
    </span>
  );
}
