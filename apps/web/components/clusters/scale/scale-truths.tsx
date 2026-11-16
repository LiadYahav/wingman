"use client";

import { CircleCheck, GitCommitHorizontal, RefreshCw, ServerOff, Warehouse, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * What update-nodepool does, said before anything is sent (its design doc is
 * the authority; Wingman starts it and shows its run). A scale-down adds
 * which servers leave and where they go.
 */
function lines(down: boolean): { icon: LucideIcon; text: React.ReactNode; emphasis?: boolean }[] {
  return [
    {
      icon: GitCommitHorizontal,
      text: (
        <>
          One commit to day1 <span className="font-mono">main</span> that changes only the <span className="font-mono">replicas</span>{" "}
          lines, with no merge request.
        </>
      ),
    },
    { icon: RefreshCw, text: "The workflow syncs the cluster's Argo CD Application itself, then checks the NodePools show the new replicas." },
    ...(down
      ? [
          {
            icon: ServerOff,
            emphasis: true,
            text: (
              <>
                The servers that leave are chosen by each NodePool&apos;s{" "}
                <span className="font-mono">redbull.io/scale-down-policy</span>; without one, CAPI picks them at random.
              </>
            ),
          },
          { icon: Warehouse, text: "The freed servers stay in the MCE's inventory, as free Agents." },
        ]
      : []),
    { icon: CircleCheck, text: "Done means the NodePools show the new replicas, not that new nodes are Ready." },
  ];
}

/** The truths of a scale, as a list; `down` adds the scale-down's own. */
export function ScaleTruths({ down, compact = false }: { down: boolean; compact?: boolean }) {
  return (
    <ul className={cn(compact ? "space-y-1" : "space-y-2")} aria-label="What update-nodepool does" data-testid="scale-truths">
      {lines(down).map(({ icon: Icon, text, emphasis }, i) => (
        <li key={i} className={cn("flex items-start gap-2.5", compact ? "text-xs" : "text-sm")}>
          <Icon
            className={cn("shrink-0", compact ? "mt-px h-3.5 w-3.5" : "mt-0.5 h-4 w-4", emphasis ? "text-status-warning-fg" : "text-muted-foreground")}
            aria-hidden
          />
          <span className={emphasis ? "font-medium text-foreground" : "text-muted-foreground"}>{text}</span>
        </li>
      ))}
    </ul>
  );
}
