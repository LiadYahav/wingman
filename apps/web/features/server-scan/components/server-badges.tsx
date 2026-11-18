import { actorIdLabel } from "@/features/server-scan/lib/actor";
import { formatAge } from "@/features/server-scan/lib/datetime";
import { reservationDetail } from "@/features/server-scan/lib/overview";
import { isDonor } from "@/features/server-scan/lib/rows";
import { SEVERITY_GLYPH } from "@/features/server-scan/lib/vocabulary";
import { cn, formatDateTime } from "@/lib/utils";
import type { HealthSeverity, OpenShiftState } from "@/features/server-scan/types/server-scan";
import type { ReservationState, ServerRow } from "@/features/server-scan/types/server-scan-servers";

/**
 * The Server Scan area's badges, server-scan's words, rules and colours
 * (team-redbull/server-scan: `InstallationBadge.tsx`, `ReservationBadge.tsx`,
 * `StateBadge.tsx`, `HealthBadge.tsx`, decision 18), shared by the Servers
 * table and a server's page. The colours are server-scan's own palette
 * (`../palette.css`: its tint and on-tint pairs; Installed red, Available
 * green, as its palette inverts for "in use" and "free"), at the user's
 * request (ADR-0048's 2026-11-18 amendment). The explanation is each
 * badge's tooltip.
 *
 * What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
 */

export const pill = "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium";

const INSTALLATION: Record<OpenShiftState, { label: string; full: string; tone: string; title: string }> = {
  AVAILABLE: { label: "Available", full: "Available", tone: "bg-ss-tint-healthy text-ss-on-healthy", title: "No cluster holds it" },
  INSTALLED: { label: "Installed", full: "Installed", tone: "bg-ss-tint-critical text-ss-on-critical", title: "A cluster's node" },
  INSTALLED_TO_INVENTORY: {
    label: "In inventory",
    full: "Installed to inventory",
    tone: "bg-ss-tint-info text-ss-on-info",
    title: "An MCE's Agent, in no cluster yet",
  },
};

/** Whether a cluster uses the server: the table's short word, or the page's `full` one. */
export function InstallationBadge({ state, full = false }: { state: OpenShiftState; full?: boolean }) {
  const known = INSTALLATION[state] ?? { label: state, full: state, tone: "bg-ss-tint-unknown text-ss-on-unknown", title: "" };
  return (
    <span className={cn(pill, known.tone)} title={known.title} data-testid="ss-installation">
      {full ? known.full : known.label}
    </span>
  );
}

/** Whether a cluster uses the server, and under it which MCE an install is taking it to, centred as there. */
export function InstallationCell({ row }: { row: ServerRow }) {
  return (
    <span className="inline-flex flex-col items-center gap-1">
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
    <span title={detail} aria-label={detail} data-testid="ss-reservation" className={cn(pill, "bg-ss-tint-info text-ss-on-info")}>
      <span aria-hidden>→</span>
      {full ? `Installing to ${target}` : target}
    </span>
  );
}

const SEVERITY: Record<HealthSeverity, { label: string; tone: string }> = {
  CRITICAL: { label: "Critical", tone: "bg-ss-tint-critical text-ss-on-critical" },
  MAJOR: { label: "Major", tone: "bg-ss-tint-major text-ss-on-major" },
  WARNING: { label: "Warning", tone: "bg-ss-tint-warning text-ss-on-warning" },
  HEALTHY: { label: "Healthy", tone: "bg-ss-tint-healthy text-ss-on-healthy" },
  UNKNOWN: { label: "Unknown", tone: "bg-ss-tint-unknown text-ss-on-unknown" },
};

/**
 * server-scan's `HealthBadge` (its server page's health): the severity's own
 * word as server-scan sends it, in that badge's palette (Tailwind's green,
 * amber, orange, red and grey; its light and its dark), no glyph.
 */
const HEALTH_BADGE: Record<HealthSeverity, string> = {
  HEALTHY: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  WARNING: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  MAJOR: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
  CRITICAL: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  UNKNOWN: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
};

/** A severity on a server's page, as server-scan's page shows it: `HEALTHY`, `CRITICAL`, ... */
export function HealthBadge({ severity }: { severity: HealthSeverity }) {
  return (
    <span className={cn(pill, HEALTH_BADGE[severity] ?? HEALTH_BADGE.UNKNOWN)} data-health={severity}>
      {severity}
    </span>
  );
}

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
    <span className="inline-flex flex-wrap items-center justify-center gap-1.5" data-testid="ss-state">
      <SeverityPill severity={row.health} />
      {maintenance.enabled && (
        <span
          title={why || undefined}
          data-testid="ss-maint-chip"
          className={cn(pill, donor ? "bg-ss-tint-donor text-ss-on-donor" : "bg-ss-tint-maintenance text-ss-on-maintenance")}
        >
          <span aria-hidden className="text-[0.7em] leading-none">
            {donor ? "◇" : "⏸"}
          </span>
          {donor ? "Donor" : "Maint"}
        </span>
      )}
      {row.stale && (
        <span title={row.last_seen_at ? `Last seen ${formatDateTime(row.last_seen_at)}` : "Never successfully collected"} className={cn(pill, "bg-ss-tint-unknown text-ss-on-unknown")}>
          Stale{row.last_seen_at ? ` ${formatAge(row.last_seen_at)}` : ""}
        </span>
      )}
      {row.openshift_reported_name && (
        <span title={`OpenShift reports this node as "${row.openshift_reported_name}"`} className={cn(pill, "bg-ss-tint-warning text-ss-on-warning")}>
          Name mismatch
        </span>
      )}
    </span>
  );
}
