/**
 * server-scan's words and orders, shared by the area's pages (ADR-0048):
 * the vendors and collectors, the installation types and OpenShift states,
 * the severities with their glyphs and order, the Unassigned bucket.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18):
 * `frontend/src/api/sites.ts` (vendors, collectors, Unassigned),
 * `frontend/src/components/severity.ts` (glyphs, order),
 * `frontend/src/features/inventory/InventoryPage.tsx` (the dropdowns' options)
 * and `frontend/src/components/InstallationBadge.tsx` (the state labels).
 */

import type { HealthSeverity, InstallationType, OpenShiftState, Vendor } from "@/types/server-scan";

/** server-scan's bucket for servers whose name carries no site. */
export const UNASSIGNED_SITE_ID = "unassigned";

export const VENDORS: readonly Vendor[] = ["dell", "cisco", "hp", "standalone", "kubevirt"];

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

/** The collectors that exist (server-scan's `ManagerType`), with its labels. */
export const SOURCE_PROVIDERS: readonly { value: string; label: string }[] = [
  { value: "UCS_CENTRAL", label: "UCS Central" },
  { value: "INTERSIGHT", label: "Intersight" },
  { value: "OPENMANAGE", label: "OpenManage (Dell)" },
  { value: "ONEVIEW", label: "OneView (HPE)" },
  { value: "REDFISH_STANDALONE", label: "Standalone (Redfish)" },
  { value: "KUBEVIRT", label: "KubeVirt (VMs)" },
];

export const INSTALLATION_TYPES: readonly InstallationType[] = ["HOSTED_CLUSTER", "MCE", "UPI", "UNCLASSIFIED"];

/** The Installation dropdown, in server-scan's order and its table-width words. */
export const OPENSHIFT_STATES: readonly { value: OpenShiftState; label: string }[] = [
  { value: "INSTALLED", label: "Installed" },
  { value: "INSTALLED_TO_INVENTORY", label: "In inventory" },
  { value: "AVAILABLE", label: "Available" },
];

export const HEALTH_SEVERITIES: readonly HealthSeverity[] = ["UNKNOWN", "HEALTHY", "WARNING", "MAJOR", "CRITICAL"];

/** The one place a severity's shape is decided: shape, then word, then colour tell them apart. */
export const SEVERITY_GLYPH: Record<HealthSeverity, string> = {
  CRITICAL: "◆",
  MAJOR: "⬟",
  WARNING: "▲",
  HEALTHY: "●",
  UNKNOWN: "○",
};

/** Most to least severe; the one ordering every severity sort uses. */
export const SEVERITY_ORDER: readonly HealthSeverity[] = ["CRITICAL", "MAJOR", "WARNING", "HEALTHY", "UNKNOWN"];

/**
 * Whether a component's health is a severity this UI styles: Cisco and the
 * Redfish PSU path report UP, DOWN, DISABLED or UNKNOWN instead, shown as
 * their own word.
 */
export function isHealthSeverity(value: string): value is HealthSeverity {
  return value in SEVERITY_GLYPH;
}
