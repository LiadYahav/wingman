"use client";

import { Lock } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { kindBlock, MAX_REPLICAS, nodepoolBlock, type ScaleMode } from "@/lib/scale-model";
import { cn, plural } from "@/lib/utils";
import type { ScaleKind, ScaleNodePool, ScaleOptions } from "@/types";

const rowClass = (selected: boolean, blocked: boolean) =>
  cn(
    "flex items-start gap-2.5 rounded-md px-2.5 py-2 text-sm",
    blocked ? "cursor-not-allowed text-muted-foreground" : "cursor-pointer hover:bg-muted/40",
    selected && "bg-primary/5 hover:bg-primary/5"
  );

/** Why a row cannot be chosen, under it, and read with it. */
function Blocked({ id, reason }: { id: string; reason: string | null }) {
  if (!reason) return null;
  return (
    <span id={id} className="mt-0.5 flex items-start gap-1 text-xs text-muted-foreground" data-testid="scale-blocked">
      <Lock className="mt-px h-3 w-3 shrink-0" aria-hidden />
      <span className="break-words">{reason}</span>
    </span>
  );
}

function KindRow({ kind, flavor, selected, onChoose }: { kind: ScaleKind; flavor: string | null; selected: boolean; onChoose: () => void }) {
  const blocked = kindBlock(kind, flavor);
  const id = `scale-kind-${kind.kind}`;
  return (
    <label className={rowClass(selected, blocked !== null)} data-testid="scale-kind" data-kind={kind.kind} data-blocked={blocked !== null}>
      <input
        type="radio"
        name="scale-kind"
        value={kind.kind}
        checked={selected}
        onChange={onChoose}
        disabled={blocked !== null}
        aria-describedby={blocked ? `${id}-why` : `${id}-pools`}
        className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline justify-between gap-x-3">
          <span className="font-mono font-medium break-all">{kind.kind}</span>
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
            {plural(kind.nodepools.length, "NodePool")} · {kind.total ?? "—"} replicas
          </span>
        </span>
        <span id={`${id}-pools`} className="mt-0.5 block font-mono text-[11px] text-muted-foreground break-all">
          {kind.nodepools.join(", ")}
        </span>
        <Blocked id={`${id}-why`} reason={blocked} />
      </span>
    </label>
  );
}

function NodePoolRow({ pool, selected, onChoose }: { pool: ScaleNodePool; selected: boolean; onChoose: () => void }) {
  const blocked = nodepoolBlock(pool);
  const id = `scale-pool-${pool.index}`;
  return (
    <label className={rowClass(selected, blocked !== null)} data-testid="scale-nodepool" data-nodepool={pool.name ?? ""} data-blocked={blocked !== null}>
      <input
        type="radio"
        name="scale-nodepool"
        value={pool.name ?? ""}
        checked={selected}
        onChange={onChoose}
        disabled={blocked !== null}
        aria-describedby={blocked ? `${id}-why` : undefined}
        className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline justify-between gap-x-3">
          <span className="font-mono font-medium break-all">{pool.name ?? `nodepool[${pool.index}]`}</span>
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{pool.replicas ?? "—"} replicas</span>
        </span>
        {pool.infra_env && <span className="mt-0.5 block font-mono text-[11px] text-muted-foreground break-all">{pool.infra_env}</span>}
        <Blocked id={`${id}-why`} reason={blocked} />
      </span>
    </label>
  );
}

/**
 * What to scale: a hardware kind (the total over the NodePools it selects,
 * spread by the workflow) or one NodePool (its replicas, set exactly), and
 * the number. A locked or unnamed target is shown, not offered, with why.
 */
export function ScaleChoice({
  options,
  mode,
  target,
  replicas,
  current,
  onMode,
  onTarget,
  onReplicas,
  disabled,
}: {
  options: ScaleOptions;
  mode: ScaleMode;
  target: string | null;
  replicas: number;
  /** The chosen target's replicas now. */
  current: number | null;
  onMode: (mode: ScaleMode) => void;
  onTarget: (target: string) => void;
  onReplicas: (replicas: number) => void;
  disabled: boolean;
}) {
  const byKind = mode === "kind";
  return (
    <div className="grid gap-3">
      <Tabs value={mode} onValueChange={(value) => onMode(value as ScaleMode)}>
        <TabsList aria-label="How to scale">
          <TabsTrigger value="kind" disabled={disabled} data-testid="scale-mode-kind">By hardware kind</TabsTrigger>
          <TabsTrigger value="nodepool" disabled={disabled} data-testid="scale-mode-nodepool">One NodePool</TabsTrigger>
        </TabsList>
      </Tabs>
      <p className="text-xs text-muted-foreground">
        {byKind
          ? "A total over the NodePools of one InfraEnv kind. update-nodepool spreads it so no two of them are more than one replica apart, and refuses NodePools already further apart."
          : "One NodePool's replicas, set exactly. Its siblings of the same kind keep theirs."}
      </p>
      <fieldset className="grid max-h-64 gap-0.5 overflow-y-auto rounded-lg border p-1" disabled={disabled}>
        <legend className="sr-only">{byKind ? "Hardware kind" : "NodePool"}</legend>
        {byKind
          ? options.kinds.map((k) => (
              <KindRow key={k.kind} kind={k} flavor={options.flavor} selected={target === k.kind} onChoose={() => onTarget(k.kind)} />
            ))
          : options.nodepools.map((p) => (
              <NodePoolRow key={p.index} pool={p} selected={p.name !== null && target === p.name} onChoose={() => p.name && onTarget(p.name)} />
            ))}
        {(byKind ? options.kinds : options.nodepools).length === 0 && (
          <p className="px-2.5 py-2 text-xs text-muted-foreground">
            {byKind ? "No NodePool of this cluster names an InfraEnv." : "The cluster file has no NodePool."}
          </p>
        )}
      </fieldset>
      <label className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-muted-foreground">{byKind ? "New total" : "Replicas"}</span>
        <input
          type="number"
          min={0}
          max={MAX_REPLICAS}
          step={1}
          value={Number.isNaN(replicas) ? "" : replicas}
          onChange={(e) => onReplicas(e.target.valueAsNumber)}
          aria-label={byKind ? "New total replicas of the kind" : "Replicas of the NodePool"}
          disabled={disabled || target === null}
          data-testid="scale-replicas"
          className="w-24 rounded-md border bg-background px-2.5 py-1.5 text-sm tabular-nums outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60"
        />
        {current !== null && <span className="text-xs text-muted-foreground tabular-nums">now {current}</span>}
      </label>
    </div>
  );
}
