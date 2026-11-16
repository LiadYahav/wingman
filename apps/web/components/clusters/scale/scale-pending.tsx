"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Loader2, TriangleAlert } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { ProblemList } from "@/components/common/problem-list";
import { isApiError } from "@/lib/api-client";
import { changeLabel, changeWords, MAX_REPLICAS, refusalTitle, STALE_RUN_CODES } from "@/lib/scale-model";
import { cn } from "@/lib/utils";
import { stepperInputId } from "./replicas-stepper";
import { ScaleDownTruths } from "./scale-truths";
import type { ScaleTabValue } from "./scale-tab";

/** Start scale-down waits this long once asked, so the click that asked cannot also start it. */
const ARM_MS = 500;

/** Focus an element once React has drawn it (or the one it replaced). */
export function focusSoon(id: string) {
  requestAnimationFrame(() => document.getElementById(id)?.focus());
}

/** Whether the change can be sent now, and why not: a run is going, the refusal said the page was out of date, or no number. */
export function sendable(tab: ScaleTabValue): boolean {
  const { start, asked } = tab.state;
  const settled = STALE_RUN_CODES.some((code) => isApiError(start.error, code));
  return tab.busy === null && !settled && asked !== null && !start.isPending;
}

/** Sends the change once; on its start, a toast, and focus on the run where it shows. */
export function sendChange(tab: ScaleTabValue, then?: () => void) {
  const { change, current, asked } = tab.state;
  if (!change) return;
  const label = changeLabel(change);
  tab.state.send(() => {
    toast.success("update-nodepool started", { description: `${label}: ${changeWords(current, asked)} replicas` });
    then?.();
    focusSoon("scale-run");
  });
}

/** A scale-down, said before it is sent: which servers leave and where they go. Focused when it opens; Escape steps back. */
export function ConfirmDown({ question, pending, blocked, onBack, onStart, children }: {
  question: React.ReactNode;
  pending: boolean;
  blocked: boolean;
  onBack: () => void;
  onStart: () => void;
  /** What the run does on a scale-down. */
  children: React.ReactNode;
}) {
  const [armed, setArmed] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.focus();
    const timer = setTimeout(() => setArmed(true), ARM_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div
      ref={box}
      tabIndex={-1}
      role="group"
      aria-labelledby="scale-confirm-question"
      onKeyDown={(e) => {
        if (e.key === "Escape" && !pending) {
          e.stopPropagation();
          onBack();
        }
      }}
      data-testid="scale-confirm"
      className="space-y-2.5 rounded-lg border border-status-warning/40 bg-status-warning/[0.07] px-3 py-2.5 outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <p id="scale-confirm-question" className="flex items-start gap-2 text-sm font-medium">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-status-warning-fg" aria-hidden />
        <span className="break-all">{question}</span>
      </p>
      {children}
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={onBack} disabled={pending} className={buttonVariants({ variant: "outline", size: "sm" })} data-testid="scale-back">
          Back
        </button>
        <button
          type="button"
          onClick={onStart}
          disabled={!armed || pending || blocked}
          className={buttonVariants({ variant: "destructive", size: "sm" })}
          data-testid="scale-confirm-start"
        >
          {pending && <Loader2 className="animate-spin" aria-hidden />}
          {pending ? "Starting…" : "Start scale-down"}
        </button>
      </div>
    </div>
  );
}

/** Scale up (at once) or Scale down (asks first): the change's own button. */
export function ScaleButton({ tab, id, size = "sm", onStarted }: {
  tab: ScaleTabValue;
  id?: string;
  size?: "sm" | "default";
  /** After a scale-up started (a scale-down's start is its question's). */
  onStarted?: () => void;
}) {
  const { direction, start } = tab.state;
  const down = direction === "down";
  return (
    <button
      type="button"
      id={id}
      onClick={() => (down ? tab.state.setConfirming(true) : sendChange(tab, onStarted))}
      disabled={!sendable(tab)}
      className={buttonVariants({ variant: down ? "destructive" : "default", size })}
      data-testid="scale-start"
    >
      {start.isPending && <Loader2 className="animate-spin" aria-hidden />}
      {start.isPending ? "Starting…" : down ? "Scale down" : "Scale up"}
    </button>
  );
}

/** The refusal of a start, in the problem's words. */
export function StartError({ tab }: { tab: ScaleTabValue }) {
  const { error } = tab.state.start;
  if (!error) return null;
  return (
    <div data-testid="scale-error">
      <ProblemList error={error} title={refusalTitle(error)} />
    </div>
  );
}

/**
 * One NodePool's change, where its stepper is (its card, or its NodePool
 * sizes row): the change, what the run does, Cancel and Scale up or Scale
 * down; a scale-down asks first, in place. Nothing for another target.
 */
export function PendingChange({ tab, nodepool, className }: { tab: ScaleTabValue; nodepool: string; className?: string }) {
  const { change, current, asked, direction, confirming, start } = tab.state;
  if (!change || change.mode !== "nodepool" || change.target !== nodepool) return null;
  const primaryId = `scale-primary-${nodepool}`;
  const cancel = () => {
    tab.state.cancel();
    focusSoon(stepperInputId(change));
  };
  const fewer = current !== null && asked !== null ? current - asked : 0;
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
        {!confirming && (
          <div className="flex shrink-0 gap-2">
            <button type="button" onClick={cancel} disabled={start.isPending} className={buttonVariants({ variant: "outline", size: "sm" })} data-testid="scale-cancel">
              Cancel
            </button>
            <ScaleButton tab={tab} id={primaryId} />
          </div>
        )}
      </div>
      {confirming && direction === "down" && (
        <ConfirmDown
          question={`Scale down by ${fewer === 1 ? "1 replica" : `${fewer} replicas`}?`}
          pending={start.isPending}
          blocked={!sendable(tab)}
          onBack={() => {
            start.reset();
            tab.state.setConfirming(false);
            focusSoon(primaryId);
          }}
          onStart={() => sendChange(tab)}
        >
          <ScaleDownTruths />
        </ConfirmDown>
      )}
      <StartError tab={tab} />
    </div>
  );
}
