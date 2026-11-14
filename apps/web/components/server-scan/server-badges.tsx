import { actorIdLabel } from "@/lib/server-scan/actor";
import { formatAge } from "@/lib/server-scan/datetime";
import { reservationDetail } from "@/lib/server-scan/overview";
import { isDonor } from "@/lib/server-scan/rows";
import { SEVERITY_GLYPH } from "@/lib/server-scan/vocabulary";
import { cn, formatDateTime } from "@/lib/utils";
import type { HealthSeverity, OpenShiftState } from "@/types/server-scan";
import type { ReservationState, ServerRow } from "@/types/server-scan-servers";

/**
 * The Server Scan area's badges, server-scan's words and rules in Wingman's
 * colours (team-redbull/server-scan at 92146d3: `InstallationBadge.tsx`,
 * `ReservationBadge.tsx`, `StateBadge.tsx`, `HealthBadge.tsx`, decision 18),
 * shared by the Servers table and a server's page. The explanation is each
 * badge's tooltip.
 */

export const pill = "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-px text-xs font-medium";

const INSTALLATION: Record<OpenShiftState, { label: string; full: string; tone: string; title: string }> = {
  AVAILABLE: { label: "Available", full: "Available", tone: "bg-status-ready/15 text-status-ready-fg", title: "No cluster holds it" },
  INSTALLED: { label: "Installed", full: "Installed", tone: "bg-primary/12 text-primary", title: "A cluster's node" },
  INSTALLED_TO_INVENTORY: {
    label: "In inventory",
    full: "Installed to inventory",
    tone: "bg-status-provisioning/15 text-status-provisioning-fg",
    title: "An MCE's Agent, in no cluster yet",
  },
};

/** Whether a cluster uses the server: the table's short word, or the page's `full` one. */
export function InstallationBadge({ state, full = false }: { state: OpenShiftState; full?: boolean }) {
  const known = INSTALLATION[state] ?? { label: state, full: state, tone: "bg-muted text-muted-foreground", title: "" };
  return (
    <span className={cn(pill, known.tone)} title={known.title} data-testid="ss-installation">
      {full ? known.full : known.label}
    </span>
  );
}

/** Whether a cluster uses the server, and under it which MCE an install is taking it to. */
export function InstallationCell({ row }: { row: ServerRow }) {
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <InstallationBadge state={row.openshift_state} />
      <ReservationBadge reservation={row.reservation} />
    </span>
  );
}

/**
 * "→ <MCE>" (on a server's page "→ Installing to <MCE>") while an install
 * holds the server: beside the state, not in its place, since a server
 * mid-install is still Available to the collectors. Nothing when no lock is
 * held (nearly every server).
 */
export function ReservationBadge({ reservation, full = false }: { reservation: ReservationState; full?: boolean }) {
  if (!reservation.held) return null;
  const target = reservation.mce_cluster ?? "an unnamed MCE";
  const detail = reservationDetail(reservation);
  return (
    <span title={detail} aria-label={detail} data-testid="ss-reservation" className={cn(pill, "bg-status-provisioning/15 text-status-provisioning-fg")}>
      <span aria-hidden>→</span>
      {full ? `Installing to ${target}` : target}
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

/** A severity's tone, for a chip that shows server-scan's own word (History's FROM → TO). */
export function severityTone(severity: string): string {
  return SEVERITY[severity as HealthSeverity]?.tone ?? SEVERITY.UNKNOWN.tone;
}

/** A health as its glyph and word: shape, then word, then colour tell them apart. */
export function SeverityPill({ severity }: { severity: HealthSeverity }) {
  const known = SEVERITY[severity] ?? SEVERITY.UNKNOWN;
  return (
    <span className={cn(pill, known.tone)} data-health={severity}>
      <span aria-hidden className="text-[0.7em] leading-none">
        {SEVERITY_GLYPH[severity] ?? SEVERITY_GLYPH.UNKNOWN}
      </span>
      {known.label}
    </span>
  );
}

/**
 * The health with its glyph, then what it does not say alone: in maintenance
 * (or a parts donor), stale with its age, OpenShift naming it otherwise.
 */
export function StateCell({ row }: { row: ServerRow }) {
  const { maintenance } = row;
  const donor = isDonor(maintenance);
  const why = [maintenance.reason, maintenance.created_by ? `by ${actorIdLabel(maintenance.created_by)}` : null].filter(Boolean).join(" - ");
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5" data-testid="ss-state">
      <SeverityPill severity={row.health} />
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
