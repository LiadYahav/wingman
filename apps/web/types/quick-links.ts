/**
 * Quick Links: day1's launcher of the hub, every MCE and the team's own links
 * (docs/notes/2026-11-12-quick-links-api.md, ADR-0052). Admins only.
 */

// ── GET /api/day1/quick-links ─────────────────────────────────────────────────

/** One link of a card. A file card has one, with `label: null`; a generated card has `ArgoCD` then `Console`. */
export interface QuickLink {
  label: string | null;
  url: string;
}

export interface QuickLinkCard {
  /** Stable: `cluster:<name>`, `file:<section slug>:<card slug>`. */
  id: string;
  name: string;
  description: string | null;
  /** An icon key (the note's §4); always set. */
  icon: string;
  /** At least one; `links[0]` is the card's own link (its title opens it). */
  links: QuickLink[];
}

export interface QuickLinkSection {
  /** Stable: `hub`, `site:<site>`, `file:<slug>`. */
  id: string;
  name: string;
  description: string | null;
  /** Cards a row holds on a wide screen, 1 to 6. */
  columns: number;
  /** `true` for what Wingman generated, `false` for the links file's. */
  generated: boolean;
  cards: QuickLinkCard[];
}

export type LinksFileState = "loaded" | "missing" | "invalid";

export interface LinksFileInfo {
  path: string;
  state: LinksFileState;
  problems: string[];
}

export interface QuickLinks {
  sections: QuickLinkSection[];
  /** What Wingman could not generate, one sentence each. */
  problems: string[];
  links_file: LinksFileInfo;
}
