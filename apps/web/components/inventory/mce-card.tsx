"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Info, Plus, TriangleAlert } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Hint } from "@/components/common/hint";
import { useCandidates } from "@/lib/api/inventory";
import { hardwareLabel } from "@/lib/inventory/pools";
import { cn } from "@/lib/utils";
import type { MceInventory, PoolCount } from "@/types/inventory";
import { CandidateList } from "./candidate-list";

/** Which pool's Add was pressed: the page opens the dialog for it. */
export interface PoolTarget {
  mce: string;
  infraEnv: string;
  drawable: number | null;
}

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

function Available({ pool }: { pool: PoolCount }) {
  const unusable = pool.available - pool.usable;
  return (
    <span className="inline-flex items-center gap-1 tabular-nums">
      {pool.available}
      {unusable > 0 && (
        <Hint
          hint="Counted as available, but server-scan says it cannot be used now: in maintenance, unreachable, stale, unhealthy or contested."
          label={`${unusable} not usable: why`}
        >
          <span className="text-[11px] text-status-warning-fg">{unusable} not usable</span>
        </Hint>
      )}
    </span>
  );
}

/** The pool's servers in no MCE, read when opened. */
function PoolServers({ mce, infraEnv }: { mce: string; infraEnv: string }) {
  const read = useCandidates(mce, infraEnv, { enabled: true });
  return <CandidateList infraEnv={infraEnv} candidates={read.data?.candidates} isLoading={read.isLoading} error={read.error} />;
}

function PoolRow({ mce, pool, canAdd, onAdd }: { mce: string; pool: PoolCount; canAdd: boolean; onAdd: (t: PoolTarget) => void }) {
  const [open, setOpen] = useState(false);
  const infraEnv = pool.infra_env;
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <>
      <tr data-testid="pool-row" data-pool={infraEnv ?? ""} className="align-middle">
        <td className="whitespace-nowrap py-1.5 pr-3 font-mono text-xs">
          {infraEnv ?? (
            <span className="inline-flex items-center gap-1 font-sans text-muted-foreground">
              No InfraEnv
              <Hint hint="Available in server-scan, but the server's name starts with no InfraEnv on this MCE." label="About no InfraEnv">
                <Info aria-hidden className="h-3 w-3" />
              </Hint>
            </span>
          )}
        </td>
        <td className="py-1.5 pr-3" data-testid="pool-available"><Available pool={pool} /></td>
        <td className="py-1.5 pr-3 text-xs text-muted-foreground">
          {pool.hardware.map((h) => `${hardwareLabel(h)} ×${h.available}`).join(", ") || "—"}
        </td>
        <td className="py-1.5 pr-3 text-xs">
          {infraEnv !== null && pool.drawable !== null ? (
            <button
              type="button"
              onClick={() => setOpen((now) => !now)}
              aria-expanded={open}
              aria-label={`${pool.drawable} free in server-scan for ${infraEnv}`}
              className="inline-flex items-center gap-0.5 rounded tabular-nums hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 outline-none"
            >
              <Chevron aria-hidden className="h-3 w-3" />
              {pool.drawable}
            </button>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </td>
        <td className="py-1.5 text-right">
          {canAdd && infraEnv !== null && (
            <button
              type="button"
              onClick={() => onAdd({ mce, infraEnv, drawable: pool.drawable })}
              className={buttonVariants({ variant: "outline", size: "xs" })}
              aria-label={`Add servers to ${infraEnv}`}
            >
              <Plus aria-hidden className="h-3 w-3" /> Add
            </button>
          )}
        </td>
      </tr>
      {open && infraEnv !== null && (
        <tr>
          <td colSpan={5} className="pb-2">
            <PoolServers mce={mce} infraEnv={infraEnv} />
          </td>
        </tr>
      )}
    </>
  );
}

/** One MCE: its available Agents, then a row per InfraEnv pool. */
export function MceCard({ mce, canAdd, onAdd }: { mce: MceInventory; canAdd: boolean; onAdd: (t: PoolTarget) => void }) {
  return (
    <section data-testid="mce-card" data-mce={mce.mce} aria-label={mce.mce} className="rounded-xl border bg-card px-4 py-3">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="font-mono text-sm font-medium">{mce.mce}</h3>
        <p className="flex items-baseline gap-3 text-xs text-muted-foreground">
          {mce.known ? (
            <>
              <span data-testid="mce-available">
                <span className="text-lg font-semibold tabular-nums text-foreground">{mce.available}</span> available
              </span>
              <span>{mce.in_clusters} in clusters</span>
            </>
          ) : (
            <Hint hint="server-scan names no server on this MCE, so its counts are unknown." label="Unknown in server-scan">
              <span>not in server-scan</span>
            </Hint>
          )}
        </p>
      </header>
      {mce.infra_envs_error && (
        <p className="mt-1 flex items-center gap-1.5 text-xs text-status-warning-fg" data-testid="mce-infra-envs-error">
          <TriangleAlert aria-hidden className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate" title={mce.infra_envs_error}>InfraEnvs unknown: {mce.infra_envs_error}</span>
        </p>
      )}
      {mce.pools.length > 0 && (
        <table className="mt-2 w-full text-sm" aria-label={`Pools on ${mce.mce}`}>
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <th className="pb-1 pr-3 font-medium">InfraEnv</th>
              <th className="pb-1 pr-3 font-medium">
                <HeaderHint label="Available" hint="Agents in this MCE's inventory and in no cluster (server-scan's INSTALLED_TO_INVENTORY)." />
              </th>
              <th className="pb-1 pr-3 font-medium">Hardware</th>
              <th className="pb-1 pr-3 font-medium">
                <HeaderHint label="Free" hint="Servers in server-scan, not yet in this pool, that Add could pick." />
              </th>
              <th className={cn("pb-1", !canAdd && "w-0")}><span className="sr-only">Add</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {mce.pools.map((pool) => (
              <PoolRow key={pool.infra_env ?? ""} mce={mce.mce} pool={pool} canAdd={canAdd} onAdd={onAdd} />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
