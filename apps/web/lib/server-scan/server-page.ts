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

/** Where a node's server name links, and what a screen reader hears for it. */
export interface NodeServerLink {
  href: string;
  /** Wingman's server page, followed in this tab; else server-scan's own page, in a new tab. */
  inApp: boolean;
  label: string;
}

/**
 * A server's link from a cluster's nodes (ADR-0048's 3.26.0 amendment): its
 * page here for whoever has the Server Scan area (`hasArea`, from
 * `useServerScanArea()`: `undefined` while that is found out), so a server
 * has one view; server-scan's own page (`url`, built by day1) for anyone
 * else, until RBAC opens the area to them.
 */
export function nodeServerLink(server: { id: string; name: string; url: string }, hasArea: boolean | undefined): NodeServerLink {
  return hasArea === true
    ? { href: serverHref(server.id), inApp: true, label: `${server.name}, its server page` }
    : { href: server.url, inApp: false, label: `${server.name}, its server-scan page (opens in a new tab)` };
}

/** Where "← Servers" goes: the Servers view the page was opened from, when it is one, else the unfiltered list. */
export function backHref(stored: string | null): string {
  if (!stored) return SERVERS_HREF;
  const [path] = stored.split(/[?#]/);
  return path === SERVERS_HREF ? stored : SERVERS_HREF;
}
