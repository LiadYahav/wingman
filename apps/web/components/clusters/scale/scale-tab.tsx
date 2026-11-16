"use client";

import { createContext, useContext } from "react";
import { useScaleBusy, useScaleOptions } from "@/lib/scale";
import { useScaleChange, type ScaleChangeState } from "@/lib/scale-change";
import { changeLabel, changeWords, MAX_REPLICAS } from "@/lib/scale-model";
import type { ScaleOptions } from "@/types";

/** Where the Nodes tab says, once, why nothing can be scaled now; every stepper points there. */
export const BUSY_ID = "scale-busy-reason";

/** What every Scale control on the Nodes tab shares: the day1 file's NodePools, the one change, and why it waits. */
export interface ScaleTabValue {
  cluster: { name: string; where: string };
  options: ScaleOptions;
  isAdmin: boolean;
  /** Why nothing can start now (a run of the cluster is going); `null` when something can. */
  busy: string | null;
  state: ScaleChangeState;
}

const ScaleTabContext = createContext<ScaleTabValue | null>(null);

/** The Nodes tab's Scale, or `null` while scaling is off or not read yet. */
export function useScaleTab(): ScaleTabValue | null {
  return useContext(ScaleTabContext);
}

/** The change in words, for the one live region: `zone-a: 2 → 3 (+1)`. */
function announcement({ state }: ScaleTabValue): string {
  const { change, current, asked } = state;
  if (!change) return "";
  if (asked === null) return `${changeLabel(change)}: replicas are a whole number from 0 to ${MAX_REPLICAS}.`;
  return `${changeLabel(change)}: ${changeWords(current, asked)}`;
}

/**
 * Scale's state for the whole Nodes tab (ADR-0062, its 2026-11-16
 * amendment): the NodePool cards, the NodePool sizes and the hardware type
 * dialog share one change, so changing any stepper puts every other back.
 * The change is announced from one place. Nothing while scaling is off.
 */
export function ScaleTab({
  name,
  where,
  isAdmin,
  enabled = true,
  children,
}: {
  name: string;
  where: string;
  isAdmin: boolean;
  enabled?: boolean;
  children: React.ReactNode;
}) {
  const read = useScaleOptions(name, where, { enabled });
  const options = read.data?.state === "on" ? read.data.options : null;
  const busy = useScaleBusy(name, where);
  const state = useScaleChange(name, where, options);
  const value: ScaleTabValue | null = options ? { cluster: { name, where }, options, isAdmin, busy, state } : null;
  return (
    <ScaleTabContext.Provider value={value}>
      {children}
      {value && isAdmin && (
        <p role="status" className="sr-only" data-testid="scale-announce">
          {announcement(value)}
        </p>
      )}
    </ScaleTabContext.Provider>
  );
}
