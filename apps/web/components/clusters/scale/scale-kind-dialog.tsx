"use client";

import { useState } from "react";
import { Lock, Server } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { changeWords, kindBlock, MAX_REPLICAS, totalKinds } from "@/lib/scale-model";
import { cn, plural } from "@/lib/utils";
import type { ScaleKind } from "@/types";
import { ReplicasStepper, stepperInputId } from "./replicas-stepper";
import { ScaleConfirmDialog } from "./scale-confirm-dialog";
import { ScaleButton } from "./scale-pending";
import { focusSoon, StartError } from "./scale-start";
import { BUSY_ID, useScaleTab, type ScaleTabValue } from "./scale-tab";

const sizeOf = (k: ScaleKind) => `${plural(k.nodepools.length, "NodePool")} · ${k.total === null ? "—" : plural(k.total, "replica")}`;

/** The hardware types to choose from, each with its size; a locked one is shown, not offered, with why. */
function KindChoice({ kinds, flavor, value, onChoose, disabled }: {
  kinds: ScaleKind[];
  flavor: string | null;
  value: string;
  onChoose: (kind: string) => void;
  disabled: boolean;
}) {
  return (
    <fieldset className="grid gap-1" disabled={disabled}>
      <legend className="mb-1.5 text-xs font-medium text-muted-foreground">Hardware type</legend>
      {kinds.map((k) => {
        const block = kindBlock(k, flavor);
        return (
          <label
            key={k.kind}
            data-testid="scale-kind"
            data-kind={k.kind}
            className={cn(
              "flex items-start gap-2.5 rounded-lg border px-3 py-2 text-sm transition-colors",
              block ? "cursor-not-allowed text-muted-foreground" : "cursor-pointer hover:bg-muted/50",
              value === k.kind && "border-primary/50 bg-primary/[0.05] hover:bg-primary/[0.05]"
            )}
          >
            <input
              type="radio"
              name="scale-kind"
              value={k.kind}
              checked={value === k.kind}
              onChange={() => onChoose(k.kind)}
              disabled={block !== null}
              aria-describedby={block ? `scale-kind-${k.kind}-why` : undefined}
              className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
            />
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className="font-mono font-medium break-all">{k.kind}</span>
                <span className="text-xs tabular-nums text-muted-foreground">{sizeOf(k)}</span>
              </span>
              {block && (
                <span id={`scale-kind-${k.kind}-why`} className="mt-0.5 flex items-start gap-1 text-xs">
                  <Lock className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                  {block}
                </span>
              )}
            </span>
          </label>
        );
      })}
    </fieldset>
  );
}

/**
 * The total of the chosen hardware type and the change from now: a stepper
 * while it can change, else the total as text, so a held one never looks
 * editable (why is said above it).
 */
function Total({ tab, kind, held, pending }: { tab: ScaleTabValue; kind: ScaleKind; held: boolean; pending: boolean }) {
  const { change, current, asked } = tab.state;
  const mine = change?.mode === "kind" && change.target === kind.kind;
  if (held) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="scale-kind-total">
        Total <span className="font-semibold text-foreground tabular-nums">{kind.total ?? "—"}</span>{" "}
        {kind.total === 1 ? "replica" : "replicas"}
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="text-sm text-muted-foreground" aria-hidden>
        Total
      </span>
      <ReplicasStepper
        name={kind.kind}
        value={tab.state.valueOf("kind", kind.kind)}
        onValue={(n) => tab.state.edit("kind", kind.kind, n)}
        disabled={pending}
        changed={mine}
        inputId={stepperInputId({ mode: "kind", target: kind.kind })}
      />
      {mine && (
        <span data-testid="scale-change" className="text-sm font-medium tabular-nums">
          {asked === null ? `a whole number from 0 to ${MAX_REPLICAS}` : changeWords(current, asked)}
        </span>
      )}
    </div>
  );
}

/**
 * A hardware type's total in a small dialog: choose the type (over two or
 * more NodePools), set its total, and Scale up or Scale down, which opens
 * the confirmation over it (its child: Escape closes only the
 * confirmation). The change is the tab's one change.
 */
function ScaleKindDialog({ tab, kinds, onClose }: { tab: ScaleTabValue; kinds: ScaleKind[]; onClose: (returnFocus: boolean) => void }) {
  const { flavor } = tab.options;
  const [chosen, setChosen] = useState(() => (kinds.find((k) => kindBlock(k, flavor) === null) ?? kinds[0]).kind);
  const kind = kinds.find((k) => k.kind === chosen) ?? kinds[0];
  const { change, confirming, start } = tab.state;
  const mine = change?.mode === "kind" && change.target === kind.kind;
  const block = kindBlock(kind, flavor);
  const dropKindChange = () => {
    if (tab.state.change?.mode === "kind") tab.state.cancel();
  };
  const close = () => {
    if (start.isPending) return;
    dropKindChange();
    onClose(true);
  };
  return (
    <Dialog open onOpenChange={(open) => !open && close()}>
      <DialogContent className="sm:max-w-md" data-testid="scale-kind-dialog">
        <DialogHeader>
          <DialogTitle>Scale a hardware type</DialogTitle>
          <DialogDescription>A new total over its NodePools: update-nodepool spreads it, no two more than one replica apart.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <KindChoice
            kinds={kinds}
            flavor={flavor}
            value={kind.kind}
            onChoose={(k) => {
              dropKindChange();
              setChosen(k);
            }}
            disabled={start.isPending}
          />
          <Total tab={tab} kind={kind} held={block !== null || tab.busy !== null} pending={start.isPending} />
          {tab.busy && <p className="text-xs text-status-warning-fg">{tab.busy}</p>}
          {mine && !confirming && <StartError tab={tab} />}
        </div>
        <DialogFooter>
          <button type="button" onClick={close} disabled={start.isPending} className={buttonVariants({ variant: "outline" })} data-testid="scale-kind-cancel">
            Cancel
          </button>
          {mine ? (
            <ScaleButton tab={tab} id="scale-kind-primary" size="default" />
          ) : (
            <button type="button" disabled className={buttonVariants()}>
              Scale
            </button>
          )}
        </DialogFooter>
        {mine && confirming && (
          <ScaleConfirmDialog
            tab={tab}
            onCancel={() => {
              tab.state.setConfirming(false);
              focusSoon("scale-kind-primary");
            }}
            onStarted={() => onClose(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

/**
 * "Scale hardware type", beside the NodePool sizes heading: for an admin,
 * when a hardware type of this cluster holds two or more NodePools.
 * Waits, with the tab's reason, while a run of the cluster is going.
 */
export function ScaleKindButton() {
  const tab = useScaleTab();
  const [trigger, setTrigger] = useState<HTMLElement | null>(null);
  if (!tab?.isAdmin) return null;
  const kinds = totalKinds(tab.options.kinds);
  if (kinds.length === 0) return null;
  const close = (returnFocus: boolean) => {
    const back = trigger;
    setTrigger(null);
    if (returnFocus) requestAnimationFrame(() => back?.isConnected && back.focus());
  };
  return (
    <>
      <button
        type="button"
        onClick={(e) => setTrigger(e.currentTarget)}
        disabled={tab.busy !== null}
        aria-describedby={tab.busy ? BUSY_ID : undefined}
        data-testid="scale-kind-action"
        className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "shrink-0 text-muted-foreground")}
      >
        <Server aria-hidden />
        Scale hardware type
      </button>
      {trigger && <ScaleKindDialog tab={tab} kinds={kinds} onClose={close} />}
    </>
  );
}
