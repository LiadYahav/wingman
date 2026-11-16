"use client";

import { useId, useState } from "react";
import { Info, Plus } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Hint } from "@/components/common/hint";
import { useCandidates } from "@/lib/api/inventory";
import { hardwareLabel } from "@/lib/inventory/pools";
import { cn } from "@/lib/utils";
import type { InstallTarget } from "@/lib/inventory/install";
import type { PoolCount } from "@/types/inventory";
import { CandidateList } from "./candidate-list";

/** A pool row's columns, for the list's row under it. */
const POOL_COLUMNS = 7;

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

/** A count that opens the pool's servers: either count opens the one list, both groups in it. */
function CountButton({
  count,
  label,
  open,
  controls,
  onToggle,
  className,
}: {
  count: number;
  label: string;
  open: boolean;
  controls: string;
  onToggle: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls={open ? controls : undefined}
      aria-label={label}
      className={cn(
        "min-h-6 min-w-6 rounded tabular-nums underline decoration-dotted decoration-from-font underline-offset-4 outline-none",
        "hover:text-foreground hover:decoration-solid focus-visible:ring-2 focus-visible:ring-ring/50",
        open && "font-semibold decoration-solid",
        className
      )}
    >
      {count}
    </button>
  );
}

const Dash = () => <span className="text-muted-foreground">—</span>;

/**
 * One InfraEnv pool: its available Agents, then the free servers server-scan
 * has for it, ready or needing a fix (either opens the list), and its total.
 */
export function PoolRow({ mce, pool, canAdd, onAdd }: { mce: string; pool: PoolCount; canAdd: boolean; onAdd: (t: InstallTarget) => void }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const infraEnv = pool.infra_env;
  const toggle = () => setOpen((now) => !now);
  const fix = pool.needs_fix ?? 0;
  return (
    <>
      <tr data-testid="pool-row" data-pool={infraEnv ?? ""} className={cn("align-middle", open && "bg-muted/40")}>
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
        <td className="py-1.5 pr-3" data-testid="pool-ready">
          {infraEnv !== null && pool.ready !== null ? (
            <CountButton count={pool.ready} label={`${pool.ready} ready in server-scan for ${infraEnv}`} open={open} controls={listId} onToggle={toggle} />
          ) : (
            <Dash />
          )}
        </td>
        <td className="py-1.5 pr-3" data-testid="pool-needs-fix">
          {infraEnv !== null && pool.needs_fix !== null ? (
            <CountButton
              count={fix}
              label={`${fix} ${fix === 1 ? "needs" : "need"} a fix for ${infraEnv}`}
              open={open}
              controls={listId}
              onToggle={toggle}
              className={fix > 0 ? "text-status-warning-fg" : "text-muted-foreground"}
            />
          ) : (
            <Dash />
          )}
        </td>
        <td className="py-1.5 pr-3 font-medium tabular-nums" data-testid="pool-total">{pool.total}</td>
        <td className="py-1.5 text-right">
          {canAdd && infraEnv !== null && (
            <button
              type="button"
              onClick={() => onAdd({ mce, infraEnv })}
              className={buttonVariants({ variant: "outline", size: "xs" })}
              aria-label={`Install servers into ${infraEnv}`}
            >
              <Plus aria-hidden className="h-3 w-3" /> Install
            </button>
          )}
        </td>
      </tr>
      {open && infraEnv !== null && (
        <tr id={listId}>
          <td colSpan={POOL_COLUMNS} className="pb-2">
            <PoolServers mce={mce} infraEnv={infraEnv} />
          </td>
        </tr>
      )}
    </>
  );
}
