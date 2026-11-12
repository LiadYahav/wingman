import type { ReactElement, ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { describeCheck } from "@/lib/quick-links";
import { cn } from "@/lib/utils";
import type { LinkCheck } from "@/types";

/** `pending`: day1 has not answered for this link yet (the status read is on its way). */
export type DotState = LinkCheck["state"] | "pending";

const DOT: Record<DotState, string> = {
  up: "bg-status-ready",
  down: "bg-status-error",
  unknown: "bg-muted-foreground/50",
  pending: "border border-muted-foreground/60 bg-transparent",
};

export const dotState = (check: LinkCheck | undefined): DotState => check?.state ?? "pending";

/**
 * A link's status, as day1 last checked it: green up, red down, grey unknown,
 * hollow while not checked yet. Colour is never the only signal: the dot is
 * an image named for the state and why ("Up · answered 200 in 84 ms ·
 * checked 12 s ago"), the same text shows on hover, and a card spells out a
 * link that is down. No animation.
 */
export function StatusDot({ check, ping, className }: { check: LinkCheck | undefined; ping: string; className?: string }) {
  const state = dotState(check);
  return (
    <span
      role="img"
      aria-label={describeCheck(check)}
      data-testid="status-dot"
      data-state={state}
      data-ping={ping}
      className={cn("inline-block size-2 shrink-0 rounded-full", DOT[state], className)}
    />
  );
}

/** `trigger` (a dot, or a link chip holding one) with the check in words on hover. */
export function StatusTip({ check, trigger, children }: { check: LinkCheck | undefined; trigger: ReactElement; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger render={trigger}>{children}</TooltipTrigger>
      <TooltipContent data-testid="status-tip">{describeCheck(check)}</TooltipContent>
    </Tooltip>
  );
}
