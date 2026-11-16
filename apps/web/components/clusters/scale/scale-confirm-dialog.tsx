"use client";

import { useEffect, useState } from "react";
import { CircleCheck, CirclePlus, GitCommitHorizontal, Loader2, ServerOff, TriangleAlert, Warehouse, type LucideIcon } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { addsLine, changeLine, doneLine, leaving, poolsOf, type Leaving } from "@/lib/scale-confirm";
import { cn } from "@/lib/utils";
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
  /** Each NodePool's own policy, under the line. */
  pools?: Leaving["pools"];
  testId?: string;
}

const MAIN = <span className="font-mono">main</span>;

function upPoints(count: number, mode: "kind" | "nodepool"): Point[] {
  return [
    { icon: CirclePlus, text: addsLine(count, mode) },
    { icon: GitCommitHorizontal, text: <>One commit to day1 {MAIN}, no merge request; the workflow has Argo CD apply it.</> },
    { icon: CircleCheck, text: doneLine(mode) },
  ];
}

function downPoints(leave: Leaving): Point[] {
  return [
    {
      icon: leave.refused ? TriangleAlert : ServerOff,
      text: leave.text,
      emphasis: leave.refused ? "refused" : "notice",
      pools: leave.pools,
      testId: "scale-confirm-leaving",
    },
    { icon: Warehouse, text: "Their pods move to the remaining nodes; the servers stay in the MCE's inventory, free." },
    { icon: GitCommitHorizontal, text: <>One commit to day1 {MAIN}, applied by Argo CD.</> },
  ];
}

function Points({ points }: { points: Point[] }) {
  return (
    <ul className="space-y-2" aria-label="What update-nodepool does" data-testid="scale-confirm-points">
      {points.map(({ icon: Icon, text, emphasis, pools, testId }, i) => (
        <li key={i} className="flex items-start gap-2.5 text-sm" data-testid={testId}>
          <Icon
            className={cn(
              "mt-0.5 h-4 w-4 shrink-0",
              emphasis === "refused" ? "text-status-error-fg" : emphasis === "notice" ? "text-status-warning-fg" : "text-muted-foreground"
            )}
            aria-hidden
          />
          <div className="min-w-0 space-y-1">
            <p className={emphasis ? "font-medium text-foreground" : "text-muted-foreground"}>{text}</p>
            {pools && pools.length > 0 && (
              <ul className="space-y-0.5 text-xs text-muted-foreground" aria-label="Each NodePool's scale-down policy">
                {pools.map((p) => (
                  <li key={p.nodepool} className={cn("break-words", p.refused && "text-status-error-fg")} data-testid="scale-confirm-pool">
                    <span className="font-mono break-all text-foreground">{p.nodepool}</span>: {p.words}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * The confirmation before every scale (ADR-0062's amendments): what
 * update-nodepool is about to do, in a few plain lines, then Cancel or Yes.
 * A scale-down says which nodes leave, by each NodePool's scale-down policy
 * as the day1 file sets it. Yes arms after half a second; Cancel and Escape
 * change nothing, and the change stays where it was. Mount it while open; in
 * the hardware type dialog it is that dialog's child, so Escape closes only it.
 */
export function ScaleConfirmDialog({ tab, onCancel, onStarted }: {
  tab: ScaleTabValue;
  /** Closed with nothing sent. */
  onCancel: () => void;
  /** The run started (it shows under NodePool sizes, focused). */
  onStarted?: () => void;
}) {
  const armed = useArmed(ARM_MS);
  const { change, current, asked, direction, start } = tab.state;
  if (!change || current === null || asked === null || (direction !== "up" && direction !== "down")) return null;
  const up = direction === "up";
  const pools = poolsOf(change, tab.options);
  const points = up ? upPoints(asked - current, change.mode) : downPoints(leaving(current - asked, pools));
  const close = () => {
    if (!start.isPending) onCancel();
  };

  return (
    <Dialog open onOpenChange={(open) => !open && close()}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false} data-testid="scale-confirm" data-direction={direction}>
        <DialogHeader>
          <DialogTitle className="leading-snug">
            Scale {up ? "up" : "down"} <span className="font-mono break-words">{change.target}</span>?
          </DialogTitle>
          <DialogDescription className="tabular-nums text-foreground" data-testid="scale-confirm-change">
            {changeLine(change.mode, current, asked, pools.length)}
          </DialogDescription>
        </DialogHeader>

        <Points points={points} />

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
            onClick={() => sendChange(tab, onStarted)}
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
