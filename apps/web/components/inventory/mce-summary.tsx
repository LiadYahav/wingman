"use client";

import { FileText, Info } from "lucide-react";
import { Combobox } from "@/components/ui/combobox";
import { Hint } from "@/components/common/hint";
import { mceOptions } from "@/lib/inventory/install";
import { totalSum } from "@/lib/inventory/waiver";
import type { MceInventory, UsedLabels } from "@/types/inventory";
import { UsedCount } from "./used-agents";

/**
 * Which MCE the page shows: day1's MCEs by site, each with its available
 * Agents, or "not in server-scan" for one server-scan names nothing on (still
 * pickable: its hub may list pools to fill).
 */
export function McePicker({ mces, value, onChange }: { mces: readonly MceInventory[]; value: string; onChange: (mce: string) => void }) {
  return (
    <Combobox
      options={mceOptions(mces)}
      value={value}
      onValueChange={(next) => next && onChange(next)}
      aria-label="MCE"
      searchPlaceholder="Find an MCE…"
      emptyMessage="No MCE matches."
      className="font-mono sm:w-80"
      data-testid="mce-picker"
    />
  );
}

/**
 * Where the pools come from when the MCE's own InfraEnv list is unknown (live
 * status off, or its hub unreadable): the InfraEnvs its cluster files name.
 */
export function PoolsFromDay1({ mce }: { mce: MceInventory }) {
  if (mce.infra_envs_from !== "day1") return null;
  const why = mce.infra_envs_error ?? "The MCE's own InfraEnv list is not read here.";
  return (
    <p className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="mce-pools-from-day1">
      <FileText aria-hidden className="h-3.5 w-3.5 shrink-0" />
      Pools named by this MCE&apos;s cluster files
      <Hint
        hint={`${why} The pools are the InfraEnvs its cluster files name. Without their agentLabels, which name a pool's servers, no free server is counted, and a pool lists every free server. Install servers takes any other InfraEnv too; the workflow checks the MCE has it.`}
        label="Why these pools"
      >
        <Info aria-hidden className="h-3 w-3" />
      </Hint>
    </p>
  );
}

/** The selected MCE's counts: its available Agents, herzi's used ones, those in clusters and its total. */
export function Counts({ mce, usedLabels }: { mce: MceInventory; usedLabels: UsedLabels }) {
  if (!mce.known) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="mce-unknown-counts">
        <Hint hint="server-scan names no server on this MCE, so its counts are unknown." label="Unknown in server-scan">
          <span>not in server-scan</span>
        </Hint>
      </p>
    );
  }
  return (
    <p className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
      <span data-testid="mce-available">
        <span className="text-lg font-semibold tabular-nums text-foreground">{mce.available}</span> available
      </span>
      <UsedCount labels={usedLabels} count={mce.used ?? 0} testId="mce-used" big />
      <span>{mce.in_clusters} in clusters</span>
      <span className="inline-flex items-center gap-0.5" data-testid="mce-total">
        <span>
          <span className="font-semibold tabular-nums text-foreground">{mce.total}</span> total
        </span>
        <Hint
          hint={`${totalSum(mce)}: what this MCE's pools reach once every free server named for them is fixed and installed. A free server named for two of its pools counts once; locked, in-maintenance and contested servers are not counted.`}
          label="About the total"
        >
          <Info aria-hidden className="h-3 w-3" />
        </Hint>
      </span>
    </p>
  );
}
