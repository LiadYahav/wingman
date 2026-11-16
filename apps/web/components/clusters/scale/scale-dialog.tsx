"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ProblemList } from "@/components/common/problem-list";
import { isApiError } from "@/lib/api-client";
import { useScaleBusy, useStartScale } from "@/lib/scale";
import { currentOf, directionOf, refusalTitle, replicasOf, STALE_RUN_CODES, startBody, type ScaleMode } from "@/lib/scale-model";
import { plural } from "@/lib/utils";
import type { ScaleOptions } from "@/types";
import { fromTo } from "./restore-replicas";
import { ScaleChoice } from "./scale-choice";
import { ScaleTruths } from "./scale-truths";

type Step = "choose" | "confirm";

/** Start waits this long after Review: it sits where Review was, so a double-click would press it. */
const ARM_MS = 500;

/** What the review step restates: the target, where it is and what is asked. */
function Change({ options, mode, target, current, asked }: {
  options: ScaleOptions;
  mode: ScaleMode;
  target: string;
  current: number | null;
  asked: number;
}) {
  const kind = mode === "kind" ? options.kinds.find((k) => k.kind === target) : undefined;
  return (
    <div className="rounded-lg border bg-muted/30 px-3.5 py-3 space-y-1" data-testid="scale-change">
      <p className="text-xs text-muted-foreground">{mode === "kind" ? "Hardware kind" : "NodePool"}</p>
      <p className="font-mono text-sm font-medium break-all">{target}</p>
      <p className="text-sm">
        <span className="tabular-nums font-medium">{fromTo(current, asked)}</span> replicas
        {kind && <span className="text-muted-foreground"> in total over {plural(kind.nodepools.length, "NodePool")}</span>}
      </p>
      {kind && <p className="font-mono text-[11px] text-muted-foreground break-all">{kind.nodepools.join(", ")}</p>}
      {kind && (
        <p className="text-xs text-muted-foreground">
          update-nodepool plans the spread and shows it in its run; Wingman computes none.
        </p>
      )}
    </div>
  );
}

/**
 * Scale a cluster's NodePools through the platform's update-nodepool
 * workflow (ADR-0062): choose a hardware kind (a total) or one NodePool (its
 * replicas), then a review that says what the run does. Sent once and never
 * retried; after a refusal that means a run is (or may be) going, it sends
 * nothing more. Mount it while open: its state is one start's.
 */
export function ScaleDialog({ name, where, options, onClose }: { name: string; where: string; options: ScaleOptions; onClose: () => void }) {
  const firstKind = options.kinds.find((k) => k.locked.length === 0 && k.total !== null)?.kind ?? null;
  const [mode, setMode] = useState<ScaleMode>(firstKind ? "kind" : "nodepool");
  const [target, setTarget] = useState<string | null>(firstKind);
  const [replicas, setReplicas] = useState<number>(NaN);
  const [step, setStep] = useState<Step>("choose");
  const [armed, setArmed] = useState(false);
  const start = useStartScale(name, where);
  const busy = useScaleBusy(name, where);
  const pending = start.isPending;
  const settled = STALE_RUN_CODES.some((code) => isApiError(start.error, code));
  const current = currentOf(mode, target, options.kinds, options.nodepools);
  const asked = replicasOf(replicas);
  const direction = directionOf(current, asked);
  const body = startBody(mode, target, replicas);
  const canReview = body !== null && direction !== "none" && busy === null;

  const chooseMode = (next: ScaleMode) => {
    setMode(next);
    setTarget(null);
    setReplicas(NaN);
  };
  const chooseTarget = (next: string) => {
    setTarget(next);
    setReplicas(NaN);
  };
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (step === "choose") {
      if (canReview) setStep("confirm");
      return;
    }
    if (body === null || pending || settled || busy !== null || !armed) return;
    start.mutate(body, {
      onSuccess: () => {
        toast.success("update-nodepool started", { description: `${target}: ${fromTo(current, asked)} replicas` });
        onClose();
      },
    });
  };
  const back = () => {
    start.reset();
    setArmed(false);
    setStep("choose");
  };
  useEffect(() => {
    if (step !== "confirm") return;
    const timer = setTimeout(() => setArmed(true), ARM_MS);
    return () => clearTimeout(timer);
  }, [step]);
  const down = direction === "down";

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !pending) onClose(); }}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false} data-testid="scale-dialog">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle className="leading-snug">
              {step === "choose" ? (
                <>Scale <span className="font-mono break-all">{name}</span></>
              ) : down ? (
                "Scale down?"
              ) : (
                "Scale up?"
              )}
            </DialogTitle>
            <DialogDescription>
              {step === "choose"
                ? "Through the platform's update-nodepool workflow, which owns NodePool replicas. Wingman starts it and shows its run."
                : "Start sends one update-nodepool run. In short, the workflow:"}
            </DialogDescription>
          </DialogHeader>
          {step === "choose" ? (
            <ScaleChoice
              options={options}
              mode={mode}
              target={target}
              replicas={replicas}
              current={current}
              onMode={chooseMode}
              onTarget={chooseTarget}
              onReplicas={setReplicas}
              disabled={pending}
            />
          ) : (
            <>
              <Change options={options} mode={mode} target={target ?? ""} current={current} asked={asked ?? 0} />
              <ScaleTruths down={down} />
            </>
          )}
          {step === "choose" && direction === "none" && (
            <p className="text-xs text-muted-foreground" data-testid="scale-unchanged">It already has {current} replicas: nothing to change.</p>
          )}
          {busy && <p className="text-xs text-status-warning-fg" data-testid="scale-busy">{busy}</p>}
          {Boolean(start.error) && (
            <div data-testid="scale-error">
              <ProblemList error={start.error} title={refusalTitle(start.error)} />
            </div>
          )}
          <DialogFooter>
            {step === "confirm" && !settled ? (
              <button type="button" onClick={back} disabled={pending} className={buttonVariants({ variant: "outline" })}>
                Back
              </button>
            ) : (
              <button type="button" onClick={onClose} disabled={pending} className={buttonVariants({ variant: "outline" })}>
                {settled ? "Close" : "Cancel"}
              </button>
            )}
            {step === "choose" ? (
              <button key="review" type="submit" disabled={!canReview} className={buttonVariants()} data-testid="scale-review">
                Review…
              </button>
            ) : (
              <button
                key="start"
                type="submit"
                disabled={pending || settled || busy !== null || !armed}
                data-testid="scale-start"
                className={buttonVariants({ variant: down ? "destructive" : "default" })}
              >
                {pending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
                {pending ? "Starting…" : down ? "Start scale-down" : "Start scale-up"}
              </button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
