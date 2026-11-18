/**
 * How tall a box may be so its page never scrolls: the Servers table's and
 * the Events table's own scroll boxes, and the cluster sidebar beside the
 * table (ADR-0048's v6.6.0 amendment).
 *
 * Ported from team-redbull/server-scan (decision 18): `lib/useFillViewport.ts`
 * (v6.4.0's f80ffb9, v6.6.0's 55b6391) and `ClusterSidebar.tsx`'s room at the
 * bottom. There the window scrolls; in Wingman the page scrolls inside the
 * shell's `main`, so the room is `main`'s height, not the window's.
 *
 * What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
 */

/** A box never gets shorter than this, even in a short window: the page then scrolls a little. */
export const FILL_MIN_HEIGHT = 240;

/** What a box's height is measured from, in pixels. */
export interface FillRoom {
  /** `main`'s visible height. */
  main: number;
  /** Where the box starts in `main`'s content (its offset from the content's top, not from the scroll). */
  top: number;
  /** What must stay under it: the rest of its column (a pager) and the page's bottom padding. */
  under: number;
}

/** The box's largest height: what is left of `main` under its top and above what follows it. */
export function fillHeight({ main, top, under }: FillRoom, min: number = FILL_MIN_HEIGHT): number {
  return Math.max(min, Math.round(main - top - under));
}
