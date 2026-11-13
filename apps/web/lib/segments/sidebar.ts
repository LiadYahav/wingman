/**
 * The Segments area's sidebar (ADR-0047's amendment). segments-manager's UI
 * has no sidebar: its entries are the page's own options, each a link that
 * sets the page's URL filters (the rest of the view stays), marked active
 * from the URL.
 */

import type { NavSection } from "@/lib/areas";
import type { SiteSegmentStats } from "@/types/segments";
import { siteCard } from "./sites";
import { viewHref, type SegmentsView, type StatusTab } from "./view";

/** Where the Documentation entry goes: Wingman's docs page (it has no Segments part yet). */
const DOCS_HREF = "/docs";

/** The sites' counts: read, still loading, or failed. */
export type SitesState = { sites: SiteSegmentStats[] } | "loading" | "error";

/** The status presets: each sets the status and turns "Disagrees with Git" off; that one is its own. */
function segmentsSection(view: SegmentsView): NavSection {
  const preset = (key: string, label: string, status: StatusTab, icon: "all" | "available" | "allocated") => ({
    key,
    label,
    icon,
    href: viewHref({ ...view, status, mismatch: false }),
    active: view.status === status && !view.mismatch,
  });
  return {
    label: "Segments",
    items: [
      preset("all", "All", "all", "all"),
      preset("available", "Available", "available", "available"),
      preset("allocated", "Allocated", "allocated", "allocated"),
      {
        key: "mismatch",
        label: "Disagrees with Git",
        icon: "mismatch",
        href: viewHref({ ...view, status: "all", mismatch: true }),
        active: view.mismatch && view.status === "all",
      },
    ],
  };
}

/** One entry per site, sites without segments too; the active one's link clears it, as its card does. */
function sitesSection(view: SegmentsView, state: SitesState): NavSection {
  if (state === "loading") return { label: "Sites", items: [], note: "Loading…" };
  if (state === "error") return { label: "Sites", items: [], note: "The sites could not be read." };
  return {
    label: "Sites",
    items: state.sites.map((stats) => {
      const card = siteCard(stats);
      const active = view.site !== null && view.site.toLowerCase() === card.site.toLowerCase();
      return {
        key: `site:${card.site}`,
        label: card.site,
        icon: "site",
        href: viewHref({ ...view, site: active ? null : card.site }),
        active,
        meta: `${card.allocated}/${card.total}`,
        metaLabel: `${card.allocated} of ${card.total} segments allocated`,
      };
    }),
  };
}

export function segmentsSidebar(view: SegmentsView, sites: SitesState): NavSection[] {
  return [
    segmentsSection(view),
    sitesSection(view, sites),
    {
      label: "Help",
      items: [{ key: "docs", label: "Documentation", icon: "docs", href: DOCS_HREF, active: false }],
    },
  ];
}
