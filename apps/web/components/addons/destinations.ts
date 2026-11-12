import type { DestinationState, ScopeDestination, ScopePanel } from "@/types/day2";

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
    description: "exclusions.yaml keeps the default off it: no app.",
  },
  "own-deploy": {
    label: "own deploy config",
    tone: "bg-chart-5/12 text-chart-5",
    description: "Excluded from the default, and deployed from its own folder with its own deploy config.",
  },
  "own-folder": {
    label: "own folder (an add-on)",
    tone: "bg-primary/12 text-primary",
    description: "Not a default here: the cluster has the chart in its own folder, managed from its page.",
  },
  duplicate: {
    label: "duplicate: generated twice",
    tone: "bg-status-error/12 text-status-error-fg",
    description:
      "A default and its own folder, not excluded: the platform generates the same app twice. Exclude it to keep only its own folder's app, or remove its own folder.",
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

/** The scope's destinations the default skips today, by id. */
export function excludedIds(panel: ScopePanel): Set<string> {
  const names = new Set(panel.exclusions?.names ?? []);
  return new Set(
    panel.destinations
      .filter((d) => d.state === "excluded" || d.state === "own-deploy" || (d.state === "not-rendered" && names.has(d.name)))
      .map((d) => d.id),
  );
}

/** Why a destination's "deployed by this default" checkbox cannot be changed, or `null`. */
export function lockedReason(d: ScopeDestination): string | null {
  if (d.state === "own-deploy")
    return `Deployed from its own folder${d.own_folder ? ` (${d.own_folder})` : ""} with its own deploy config: remove that to put it back under the default.`;
  if (d.state === "not-rendered") return "day1 has no version for it: the platform renders nothing there, default or not.";
  if (d.state === "own-folder" || d.state === "none") return "Not a default here.";
  return null;
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

/** A destination's id or name, as a plan or a list names it. */
export function nameOf(panel: ScopePanel, id: string): string {
  return panel.destinations.find((d) => d.id === id)?.name ?? id;
}
