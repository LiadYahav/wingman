/**
 * Wingman's areas (ADR-0047 and its amendment, ADR-0048; the single-pane
 * plan's workstream 2): the platforms the top bar switches between. Each has its
 * own brand (top left) and its own sidebar; only the areas that exist are
 * listed. Since 2026-11-23 the team keeps segments-manager and server-scan
 * apart (both ADRs' amendments): while an area is off, its switch entry opens
 * the system's own UI in a new tab. Data only, so a new area is an entry here
 * and its sidebar's sections, not layout code.
 */

import type { Platform } from "@/types";

export type AreaId = "wingman" | "segments" | "server-scan";

/** Every area but Wingman's, which everyone has. */
type OtherAreaId = Exclude<AreaId, "wingman">;

/**
 * The mark beside an area's name: Wingman's logo, server-scan's own app icon,
 * or an icon (the layout maps the key).
 */
export type BrandMark = "wingman-logo" | "server-scan-icon" | "server";

export interface Area {
  id: AreaId;
  /** The top bar's word for it. */
  label: string;
  /** Its home: the brand and the switch open it. */
  href: string;
  /** What the top left shows while you are in it. */
  brand: { name: string; mark: BrandMark };
  /** Who built it, each with their years: five quick clicks on the brand show them. */
  credits: Credit[];
}

export interface Credit {
  name: string;
  years: string;
}

const ROI_BLUM: Credit = { name: "Roi Blum", years: "2024 – 2028" };

const WINGMAN: Area = {
  id: "wingman",
  label: "Wingman",
  href: "/",
  brand: { name: "Wingman", mark: "wingman-logo" },
  credits: [{ name: "Liad Yahav", years: "2024 – 2026" }, ROI_BLUM],
};
/** The original's header: a server-rack mark and "Segments Manager". */
const SEGMENTS: Area = {
  id: "segments",
  label: "Segments",
  href: "/segments",
  brand: { name: "Segments Manager", mark: "server" },
  credits: [ROI_BLUM, { name: "Itay Herzberg", years: "2026 – 2028" }],
};

/** server-scan's own app icon (its header shows the team's logo, not server-scan's) and its page title (ADR-0048). */
const SERVER_SCAN: Area = {
  id: "server-scan",
  label: "Server Scan",
  href: "/server-scan",
  brand: { name: "Server Scan", mark: "server-scan-icon" },
  credits: [ROI_BLUM, { name: "Tomer Karniol", years: "2025 – 2042" }],
};

const AREAS: Record<AreaId, Area> = { wingman: WINGMAN, segments: SEGMENTS, "server-scan": SERVER_SCAN };

/** Every area but Wingman's, in the switch's order. */
const OTHERS: (Area & { id: OtherAreaId })[] = [
  { ...SEGMENTS, id: "segments" },
  { ...SERVER_SCAN, id: "server-scan" },
];

export const areaById = (id: AreaId): Area => AREAS[id];

/**
 * Which areas this person has (Wingman's is everyone's): `true`, `false`, or
 * `undefined` while that is still being found out.
 */
export type AreaAccess = Partial<Record<OtherAreaId, boolean | undefined>>;

/** The area a page belongs to: its first path segment; every other page is Wingman's. */
export function areaOf(pathname: string): AreaId {
  return OTHERS.find((area) => pathname === area.href || pathname.startsWith(`${area.href}/`))?.id ?? "wingman";
}

/** One entry of the top bar's switch: an area here, or another system's own UI in a new tab. */
export interface SwitchEntry {
  id: AreaId;
  label: string;
  href: string;
  /** `href` is the system's own UI, opened in a new tab; else an area here. */
  external: boolean;
}

/**
 * The switch's entries, in its order: Wingman's, then each other platform's
 * area when this person has it (not yet while that is found out), else its
 * own UI while day1 says its area is off (`platforms`, from `GET
 * /api/day1/platforms`; admins only, so a viewer gets none). A system day1 is
 * not configured for has neither.
 */
export function switchEntries(access: AreaAccess, platforms: readonly Platform[] = []): SwitchEntry[] {
  const entries: SwitchEntry[] = [{ id: WINGMAN.id, label: WINGMAN.label, href: WINGMAN.href, external: false }];
  for (const area of OTHERS) {
    const platform = platforms.find((p) => p.id === area.id);
    if (access[area.id] === true) entries.push({ id: area.id, label: area.label, href: area.href, external: false });
    else if (platform && !platform.area && platform.url) entries.push({ id: area.id, label: area.label, href: platform.url, external: true });
  }
  return entries;
}

/**
 * Whose chrome (brand and sidebar) a page wears: its area's when this person
 * has that area, else Wingman's. While access is `undefined` (still being
 * found out) the page's own area is assumed, so an admin's Segments page does
 * not flash Wingman's sidebar; a viewer's turns Wingman's once known.
 */
export function chromeArea(pathname: string, access: AreaAccess): AreaId {
  const area = areaOf(pathname);
  return area !== "wingman" && access[area] === false ? "wingman" : area;
}

// ── A data-driven sidebar (every area but Wingman's, whose items stay in sidebar-nav.tsx) ──

/** An entry's icon; the layout maps each key to its icon. */
export type NavIcon = "all" | "available" | "allocated" | "mismatch" | "site" | "servers" | "confs" | "rules" | "events" | "jobs" | "docs" | "claude" | "architecture";

export interface NavItem {
  /** Unique in its section; also its test id. */
  key: string;
  label: string;
  href: string;
  icon: NavIcon;
  /** Marked as where you are. */
  active: boolean;
  /** A short figure at the end of the row, e.g. "10/12". */
  meta?: string;
  /** What `meta` means, for a title and screen readers. */
  metaLabel?: string;
}

export interface NavSection {
  label: string;
  items: NavItem[];
  /** Said instead of the items while they load or when they could not be read. */
  note?: string;
}
