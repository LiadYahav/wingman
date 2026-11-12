import type { DestinationState } from "@/types/day2";

/** How a destination's state reads beside it, and its tone. */
export const STATE_LABEL: Record<string, { label: string; tone: string; description: string }> = {
  default: {
    label: "deployed by the default",
    tone: "bg-status-ready/12 text-status-ready-fg",
    description: "The fleet default deploys it here.",
  },
  excluded: {
    label: "excluded",
    tone: "bg-muted text-muted-foreground",
    description: "The repo's exclusions.yaml keeps the default off it: no app. Wingman does not edit that file.",
  },
  "own-deploy": {
    label: "own deploy config",
    tone: "bg-chart-5/12 text-chart-5",
    description: "The repo's exclusions.yaml keeps the default off it, and it is deployed from its own folder.",
  },
  "own-folder": {
    label: "installed",
    tone: "bg-primary/12 text-primary",
    description: "Not a default here: installed in its own folder.",
  },
  duplicate: {
    label: "duplicate: generated twice",
    tone: "bg-status-error/12 text-status-error-fg",
    description:
      "A default and its own folder: the platform generates the same app twice. Remove its own folder (on the cluster's page).",
  },
  none: { label: "not deployed", tone: "bg-muted text-muted-foreground", description: "Not a default, no own folder." },
  "not-rendered": {
    label: "not rendered",
    tone: "bg-status-warning/12 text-status-warning-fg",
    description: "day1 has no version for it: the platform renders nothing there.",
  },
};

export function stateStyle(state: DestinationState) {
  return STATE_LABEL[state] ?? { label: state, tone: "bg-muted text-muted-foreground", description: `State "${state}"` };
}

/** Destinations by site and env (the hub alone), in a stable order. */
export function groupDestinations<T extends { site: string; env: string; name: string }>(items: readonly T[]): [string, T[]][] {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const key = item.site || item.env ? `${item.site || "no site"} · ${item.env || "no env"}` : "the hub";
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, list]) => [key, [...list].sort((a, b) => a.name.localeCompare(b.name))]);
}
