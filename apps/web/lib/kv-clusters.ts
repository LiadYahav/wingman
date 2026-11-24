/**
 * A seed's KV clusters in the order create-vm fills them (ADR-0069), from the
 * clusters list alone: each KV cluster's `kv.workers` (its NodePools'
 * replicas) and its zone check (ADR-0067's 2026-11-24 amendment).
 *
 * create-vm places a zone's VMs first fit, oldest first by the name's id
 * letter (AD33), on KV clusters whose NodePools name the zone; one holds at
 * most the capacity policy's `maxNodes` (40). So, in that order: **Full** at
 * 40 or more, **Filling** the oldest under 40 (where the next VMs go), **Next**
 * every one after it (next in line; Wingman cannot see VMs, so never "empty").
 * A zone with no Next has no standby: when the filling one is full, create-vm
 * has nowhere to put the zone's VMs (the capacity controller's
 * `KvccNoStandby`). Pure: nothing is read here.
 */

import type { ClusterStatus } from "@/types";

/** The capacity policy's `maxNodes`, when a row does not say (day1 sends it as `kv.max_workers`). */
export const MAX_KV_WORKERS = 40;

export type FillState = "full" | "filling" | "next";

export const FILL_LABELS: Record<FillState, { label: string; hint: string }> = {
  full: { label: "Full", hint: "At the capacity policy's most workers: create-vm places no more VMs here." },
  filling: { label: "Filling", hint: "The oldest KV cluster with room: create-vm places the zone's next VMs here." },
  next: { label: "Next", hint: "Next in line: create-vm fills it once the ones before it are full." },
};

export interface FillEntry {
  cluster: ClusterStatus;
  /** Its place in the fill order, 1 first. */
  place: number;
  state: FillState;
  workers: number;
  maxWorkers: number;
}

/** One zone's KV clusters on a seed. */
export interface ZoneChain {
  /** The KV clusters' zone; `null` when neither their names nor the seed's give one. */
  zone: string | null;
  /** In fill order. */
  entries: FillEntry[];
  /** Never offered to placement: NodePools that miss the zone, or a file that does not parse. */
  apart: ClusterStatus[];
}

const ID_LAST = "~"; // after every letter: a name with no id letter is placed last

/** Oldest first: by the name's id letter, then by name. */
function byIdLetter(a: ClusterStatus, b: ClusterStatus): number {
  const left = a.naming.sequence ?? ID_LAST;
  const right = b.naming.sequence ?? ID_LAST;
  return left === right ? a.name.localeCompare(b.name, undefined, { numeric: true }) : left < right ? -1 : 1;
}

const offered = (cluster: ClusterStatus) => cluster.kv != null && cluster.kv.zone_problems.length === 0;

function fillOrder(clusters: ClusterStatus[]): FillEntry[] {
  let filling = false;
  return [...clusters].sort(byIdLetter).map((cluster, index) => {
    const workers = cluster.kv?.workers ?? 0;
    const maxWorkers = cluster.kv?.max_workers ?? MAX_KV_WORKERS;
    let state: FillState = "full";
    if (workers < maxWorkers) {
      state = filling ? "next" : "filling";
      filling = true;
    }
    return { cluster, place: index + 1, state, workers, maxWorkers };
  });
}

/** A seed's KV clusters by zone (the seed's when a name gives none), each zone in its fill order. */
export function zoneChains(clusters: readonly ClusterStatus[], seedZone: string | null): ZoneChain[] {
  const zones = new Map<string | null, ClusterStatus[]>();
  for (const cluster of clusters) {
    const zone = cluster.naming.zone ?? seedZone;
    zones.set(zone, [...(zones.get(zone) ?? []), cluster]);
  }
  if (zones.size === 0) zones.set(seedZone, []);
  return [...zones.entries()]
    .sort(([a], [b]) => (a ?? ID_LAST).localeCompare(b ?? ID_LAST))
    .map(([zone, members]) => ({
      zone,
      entries: fillOrder(members.filter(offered)),
      apart: members.filter((c) => !offered(c)).sort(byIdLetter),
    }));
}

/** The KV cluster the zone's next VMs go to, if one has room. */
export const fillingOf = (chain: ZoneChain): FillEntry | undefined => chain.entries.find((e) => e.state === "filling");

/** Why the zone has no standby, in words; `null` while a KV cluster is next in line. */
export function noStandbyWarning(chain: ZoneChain): string | null {
  if (chain.entries.some((e) => e.state === "next")) return null;
  const zone = chain.zone ? `${chain.zone}'s` : "this seed's";
  const filling = fillingOf(chain);
  if (filling) return `When ${filling.cluster.name} fills up, create-vm has nowhere to put ${zone} VMs.`;
  if (chain.entries.length > 0) return `Every KV cluster here is full: create-vm has nowhere to put ${zone} VMs.`;
  return `No KV cluster here takes VMs: create-vm has nowhere to put ${zone} VMs.`;
}

/** `1st`, `2nd`, `3rd`, `4th`, ..., `11th`, `21st`. */
export function ordinal(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13;
  const suffix = teen ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}
