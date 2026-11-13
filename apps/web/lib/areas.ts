/**
 * Wingman's areas (ADR-0047 and its amendment; the single-pane plan's
 * workstream 2): the platforms the top bar switches between. Each has its
 * own brand (top left) and its own sidebar; only the areas that exist are
 * listed. Data only, so a new area is an entry here and its sidebar's
 * sections, not layout code.
 */

export type AreaId = "wingman" | "segments";

/** The mark beside an area's name: Wingman's logo, or an icon (the layout maps the key). */
export type BrandMark = "wingman-logo" | "server";

export interface Area {
  id: AreaId;
  /** The top bar's word for it. */
  label: string;
  /** Its home: the brand and the switch open it. */
  href: string;
  /** What the top left shows while you are in it. */
  brand: { name: string; mark: BrandMark };
}

const WINGMAN: Area = { id: "wingman", label: "Wingman", href: "/", brand: { name: "Wingman", mark: "wingman-logo" } };
/** The original's header: a server-rack mark and "Segments Manager". */
const SEGMENTS: Area = {
  id: "segments",
  label: "Segments",
  href: "/segments",
  brand: { name: "Segments Manager", mark: "server" },
};

const AREAS: Record<AreaId, Area> = { wingman: WINGMAN, segments: SEGMENTS };

export const areaById = (id: AreaId): Area => AREAS[id];

/** The area a page belongs to: its first path segment; every other page is Wingman's. */
export function areaOf(pathname: string): AreaId {
  return pathname === SEGMENTS.href || pathname.startsWith(`${SEGMENTS.href}/`) ? "segments" : "wingman";
}

/** The areas this person has, in the switch's order. */
export function areasFor({ segments }: { segments: boolean }): Area[] {
  return segments ? [WINGMAN, SEGMENTS] : [WINGMAN];
}

/**
 * Whose chrome (brand and sidebar) a page wears: its area's when this person
 * has that area, else Wingman's. `segments` is `undefined` while that is
 * still being found out: the page's own area is assumed, so an admin's
 * Segments page does not flash Wingman's sidebar; a viewer's turns
 * Wingman's once known.
 */
export function chromeArea(pathname: string, { segments }: { segments: boolean | undefined }): AreaId {
  const area = areaOf(pathname);
  return area === "segments" && segments === false ? "wingman" : area;
}

// ── A data-driven sidebar (every area but Wingman's, whose items stay in sidebar-nav.tsx) ──

/** An entry's icon; the layout maps each key to its icon. */
export type NavIcon = "all" | "available" | "allocated" | "mismatch" | "site" | "docs";

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
