/**
 * The machine configs a nodepool can name (`GET /api/day1/machine-configs`,
 * ADR-0027) and the rules day1 checks an entry by. Day1 is the authority: these
 * checks only give a form instant feedback, and every problem day1 returns is
 * still shown.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { ConfigEntry, MachineConfigs } from "@/types";

/** The entry name that stands for the cluster's own network config. */
export const NETWORK_CONFIG = "nm-conf";

export const machineConfigsKey = ["machine-configs"] as const;

/** The catalogue and the nodepool defaults; cached a minute, like day1's own read. */
export function useMachineConfigs(enabled = true) {
  return useQuery<MachineConfigs>({
    queryKey: machineConfigsKey,
    queryFn: () => api.get<MachineConfigs>("/api/day1/machine-configs"),
    staleTime: 60_000,
    enabled,
  });
}

export function isNetworkEntry(entry: ConfigEntry): boolean {
  return entry.name === NETWORK_CONFIG;
}

/** The name the CI resolves: `nm-conf-<clusterName>-<hw>` (clusterName without `ocp4-`). */
export function networkConfigName(clusterName: string, hardware: string): string {
  return `${NETWORK_CONFIG}-${clusterName}-${hardware}`;
}

/** What the cluster file will say for an entry; `null` while a network entry has no hardware. */
export function fileName(entry: ConfigEntry, clusterName?: string): string | null {
  if (!isNetworkEntry(entry)) return entry.name;
  if (!entry.hardware) return null;
  return networkConfigName(clusterName || "<cluster>", entry.hardware);
}

/** An entry as a request sends it: `hardware` only on `nm-conf`. */
export function cleanEntry(entry: ConfigEntry): ConfigEntry {
  return isNetworkEntry(entry) ? { name: NETWORK_CONFIG, hardware: entry.hardware ?? null } : { name: entry.name };
}

/** Copies of the defaults a new nodepool starts with; none when the file is missing or unusable. */
export function defaultConfigs(catalog: MachineConfigs | undefined): ConfigEntry[] {
  const defaults = catalog?.nodepool_defaults;
  if (!defaults || defaults.error) return [];
  return defaults.configs.map(cleanEntry);
}

/** Read a template input value as config entries; anything else in the list is dropped. */
export function asEntries(value: unknown): ConfigEntry[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item): ConfigEntry[] => {
    if (typeof item === "string") return item ? [{ name: item }] : [];
    if (item && typeof item === "object" && typeof (item as { name?: unknown }).name === "string") {
      const { name, hardware } = item as { name: string; hardware?: unknown };
      return [typeof hardware === "string" ? { name, hardware } : { name }];
    }
    return [];
  });
}

/**
 * The problems day1 would report for each entry, by index (§3 of the API
 * note): a network entry without a known hardware type, hardware on a static
 * config, a name `mc-files/` does not have, the same entry twice.
 *
 * `hardwareRequired: false` is for a list whose network entry takes each
 * nodepool's own hardware (the configs rule, ADR-0029): a missing hardware
 * type is then not a problem of the list.
 */
export function entryProblems(
  entries: ConfigEntry[],
  catalog: MachineConfigs | undefined,
  { hardwareRequired = true }: { hardwareRequired?: boolean } = {}
): string[][] {
  const hardware = new Set(catalog?.hardware_types.map((h) => h.name) ?? []);
  const known = new Set(catalog?.static_configs.map((c) => c.name) ?? []);
  const hardwareList = [...hardware].join(", ");
  const seen = new Map<string, number>();
  return entries.map((entry, index) => {
    const problems: string[] = [];
    if (!entry.name) problems.push("Choose a machine config");
    else if (isNetworkEntry(entry)) {
      if (!entry.hardware) {
        if (hardwareRequired) problems.push(`Choose the hardware type${hardwareList ? ` (${hardwareList})` : ""}`);
      } else if (catalog && !hardware.has(entry.hardware)) problems.push(`No hardware type '${entry.hardware}'`);
    } else {
      if (entry.hardware) problems.push(`Hardware applies only to ${NETWORK_CONFIG}`);
      if (catalog && !known.has(entry.name)) problems.push(`No machine config '${entry.name}' in mc-files/`);
    }
    const key = `${entry.name}\u0000${isNetworkEntry(entry) ? entry.hardware ?? "" : ""}`;
    const first = seen.get(key);
    if (entry.name && first !== undefined) problems.push(`The same config as entry ${first + 1}`);
    else seen.set(key, index);
    return problems;
  });
}

/** Two config lists name the same configs, each as often, in any order (the rule's comparison, ADR-0029). */
export function sameConfigs(a: ConfigEntry[], b: ConfigEntry[]): boolean {
  const key = (e: ConfigEntry) => (isNetworkEntry(e) ? NETWORK_CONFIG : e.name);
  const count = (entries: ConfigEntry[]) =>
    entries.reduce((m, e) => m.set(key(e), (m.get(key(e)) ?? 0) + 1), new Map<string, number>());
  const ca = count(a);
  const cb = count(b);
  return ca.size === cb.size && [...ca].every(([name, n]) => cb.get(name) === n);
}

/** `mc-files/` or `mc-files/<folder>/`: where a static config lives, for grouping the picker. */
export function folderLabel(folder: string): string {
  return folder ? `mc-files/${folder}/` : "mc-files/";
}
