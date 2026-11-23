"use client";

import { useId } from "react";
import { ChevronRight, FileText, Info } from "lucide-react";
import { Hint } from "@/components/common/hint";
import { cn } from "@/lib/utils";
import { totalSum } from "@/lib/inventory/waiver";
import type { InstallTarget } from "@/lib/inventory/install";
import type { MceInventory } from "@/types/inventory";
import { PoolRow } from "./pool-row";

function HeaderHint({ label, hint }: { label: string; hint: string }) {
  return (
    <span className="inline-flex items-center gap-0.5">
      {label}
      <Hint hint={hint} label={`About ${label}`}>
        <Info aria-hidden className="h-3 w-3" />
      </Hint>
    </span>
  );
}

const READY_HINT =
  "Free servers in server-scan named for this pool (ocp-<flavor>-<size>-<site>-…, from its InfraEnv's agentLabels) that a pool draw could pick today: healthy and reachable, unlocked, out of maintenance. The workflow still checks each one itself (its NICs' links, a live recheck), so a run may still refuse one. A dash: its agentLabels are unknown, or name no servers.";
const NEEDS_FIX_HINT =
  "Free servers named for this pool that a pool draw never picks: server-scan does not call them healthy, or cannot reach their BMC. An admin may install one by name, with the workflow's health checks waived, after confirming.";
const TOTAL_HINT =
  "Available + Ready + Needs fix: what this pool reaches once every free server named for it is fixed and installed. Locked, in-maintenance and contested servers are not counted.";

/**
 * Where the pools come from when the MCE's own InfraEnv list is unknown (live
 * status off, or its hub unreadable): the InfraEnvs its cluster files name.
 */
function PoolsFromDay1({ mce }: { mce: MceInventory }) {
  if (mce.infra_envs_from !== "day1") return null;
  const why = mce.infra_envs_error ?? "The MCE's own InfraEnv list is not read here.";
  return (
    <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground" data-testid="mce-pools-from-day1">
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

/** The card's counts line: shown collapsed too, so a collapsed MCE still says what it has. */
function Counts({ mce }: { mce: MceInventory }) {
  if (!mce.known) {
    return (
      <p className="text-xs text-muted-foreground">
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

/**
 * One MCE: its counts, then a row per InfraEnv pool. Its title collapses the
 * pools (`collapsed`, kept per viewer by the page) so the other MCEs fit.
 */
export function MceCard({
  mce,
  canAdd,
  onAdd,
  collapsed,
  onToggle,
}: {
  mce: MceInventory;
  canAdd: boolean;
  onAdd: (t: InstallTarget) => void;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const bodyId = useId();
  return (
    <section
      data-testid="mce-card"
      data-mce={mce.mce}
      data-collapsed={collapsed}
      aria-label={mce.mce}
      className="rounded-xl border bg-card px-4 py-3"
    >
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h3>
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={!collapsed}
            aria-controls={bodyId}
            data-testid="mce-toggle"
            className="-mx-1.5 inline-flex min-h-8 items-center gap-1.5 rounded-md px-1.5 text-left font-mono text-sm font-medium outline-none transition-colors hover:bg-muted/70 focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            <ChevronRight
              aria-hidden
              className={cn(
                "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-150 ease-out motion-reduce:transition-none",
                !collapsed && "rotate-90"
              )}
            />
            <span>{mce.mce}</span>
          </button>
        </h3>
        <Counts mce={mce} />
      </header>
      <div id={bodyId} hidden={collapsed}>
        <PoolsFromDay1 mce={mce} />
        {mce.pools.length > 0 && (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-sm" aria-label={`Pools on ${mce.mce}`}>
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th className="pb-1 pr-3 font-medium">InfraEnv</th>
                  <th className="pb-1 pr-3 font-medium">
                    <HeaderHint label="Available" hint="Agents in this MCE's inventory and in no cluster (server-scan's INSTALLED_TO_INVENTORY)." />
                  </th>
                  <th className="pb-1 pr-3 font-medium">Hardware</th>
                  <th className="pb-1 pr-3 font-medium">
                    <HeaderHint label="Ready" hint={READY_HINT} />
                  </th>
                  <th className="pb-1 pr-3 font-medium">
                    <HeaderHint label="Needs fix" hint={NEEDS_FIX_HINT} />
                  </th>
                  <th className="pb-1 pr-3 font-medium">
                    <HeaderHint label="Total" hint={TOTAL_HINT} />
                  </th>
                  <th className={cn("pb-1", !canAdd && "w-0")}><span className="sr-only">Install</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {mce.pools.map((pool) => (
                  <PoolRow key={pool.infra_env ?? ""} mce={mce.mce} pool={pool} canAdd={canAdd} onAdd={onAdd} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
