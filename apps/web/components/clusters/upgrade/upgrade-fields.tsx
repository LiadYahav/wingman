"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { UpgradeTargets } from "@/types";

/**
 * The Upgrade dialog's fields: the targets the workflow offers, the
 * NodePools' roll order and maxUnavailable, and the run's options. Only
 * what is changed from the workflow's defaults is sent.
 */

const INPUT =
  "w-16 rounded-md border bg-background px-2 py-1 font-mono text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60";

export function TargetList({
  targets,
  target,
  onChoose,
  disabled,
}: {
  targets: UpgradeTargets;
  target: string | null;
  onChoose: (version: string) => void;
  disabled: boolean;
}) {
  if (targets.targets.length === 0) {
    return (
      <p
        data-testid="upgrade-targets-empty"
        className="rounded-lg border bg-muted/30 px-3 py-2 text-sm"
        title="The workflow offers no ladder rung newer than the mastertag that this MCE supports, and does not say why. A run started toward an expected target would fail its planning, naming the rule."
      >
        Nothing newer to offer.
      </p>
    );
  }
  return (
    <fieldset className="grid gap-1" disabled={disabled}>
      <legend className="mb-1 text-xs font-medium text-muted-foreground">Target</legend>
      {targets.targets.map((t) => (
        <label
          key={t.version}
          data-testid="upgrade-target"
          className={cn(
            "flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm hover:bg-muted/40",
            target === t.version && "bg-primary/5 hover:bg-primary/5"
          )}
        >
          <input
            type="radio"
            name="upgrade-target"
            value={t.version}
            checked={target === t.version}
            onChange={() => onChoose(t.version)}
            className="h-4 w-4 accent-primary"
          />
          <span className="font-mono font-medium">{t.version}</span>
          <span className="text-xs text-muted-foreground" title="Control-plane steps, of every step the plan to it has">
            {t.control_plane_steps} control plane · {t.steps} steps
          </span>
          {t.newest_in_minor && (
            <span className="text-xs text-muted-foreground" title={`The newest rung of ${t.minor}: the pick for that minor`}>
              newest {t.minor}
            </span>
          )}
          {t.must && <span className="text-xs text-muted-foreground" title="A ladder rung no path skips">must</span>}
        </label>
      ))}
    </fieldset>
  );
}

/** The NodePools in roll order, each moved up or down, with its maxUnavailable. */
export function NodePoolOrder({
  order,
  zones,
  limits,
  onMove,
  onLimit,
  disabled,
}: {
  order: string[];
  zones: Record<string, string | null>;
  limits: Record<string, string>;
  onMove: (index: number, by: number) => void;
  onLimit: (pool: string, value: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="grid gap-1" data-testid="upgrade-nodepools">
      <p
        className="text-xs font-medium text-muted-foreground"
        title="The order NodePools roll in, one at a time, and how many nodes each takes down at once (inPlace.maxUnavailable, kept in the file). Sent only when changed."
      >
        NodePools, in roll order · max unavailable
      </p>
      <ol className="grid gap-1">
        {order.map((pool, i) => (
          <li key={pool} className="flex items-center gap-1.5 text-xs">
            <span className="min-w-0 flex-1 truncate font-mono" title={pool}>{pool}</span>
            {zones[pool] && <span className="text-muted-foreground">zone {zones[pool]}</span>}
            <button type="button" aria-label={`Move ${pool} up`} disabled={i === 0 || disabled} onClick={() => onMove(i, -1)} className={buttonVariants({ variant: "ghost", size: "icon-xs" })}>
              <ArrowUp aria-hidden />
            </button>
            <button type="button" aria-label={`Move ${pool} down`} disabled={i === order.length - 1 || disabled} onClick={() => onMove(i, 1)} className={buttonVariants({ variant: "ghost", size: "icon-xs" })}>
              <ArrowDown aria-hidden />
            </button>
            <input
              value={limits[pool] ?? ""}
              onChange={(e) => onLimit(pool, e.target.value)}
              placeholder="1"
              aria-label={`maxUnavailable of ${pool}`}
              disabled={disabled}
              className={INPUT}
            />
          </li>
        ))}
      </ol>
    </div>
  );
}

export interface Options {
  controlPlaneOnly: boolean;
  auto: boolean;
  autoApprove: boolean;
}

function Check({ checked, onChange, disabled, title, children }: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled: boolean;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex items-center gap-2" title={title}>
      <input type="checkbox" className="h-4 w-4 accent-primary" checked={checked} onChange={(e) => onChange(e.target.checked)} disabled={disabled} />
      {children}
    </label>
  );
}

/** Control plane only, and the two choices only lab and canary clusters may make. */
export function OptionsFields({ options, onChange, disabled }: { options: Options; onChange: (options: Options) => void; disabled: boolean }) {
  const set = (key: keyof Options) => (value: boolean) => onChange({ ...options, [key]: value });
  return (
    <div className="grid gap-2 text-sm">
      <Check checked={options.controlPlaneOnly} onChange={set("controlPlaneOnly")} disabled={disabled} title="workers_to_target: false. NodePools move only where the path forces it.">
        Control plane only
      </Check>
      <details className="text-sm">
        <summary className="cursor-pointer text-xs text-muted-foreground" title="The run's planning refuses these unless the cluster file says upgrade.wave 0 or 1.">
          Lab and canary clusters (upgrade.wave 0 or 1)
        </summary>
        <div className="mt-2 grid gap-2 pl-1">
          <Check checked={options.auto} onChange={set("auto")} disabled={disabled}>Roll each NodePool without a Continue</Check>
          <Check checked={options.autoApprove} onChange={set("autoApprove")} disabled={disabled}>Approve the plan automatically</Check>
        </div>
      </details>
    </div>
  );
}
