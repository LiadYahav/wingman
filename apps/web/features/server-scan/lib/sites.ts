/**
 * The Sites page's cards (ADR-0048): a row of fleet-wide cards above one card
 * per site, each with its counts, as server-scan's landing page shows them.
 *
 * server-scan's own model, ported without its JSX from team-redbull/server-scan
 * (decision 18): `fleetCards`, `siteCards`, the filters, the
 * "all healthy" rule and the Physical, VM and vendor bars from
 * `frontend/src/features/sites/SitesOverviewPage.tsx`; the vendor labels and
 * glyphs are in `./vocabulary`.
 *
 * Each card, count and bar is a link to the Servers page with the filter it
 * opens in server-scan (`site_id`, `installation_type`, `openshift_state`,
 * `health_overall`, `maintenance`, `server_type`, `vendor`), in server-scan's
 * parameter names.
 *
 * What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
 */

import type { Breakdown, FleetSummary, HealthSeverity, OpenShiftState, SiteStats, SiteStatsList } from "@/features/server-scan/types/server-scan";
import { SEVERITY_GLYPH as GLYPH, UNASSIGNED_SITE_ID, serverTypeLabel, vendorLabel } from "./vocabulary";

/** The vendor whose servers are VMs: the VM bar, never a vendor bar of its own. */
const VM_VENDOR = "kubevirt";

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
 * `all-healthy` when every server in service was evaluated HEALTHY: not
 * merely none critical or warning, which is also true of a site nothing has
 * evaluated yet. `by_health` counts servers in service only, those in
 * maintenance being `in_maintenance` (server-scan v6.3.0, its a0e29c3), so a
 * card whose every server is in maintenance is neither. `empty` with no
 * server at all.
 */
export function cardVerdict(stats: Breakdown): "all-healthy" | "empty" | null {
  if (stats.total === 0) return "empty";
  const inService = stats.total - stats.in_maintenance;
  return inService > 0 && (stats.by_health.HEALTHY ?? 0) === inService ? "all-healthy" : null;
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

export interface CountBar {
  /** `physical`, `vm`, or the vendor. */
  key: string;
  /** Physical and VM first, then the vendors, a little apart. */
  group: "type" | "vendor";
  label: string;
  count: number;
  /** Its share of the card's own total (not the largest card's), 0-100. */
  percent: number;
  /** The Servers filter it opens (the card's plus `server_type` or `vendor`); `null` at zero. */
  filter: string | null;
}

/**
 * The card's bars, as server-scan v6.3.0 draws them (its a0e29c3): Physical,
 * then VM, then each vendor it lists but KubeVirt, which is the VM row (VM is
 * the `kubevirt` count, Physical the total less it); zeroes too, none for an
 * empty card. A bar above zero opens the Servers page with the card's filter
 * plus its own.
 */
export function countBars(card: SiteCard): CountBar[] {
  const { stats } = card;
  if (stats.total <= 0) return [];
  const vm = stats.by_vendor.find((entry) => entry.vendor === VM_VENDOR)?.count ?? 0;
  const bar = (group: CountBar["group"], key: string, label: string, count: number, param: string): CountBar => ({
    key,
    group,
    label,
    count,
    percent: Math.min(100, Math.round((count / stats.total) * 100)),
    filter: count > 0 ? withFilter(card.filter, param, key) : null,
  });
  return [
    bar("type", "physical", serverTypeLabel("physical"), stats.total - vm, "server_type"),
    bar("type", "vm", serverTypeLabel("vm"), vm, "server_type"),
    ...stats.by_vendor
      .filter((entry) => entry.vendor !== VM_VENDOR)
      .map((entry) => bar("vendor", entry.vendor, vendorLabel(entry.vendor), entry.count, "vendor")),
  ];
}

/** One part of a card's health bar: a severity's servers in service, or those in maintenance. */
export interface HealthSegment {
  key: HealthSeverity | "MAINTENANCE";
  count: number;
}

/**
 * The parts of server-scan's stacked health bar (v6.2.0, its 4d9d171), worst
 * first so the red end is at the left: critical, major, warning, unknown,
 * maintenance, healthy; only those above zero. `by_health` counts servers in
 * service only (v6.3.0), so they add up to the card's total.
 */
export function healthSegments(stats: Breakdown): HealthSegment[] {
  if (stats.total === 0) return [];
  const order: HealthSegment["key"][] = ["CRITICAL", "MAJOR", "WARNING", "UNKNOWN", "MAINTENANCE", "HEALTHY"];
  return order
    .map((key) => ({ key, count: key === "MAINTENANCE" ? stats.in_maintenance : (stats.by_health[key] ?? 0) }))
    .filter((segment) => segment.count > 0);
}

/** The bar's words, for its tooltip and its name: "2 critical, 1 maintenance, 20 healthy". */
export function healthSummary(segments: HealthSegment[]): string {
  return segments.map((segment) => `${segment.count} ${segment.key.toLowerCase()}`).join(", ");
}

/** The header's "N servers across M sites": M is the configured sites, Unassigned left out. */
export function sitesSummary(data: SiteStatsList): { servers: number; sites: number } {
  return {
    servers: data.fleet.total,
    sites: data.items.filter((s) => s.site_id !== UNASSIGNED_SITE_ID).length,
  };
}
