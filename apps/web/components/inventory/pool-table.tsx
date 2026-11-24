"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, Info } from "lucide-react";
import { Hint } from "@/components/common/hint";
import { cn } from "@/lib/utils";
import type { InstallTarget } from "@/lib/inventory/install";
import type { PoolSort } from "@/lib/inventory/pool-filter";
import type { PoolCount, UsedLabels } from "@/types/inventory";
import { PoolRow } from "./pool-row";
import { DIVIDER, HEADER_CELL, STICKY_HEAD } from "./table-style";

const AVAILABLE_HINT = "Agents in this MCE's inventory and in no cluster (server-scan's INSTALLED_TO_INVENTORY).";
const READY_HINT =
  "Free servers in server-scan named for this pool (ocp-<flavor>-<size>-<site>-…, from its InfraEnv's agentLabels) that a pool draw could pick today: healthy and reachable, unlocked, out of maintenance. The workflow still checks each one itself (its NICs' links, a live recheck), so a run may still refuse one. A dash: its agentLabels are unknown, or name no servers.";
const NEEDS_FIX_HINT =
  "Free servers named for this pool that a pool draw never picks: server-scan does not call them healthy, or cannot reach their BMC. An admin may install one by name, with the workflow's health checks waived, after confirming.";
const TOTAL_HINT =
  "Available + Ready + Needs fix: what this pool reaches once every free server named for it is fixed and installed. Locked, in-maintenance and contested servers are not counted.";

function HeaderHint({ label, hint }: { label: string; hint: string }) {
  return (
    <Hint hint={hint} label={`About ${label}`}>
      <Info aria-hidden className="h-3 w-3 text-muted-foreground" />
    </Hint>
  );
}

/** A column the table sorts by: its name orders the rows, the arrow says which way. */
function SortButton({ label, by, sort, onSort }: { label: string; by: PoolSort; sort: PoolSort; onSort: (by: PoolSort) => void }) {
  const active = sort === by;
  const Arrow = !active ? ArrowUpDown : by === "name" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={() => onSort(by)}
      data-testid={`pool-sort-${by}`}
      className={cn(
        "-mx-1 inline-flex min-h-6 items-center gap-1 rounded px-1 outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
        active && "text-foreground"
      )}
    >
      {label}
      <Arrow aria-hidden className={cn("h-3 w-3", !active && "opacity-40")} />
    </button>
  );
}

/**
 * The selected MCE's pools, one row per InfraEnv, under a header that stays in
 * view while a long table scrolls inside its own frame (the page keeps its
 * width on a phone). Sorted by name, or by available, most first.
 */
export function PoolTable({
  mce,
  pools,
  usedLabels,
  canAdd,
  onAdd,
  sort,
  onSort,
}: {
  mce: string;
  pools: PoolCount[];
  usedLabels: UsedLabels;
  canAdd: boolean;
  onAdd: (t: InstallTarget) => void;
  sort: PoolSort;
  onSort: (by: PoolSort) => void;
}) {
  return (
    <div className="max-h-[min(70vh,48rem)] overflow-auto rounded-xl border bg-card" data-testid="pool-table">
      <table className="w-full border-collapse text-sm" aria-label={`Pools on ${mce}`}>
        <thead className={STICKY_HEAD}>
          <tr className={cn("border-b", DIVIDER.header)}>
            <th scope="col" className={HEADER_CELL} aria-sort={sort === "name" ? "ascending" : undefined}>
              <SortButton label="InfraEnv" by="name" sort={sort} onSort={onSort} />
            </th>
            <th scope="col" className={HEADER_CELL} aria-sort={sort === "available" ? "descending" : undefined}>
              <span className="inline-flex items-center gap-0.5">
                <SortButton label="Available" by="available" sort={sort} onSort={onSort} />
                <HeaderHint label="Available" hint={AVAILABLE_HINT} />
              </span>
            </th>
            <th scope="col" className={HEADER_CELL}>Hardware</th>
            {(
              [
                ["Ready", READY_HINT],
                ["Needs fix", NEEDS_FIX_HINT],
                ["Total", TOTAL_HINT],
              ] as const
            ).map(([label, hint]) => (
              <th key={label} scope="col" className={HEADER_CELL}>
                <span className="inline-flex items-center gap-0.5">
                  {label}
                  <HeaderHint label={label} hint={hint} />
                </span>
              </th>
            ))}
            <th scope="col" className={cn(HEADER_CELL, !canAdd && "w-0 px-0")}>
              <span className="sr-only">Install</span>
            </th>
          </tr>
        </thead>
        <tbody className={cn("divide-y", DIVIDER.rows)}>
          {pools.map((pool) => (
            <PoolRow key={pool.infra_env ?? ""} mce={mce} pool={pool} usedLabels={usedLabels} canAdd={canAdd} onAdd={onAdd} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
