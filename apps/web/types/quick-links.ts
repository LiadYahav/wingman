/**
 * Quick Links: day1's launcher of the hub, every MCE and the team's own links
 * (docs/notes/2026-11-12-quick-links-api.md, ADR-0052). Admins only.
 */

// ── GET /api/day1/quick-links ─────────────────────────────────────────────────

/** One link of a card. A file card has one, with `label: null`; a generated card has `ArgoCD` then `Console`. */
export interface QuickLink {
  label: string | null;
  url: string;
  /** The URL whose answer is this link's status dot; `null`: no dot. */
  ping: string | null;
}

export interface QuickLinkCard {
  /** Stable: `cluster:<name>`, `file:<section slug>:<card slug>`. */
  id: string;
  name: string;
  description: string | null;
  /** An icon key (the note's §4); always set. */
  icon: string;
  /** The ArgoCD instance whose applications' counts the status read carries; `null`: no widget. */
  argocd: string | null;
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

// ── GET /api/day1/quick-links/status ──────────────────────────────────────────

export type LinkState = "up" | "down" | "unknown";

export interface LinkCheck {
  url: string;
  state: LinkState;
  /** Always set, short and lower-case: `answered 200`, `no answer within 3 s`. */
  reason: string;
  http_status: number | null;
  latency_ms: number | null;
  checked_at: string | null;
}

export interface ArgoSyncCounts {
  synced: number;
  out_of_sync: number;
  unknown: number;
}

export interface ArgoHealthCounts {
  healthy: number;
  progressing: number;
  degraded: number;
  missing: number;
  suspended: number;
  unknown: number;
}

export interface ArgoCounts {
  applications: number;
  sync: ArgoSyncCounts;
  health: ArgoHealthCounts;
}

export interface ArgoReading {
  instance: string;
  /** `null` when the read failed (`error` says why). */
  counts: ArgoCounts | null;
  error: string | null;
  checked_at: string | null;
}

export interface QuickLinksStatus {
  checks: LinkCheck[];
  argocd: ArgoReading[];
}
