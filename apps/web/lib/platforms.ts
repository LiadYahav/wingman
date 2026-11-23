/**
 * The top bar's platforms: Wingman, then the systems the team keeps apart
 * from it, segments-manager and server-scan (ADR-0066), each a link to its own UI in a new tab. Wingman's
 * brand also says who built it.
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

/** The top bar's word for each system beside Wingman. */
const LABELS: Record<Platform["id"], string> = { segments: "Segments", "server-scan": "Server Scan" };

/** One entry of the top bar's switch: Wingman's home, or another system's own UI in a new tab. */
export interface SwitchEntry {
  id: "wingman" | Platform["id"];
  label: string;
  href: string;
  /** `href` is the system's own UI, opened in a new tab; else Wingman's home. */
  external: boolean;
}

/**
 * The switch's entries: Wingman's, then each system day1 lists (`GET
 * /api/day1/platforms`, admins only, so a viewer's list is empty) whose UI
 * it knows, in day1's order.
 */
export function switchEntries(platforms: readonly Platform[]): SwitchEntry[] {
  const others = platforms
    .filter((platform) => platform.url)
    .map((platform) => ({ id: platform.id, label: LABELS[platform.id], href: platform.url, external: true }));
  return [{ id: "wingman", label: WINGMAN.label, href: WINGMAN.href, external: false }, ...others];
}
