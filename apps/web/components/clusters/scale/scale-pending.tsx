"use client";

import { Loader2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { changeWords, MAX_REPLICAS } from "@/lib/scale-model";
import { cn } from "@/lib/utils";
import { stepperInputId } from "./replicas-stepper";
import { ScaleConfirmDialog } from "./scale-confirm-dialog";
import { focusSoon, sendable, StartError } from "./scale-start";
import type { ScaleTabValue } from "./scale-tab";

/** Scale up or Scale down: the change's own button. Either asks first, in the confirmation. */
export function ScaleButton({ tab, id, size = "sm" }: { tab: ScaleTabValue; id?: string; size?: "sm" | "default" }) {
  const { direction, start } = tab.state;
  const down = direction === "down";
  return (
    <button
      type="button"
      id={id}
      onClick={() => {
        // A refusal that left the page current (a 502, a 422) is not kept into a new question
        start.reset();
        tab.state.setConfirming(true);
      }}
      disabled={!sendable(tab)}
      className={buttonVariants({ variant: down ? "destructive" : "default", size })}
      data-testid="scale-start"
    >
      {start.isPending && <Loader2 className="animate-spin" aria-hidden />}
      {start.isPending ? "Starting…" : down ? "Scale down" : "Scale up"}
    </button>
  );
}

/**
 * One NodePool's change, where its stepper is (its card, or its NodePool
 * sizes row): the change, what the run does, Cancel and Scale up or Scale
 * down, which opens the confirmation. Nothing for another target.
 */
export function PendingChange({ tab, nodepool, className }: { tab: ScaleTabValue; nodepool: string; className?: string }) {
  const { change, current, asked, confirming, start } = tab.state;
  if (!change || change.mode !== "nodepool" || change.target !== nodepool) return null;
  const primaryId = `scale-primary-${nodepool}`;
  const cancel = () => {
    tab.state.cancel();
    focusSoon(stepperInputId(change));
  };
  return (
    <div data-testid="scale-pending" data-nodepool={nodepool} className={cn("space-y-2.5 rounded-lg border border-primary/25 bg-primary/[0.04] px-3 py-2.5", className)}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-56 space-y-0.5">
          <p data-testid="scale-change" className="text-sm font-medium tabular-nums">
            {asked === null ? `Replicas are a whole number from 0 to ${MAX_REPLICAS}.` : `Replicas ${changeWords(current, asked)}`}
          </p>
          <p className="text-xs text-muted-foreground">
            One commit to day1 <span className="font-mono">main</span>; the workflow syncs Argo CD itself.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button type="button" onClick={cancel} disabled={start.isPending} className={buttonVariants({ variant: "outline", size: "sm" })} data-testid="scale-cancel">
            Cancel
          </button>
          <ScaleButton tab={tab} id={primaryId} />
        </div>
      </div>
      {/* Shown in the confirmation while it is open; here once it is closed */}
      {!confirming && <StartError tab={tab} />}
      {confirming && (
        <ScaleConfirmDialog
          tab={tab}
          onCancel={() => {
            tab.state.setConfirming(false);
            focusSoon(primaryId);
          }}
        />
      )}
    </div>
  );
}
