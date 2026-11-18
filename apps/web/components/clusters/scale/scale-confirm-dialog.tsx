"use client";

import { useEffect, useState } from "react";
import { CircleCheck, CirclePlus, GitCommitHorizontal, Loader2, ServerOff, TriangleAlert, Warehouse, type LucideIcon } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { addsLine, changeLine, DONE_LINE, type Leaving } from "@/lib/scale-confirm";
import { leaveLine } from "@/lib/scale-leave";
import { cn } from "@/lib/utils";
import { LeaveChoice } from "./scale-leave-choice";
import { sendable, sendChange, settled, StartError } from "./scale-start";
import type { ScaleTabValue } from "./scale-tab";

/** Yes waits this long once the confirmation opens, so the click that opened it cannot also confirm it. */
const ARM_MS = 500;

/** True once `ms` have passed since the caller mounted. */
function useArmed(ms: number): boolean {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setArmed(true), ms);
    return () => clearTimeout(timer);
  }, [ms]);
  return armed;
}

interface Point {
  icon: LucideIcon;
  text: React.ReactNode;
  /** Said louder: which nodes a scale-down removes. */
  emphasis?: "notice" | "refused";
  testId?: string;
}

const MAIN = <span className="font-mono">main</span>;

function upPoints(count: number): Point[] {
  return [
    { icon: CirclePlus, text: addsLine(count) },
    { icon: GitCommitHorizontal, text: <>One commit to day1 {MAIN}, no merge request; the workflow has Argo CD apply it.</> },
    { icon: CircleCheck, text: DONE_LINE },
  ];
}

function downPoints(leave: Leaving): Point[] {
  return [
    {
      icon: leave.refused ? TriangleAlert : ServerOff,
      text: leave.text,
      emphasis: leave.refused ? "refused" : "notice",
      testId: "scale-confirm-leaving",
    },
    { icon: Warehouse, text: "Their pods move to the remaining nodes; the servers stay in the MCE's inventory, free." },
    { icon: GitCommitHorizontal, text: <>One commit to day1 {MAIN}, applied by Argo CD.</> },
  ];
}

function Points({ points }: { points: Point[] }) {
  return (
    <ul className="space-y-2" aria-label="What update-nodepool does" data-testid="scale-confirm-points">
      {points.map(({ icon: Icon, text, emphasis, testId }, i) => (
        <li key={i} className="flex items-start gap-2.5 text-sm" data-testid={testId}>
          <Icon
            className={cn(
              "mt-0.5 h-4 w-4 shrink-0",
              emphasis === "refused" ? "text-status-error-fg" : emphasis === "notice" ? "text-status-warning-fg" : "text-muted-foreground"
            )}
            aria-hidden
          />
          <p className={cn("min-w-0", emphasis ? "font-medium text-foreground" : "text-muted-foreground")}>{text}</p>
        </li>
      ))}
    </ul>
  );
}

/**
 * The confirmation before every scale (ADR-0062's amendments): what
 * update-nodepool is about to do, in a few plain lines, then Cancel or Yes.
 * A scale-down says which nodes leave and offers one choice of how
 * (`scale-leave-choice.tsx`): the NodePool's own policy as the day1 file sets
 * it (the default), another policy for this run, or exactly the servers
 * picked. Yes arms after half a second, and waits while fewer servers are
 * ticked than leave; Cancel and Escape change nothing, and the change stays
 * where it was (the choice is dropped). Mount it while open.
 */
export function ScaleConfirmDialog({ tab, onCancel }: {
  tab: ScaleTabValue;
  /** Closed with nothing sent. */
  onCancel: () => void;
}) {
  const armed = useArmed(ARM_MS);
  const { change, current, asked, direction, start, servers, choice, own, policy } = tab.state;
  if (!change || current === null || asked === null || (direction !== "up" && direction !== "down")) return null;
  const up = direction === "up";
  const points = up ? upPoints(asked - current) : downPoints(leaveLine(choice, current - asked, own, policy, servers));
  const close = () => {
    if (!start.isPending) onCancel();
  };

  return (
    <Dialog open onOpenChange={(open) => !open && close()}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false} data-testid="scale-confirm" data-direction={direction}>
        <DialogHeader>
          <DialogTitle className="leading-snug">
            Scale {up ? "up" : "down"} <span className="font-mono break-words">{change.nodepool}</span>?
          </DialogTitle>
          <DialogDescription className="tabular-nums text-foreground" data-testid="scale-confirm-change">
            {changeLine(current, asked)}
          </DialogDescription>
        </DialogHeader>

        <Points points={points} />
        {!up && <LeaveChoice tab={tab} />}

        {tab.busy && <p className="text-xs text-status-warning-fg">{tab.busy}</p>}
        <StartError tab={tab} />

        <DialogFooter>
          <button
            type="button"
            onClick={close}
            disabled={start.isPending}
            className={buttonVariants({ variant: "outline" })}
            data-testid="scale-confirm-cancel"
          >
            {settled(tab) ? "Close" : "Cancel"}
          </button>
          <button
            type="button"
            onClick={() => sendChange(tab)}
            disabled={!armed || !sendable(tab)}
            className={buttonVariants({ variant: up ? "default" : "destructive" })}
            data-testid="scale-confirm-yes"
          >
            {start.isPending && <Loader2 className="animate-spin" aria-hidden />}
            {start.isPending ? "Starting…" : up ? "Yes, scale up" : "Yes, scale down"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
