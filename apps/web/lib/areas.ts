/**
 * Wingman's areas (ADR-0047; the single-pane plan's workstream 2): the top
 * bar switches between them. Only the areas that exist are listed; Servers
 * joins when it is built.
 */

export type AreaId = "wingman" | "segments";

export interface Area {
  id: AreaId;
  label: string;
  href: string;
}

const WINGMAN: Area = { id: "wingman", label: "Wingman", href: "/" };
const SEGMENTS: Area = { id: "segments", label: "Segments", href: "/segments" };

/** The area a page belongs to: its first path segment; every other page is Wingman's. */
export function areaOf(pathname: string): AreaId {
  return pathname === SEGMENTS.href || pathname.startsWith(`${SEGMENTS.href}/`) ? "segments" : "wingman";
}

/** The areas this person has, in the switch's order. */
export function areasFor({ segments }: { segments: boolean }): Area[] {
  return segments ? [WINGMAN, SEGMENTS] : [WINGMAN];
}
