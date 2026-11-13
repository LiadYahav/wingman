/**
 * The Sites page's cards (ADR-0048): a row of fleet-wide cards above one card
 * per site, each with its counts, as server-scan's landing page shows them.
 *
 * server-scan's own model, ported without its JSX from team-redbull/server-scan
 * at 92146d3 (decision 18): `fleetCards`, `siteCards`, the filters, the
 * "all healthy" rule and the vendor bars from
 * `frontend/src/features/sites/SitesOverviewPage.tsx`, the vendor labels from
 * `frontend/src/api/sites.ts`, the glyphs from `frontend/src/components/severity.ts`.
 *
 * Each card and count carries the Servers filter it opens in server-scan
 * (`site_id`, `installation_type`, `openshift_state`, `health_overall`,
 * `maintenance`). The counts are not links until Wingman's Servers page exists.
 */

import type { Breakdown, FleetSummary, HealthSeverity, OpenShiftState, SiteStats, SiteStatsList } from "@/types/server-scan";

/** server-scan's bucket for servers whose name carries no site. */
export const UNASSIGNED_SITE_ID = "unassigned";

/** What one card shows; every card on the page is the same shape. */
export interface SiteCard {
  key: string;
  name: string;
  subtitle: string;
  /** The Servers filter the card opens, as a query string; `""` is every server. */
  filter: string;
  stats: Breakdown;
  /** Site cards only: the fleet row has its own Installed and Available cards. */
  byOpenshiftState?: FleetSummary["by_openshift_state"];
}

const EMPTY: Breakdown = { total: 0, by_vendor: [], by_health: {}, in_maintenance: 0 };

/** The fleet-wide cards, read off server-scan's own `fleet` summary (never summed here), in a fixed order. */
export function fleetCards(fleet: FleetSummary): SiteCard[] {
  const fleetWide = "servers, every site";
  const type = (key: "UPI" | "HOSTED_CLUSTER" | "MCE", name: string): SiteCard => ({
    key,
    name,
    subtitle: fleetWide,
    filter: `installation_type=${key}`,
    stats: fleet.by_installation_type[key] ?? EMPTY,
  });
  const state = (key: "AVAILABLE" | "INSTALLED", name: string, subtitle: string): SiteCard => ({
    key,
    name,
    subtitle,
    filter: `openshift_state=${key}`,
    stats: fleet.by_openshift_state[key] ?? EMPTY,
  });
  return [
    { key: "__all__", name: "Across all sites", subtitle: fleetWide, filter: "", stats: fleet },
    type("UPI", "UPI"),
    type("HOSTED_CLUSTER", "Hosted cluster"),
    type("MCE", "MCE"),
    state("AVAILABLE", "Available", "no cluster holds these"),
    state("INSTALLED", "Installed", "in use by a cluster"),
  ];
}

/** One card per configured site, in server-scan's order; Unassigned only when it holds a server. */
export function siteCards(items: SiteStats[]): SiteCard[] {
  return items
    .filter((site) => site.site_id !== UNASSIGNED_SITE_ID || site.total > 0)
    .map((site) => ({
      key: site.site_id,
      name: site.name,
      subtitle: site.site_id === UNASSIGNED_SITE_ID ? "no site in hostname" : "servers",
      filter: withFilter("", "site_id", site.site_id),
      stats: site,
      byOpenshiftState: site.by_openshift_state,
    }));
}

/** `filter` plus one more parameter: the count's own slice of the card. */
export function withFilter(filter: string, key: string, value: string): string {
  const params = new URLSearchParams(filter);
  params.append(key, value);
  return params.toString();
}

/** server-scan's glyph per severity: shape, then word, then colour tell them apart. */
const GLYPH: Record<HealthSeverity, string> = {
  CRITICAL: "◆",
  MAJOR: "⬟",
  WARNING: "▲",
  HEALTHY: "●",
  UNKNOWN: "○",
};

export type CountKind = "critical" | "major" | "warning" | "maintenance" | "unknown";

export interface CardCount {
  kind: CountKind;
  count: number;
  glyph: string;
  word: string;
  /** The Servers filter this count opens. */
  filter: string;
}

/** The card's counts above zero, in server-scan's order: a row of zeroes trains people to skip the card. */
export function cardCounts(card: SiteCard): CardCount[] {
  const health = (severity: HealthSeverity, kind: CountKind): CardCount => ({
    kind,
    count: card.stats.by_health[severity] ?? 0,
    glyph: GLYPH[severity],
    word: kind,
    filter: withFilter(card.filter, "health_overall", severity),
  });
  const maintenance: CardCount = {
    kind: "maintenance",
    count: card.stats.in_maintenance,
    glyph: "⏸",
    word: "in maintenance",
    filter: withFilter(card.filter, "maintenance", "true"),
  };
  return [
    health("CRITICAL", "critical"),
    health("MAJOR", "major"),
    health("WARNING", "warning"),
    maintenance,
    health("UNKNOWN", "unknown"),
  ].filter((c) => c.count > 0);
}

/**
 * `all-healthy` when every server was evaluated HEALTHY: not merely none
 * critical or warning, which is also true of a site nothing has evaluated
 * yet. `empty` with no server at all.
 */
export function cardVerdict(stats: Breakdown): "all-healthy" | "empty" | null {
  if (stats.total === 0) return "empty";
  return (stats.by_health.HEALTHY ?? 0) === stats.total ? "all-healthy" : null;
}

export const HEALTHY_GLYPH = GLYPH.HEALTHY;

export interface StateCount {
  state: Extract<OpenShiftState, "INSTALLED" | "AVAILABLE">;
  count: number;
  word: string;
  filter: string;
}

/** A site card's installed and available servers, each above zero, from its own slice. */
export function installedAvailable(card: SiteCard): StateCount[] {
  const states = card.byOpenshiftState;
  if (!states) return [];
  const count = (state: StateCount["state"], word: string): StateCount => ({
    state,
    count: states[state]?.total ?? 0,
    word,
    filter: withFilter(card.filter, "openshift_state", state),
  });
  return [count("INSTALLED", "installed"), count("AVAILABLE", "available")].filter((s) => s.count > 0);
}

const VENDOR_LABELS: Record<string, string> = {
  dell: "Dell",
  cisco: "Cisco",
  hp: "HPE",
  standalone: "Standalone",
  kubevirt: "KubeVirt",
};

/** A vendor server-scan names later is shown under its own name, never dropped. */
export function vendorLabel(vendor: string): string {
  return VENDOR_LABELS[vendor] ?? vendor;
}

export interface VendorBar {
  vendor: string;
  label: string;
  count: number;
  /** Its share of the card's own total (not the largest card's), 0-100. */
  percent: number;
}

/** A bar per vendor server-scan lists, zeroes too; none for an empty card. */
export function vendorBars(stats: Breakdown): VendorBar[] {
  if (stats.total <= 0) return [];
  return stats.by_vendor.map((entry) => ({
    vendor: entry.vendor,
    label: vendorLabel(entry.vendor),
    count: entry.count,
    percent: Math.min(100, Math.round((entry.count / stats.total) * 100)),
  }));
}

/** The header's "N servers across M sites": M is the configured sites, Unassigned left out. */
export function sitesSummary(data: SiteStatsList): { servers: number; sites: number } {
  return {
    servers: data.fleet.total,
    sites: data.items.filter((s) => s.site_id !== UNASSIGNED_SITE_ID).length,
  };
}
