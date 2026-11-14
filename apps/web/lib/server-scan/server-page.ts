/**
 * The server page's address (docs/notes/2026-11-13-server-scan-area-api.md
 * §9.8): `/server-scan/servers/<id>`, its tab in the URL as `?tab=` (Overview
 * has none), and "← Servers" back to the Servers view it was opened from.
 * server-scan keeps the tab in component state and the Servers filters in
 * its router's state; Wingman keeps the tab in the URL and the filters in
 * the browser's session.
 */

import { areaById } from "@/lib/areas";

/** server-scan's five tabs, in its order. */
export const SERVER_TABS = ["overview", "hardware", "network", "connectivity", "history"] as const;
export type ServerTab = (typeof SERVER_TABS)[number];

export const TAB_LABELS: Record<ServerTab, string> = {
  overview: "Overview",
  hardware: "Hardware",
  network: "Network",
  connectivity: "Connectivity",
  history: "History",
};

/** `?tab=`'s value as a tab; anything else is Overview. */
export function parseTab(value: string | null): ServerTab {
  return SERVER_TABS.find((tab) => tab === value) ?? "overview";
}

/** The Servers page, unfiltered. */
export const SERVERS_HREF = `${areaById("server-scan").href}/servers`;

/** A server's page, on `tab`. */
export function serverHref(id: string, tab: ServerTab = "overview"): string {
  const page = `${SERVERS_HREF}/${encodeURIComponent(id)}`;
  return tab === "overview" ? page : `${page}?tab=${tab}`;
}

/** Where "← Servers" goes: the Servers view the page was opened from, when it is one, else the unfiltered list. */
export function backHref(stored: string | null): string {
  if (!stored) return SERVERS_HREF;
  const [path] = stored.split(/[?#]/);
  return path === SERVERS_HREF ? stored : SERVERS_HREF;
}
