/**
 * Wingman's brand, and the systems the team keeps apart from it,
 * segments-manager and server-scan (ADR-0066): the Infrastructure
 * workspace's sidebar links to each one's own UI in a new tab (ADR-0067).
 * Wingman's brand also says who built it.
 */

import type { Platform } from "@/types";

export interface Credit {
  name: string;
  years: string;
}

/** Wingman: its home, and who built it (five quick clicks on the brand show them). */
export const WINGMAN = {
  label: "Wingman",
  href: "/",
  credits: [
    { name: "Liad Yahav", years: "2024 – 2026" },
    { name: "Roi Blum", years: "2024 – 2028" },
  ] satisfies Credit[],
};

/** A link out of Wingman: another system's own UI, opened in a new tab. */
export interface LinkOut {
  id: Platform["id"];
  label: string;
  href: string;
}

/**
 * Each system day1 lists (`GET /api/day1/platforms`, admins only, so a
 * viewer's list is empty) whose UI it knows, in day1's order and under day1's
 * name for it.
 */
export function linksOut(platforms: readonly Platform[]): LinkOut[] {
  return platforms
    .filter((platform) => platform.url)
    .map((platform) => ({ id: platform.id, label: platform.name, href: platform.url }));
}
