/**
 * server-scan's architecture diagrams (docs/notes/2026-11-13-server-scan-area-api.md
 * §11, ADR-0048's 3.28.0 amendment). The diagrams themselves are server-scan's,
 * read through day1 from its UI each time, never copied; this is only the
 * picker's list, which server-scan keeps in its frontend and serves nowhere.
 *
 * Reused from team-redbull/server-scan at 92146d3 (decision 18):
 * `frontend/src/features/architecture/diagrams.ts`, its slugs, labels and
 * descriptions as they are. A diagram server-scan adds is one entry here; one
 * it drops answers 404 and its tab says so.
 */

import { areaById } from "@/lib/areas";

export interface DiagramSpec {
  slug: string;
  label: string;
  description: string;
}

export const DIAGRAMS: readonly DiagramSpec[] = [
  {
    slug: "runtime-architecture",
    label: "Full flow",
    description:
      "Every collector through Mongo, the prune and nodes-status jobs, Redis, the API, Prometheus, AD login and the UI, in one diagram.",
  },
  {
    slug: "ucs-central",
    label: "Cisco UCS Central",
    description:
      "Central login, per-domain UCS Manager sessions, the managed-object queries, then IngestService. Cisco BMCs are behind the fabric interconnects and are not probed.",
  },
  {
    slug: "intersight",
    label: "Cisco Intersight",
    description: "API-key request signing, the owner-relation resource walk, then IngestService.",
  },
  {
    slug: "openmanage",
    label: "Dell OpenManage",
    description:
      "OME for identity, each iDRAC's Redfish for hardware, joined before IngestService; a failed iDRAC becomes a stub with a reason.",
  },
  {
    slug: "oneview",
    label: "HPE OneView",
    description:
      "The one HPE source regardless of iLO generation, plus an unauthenticated iLO reachability probe, then IngestService.",
  },
  {
    slug: "redfish-standalone",
    label: "Redfish Standalone",
    description:
      "No manager: a fleet from an inventory file, one BMC at a time; every failed host becomes a stub, then IngestService.",
  },
  {
    slug: "nodes-status",
    label: "Nodes Status",
    description: "The nodes-status jobs that write Server.openshift directly, bypassing IngestService.",
  },
];

/** The page's address; the diagram shown is `?diagram=<slug>`, the first one without it. */
export const ARCHITECTURE_HREF = `${areaById("server-scan").href}/architecture`;

/** The diagram `?diagram=` names; anything else is the first, as server-scan does. */
export function diagramOf(slug: string | null): DiagramSpec {
  return DIAGRAMS.find((d) => d.slug === slug) ?? DIAGRAMS[0];
}

/** The page's address showing `slug`; the first diagram has no `?diagram=`. */
export function diagramHref(slug: string): string {
  return slug === DIAGRAMS[0].slug ? ARCHITECTURE_HREF : `${ARCHITECTURE_HREF}?diagram=${encodeURIComponent(slug)}`;
}

export type DiagramTheme = "light" | "dark";

/**
 * Tells the diagram Wingman's theme. server-scan passes `?theme=` in the
 * frame's address; Wingman's frame has its page as `srcdoc`, which has no
 * address, so the diagram falls back on the browser's colour preference. This
 * script, first in its head, answers that preference with Wingman's theme:
 * only the `prefers-color-scheme` queries, and through the browser's own
 * `matchMedia`, so the answer behaves as one. The diagram's own toggle still
 * switches it.
 */
export function withTheme(html: string, theme: DiagramTheme): string {
  const script =
    "<script>(function(){var m=window.matchMedia.bind(window);" +
    `window.matchMedia=function(q){var s=/prefers-color-scheme:\\s*(light|dark)/.exec(q);return s?m(s[1]==="${theme}"?"all":"not all"):m(q)}})()</script>`;
  const head = /<head(\s[^>]*)?>/i.exec(html);
  if (!head) return script + html;
  const at = head.index + head[0].length;
  return html.slice(0, at) + script + html.slice(at);
}
