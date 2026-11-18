/**
 * server-scan's fleet health for the Overview: per site, how many servers
 * each severity holds and how many are in maintenance, each count with the
 * Servers page's filter for it. The numbers and the filters are the Sites
 * page's (features/server-scan/lib/sites.ts, server-scan's own model); this
 * only adds the healthy count and the bar's parts. server-scan counts a
 * server in maintenance there and not by its health (v6.3.0), so the bar has
 * a maintenance part and its parts add up to the site's servers.
 */

import { cardCounts, fleetCards, siteCards, sitesSummary, withFilter, type CardCount, type SiteCard } from "@/features/server-scan/lib/sites";
import { SEVERITY_GLYPH } from "@/features/server-scan/lib/vocabulary";
import type { HealthSeverity, SiteStatsList } from "@/features/server-scan/types/server-scan";

/** A part of the bar: a severity's servers in service, or those in maintenance. */
export type HealthPartKind = HealthSeverity | "MAINTENANCE";

/** The bar's order: healthy grows from the left, the worst toward the right, maintenance, unknown last. */
const BAR_ORDER: readonly HealthPartKind[] = ["HEALTHY", "WARNING", "MAJOR", "CRITICAL", "MAINTENANCE", "UNKNOWN"];

export interface HealthPart {
  severity: HealthPartKind;
  count: number;
}

/** A count and the Servers filter it opens: a Sites card's counts, and the healthy ones. */
export interface HealthCount extends Omit<CardCount, "kind"> {
  kind: CardCount["kind"] | "healthy";
}

export interface HealthRow {
  key: string;
  name: string;
  total: number;
  /** The Servers page filtered to the row's servers; `""` is every server. */
  filter: string;
  /** The severities above zero, in the bar's order. */
  parts: HealthPart[];
  /** The healthy, then server-scan's counts above zero (critical, major, warning, maintenance, unknown). */
  counts: HealthCount[];
}

function partCount(card: SiteCard, part: HealthPartKind): number {
  return part === "MAINTENANCE" ? card.stats.in_maintenance : (card.stats.by_health[part] ?? 0);
}

function healthRow(card: SiteCard): HealthRow {
  const healthy = card.stats.by_health.HEALTHY ?? 0;
  const healthyCount: HealthCount = {
    kind: "healthy",
    count: healthy,
    glyph: SEVERITY_GLYPH.HEALTHY,
    word: "healthy",
    filter: withFilter(card.filter, "health_overall", "HEALTHY"),
  };
  return {
    key: card.key,
    name: card.name,
    total: card.stats.total,
    filter: card.filter,
    parts: BAR_ORDER.map((severity) => ({ severity, count: partCount(card, severity) })).filter((p) => p.count > 0),
    counts: [...(healthy > 0 ? [healthyCount] : []), ...cardCounts(card)],
  };
}

export interface FleetHealth {
  fleet: HealthRow;
  /** Every configured site in server-scan's order, then Unassigned when it holds a server. */
  sites: HealthRow[];
  /** The configured sites, Unassigned left out. */
  siteCount: number;
}

export function fleetHealth(data: SiteStatsList): FleetHealth {
  return {
    fleet: healthRow(fleetCards(data.fleet)[0]),
    sites: siteCards(data.items).map(healthRow),
    siteCount: sitesSummary(data).sites,
  };
}
