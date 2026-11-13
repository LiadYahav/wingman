import Link from "next/link";
import { AlertTriangle, ArrowUpCircle, CheckCircle2, CircleHelp, GitPullRequest, Unlink } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { approvalHref } from "@/lib/approvals";
import {
  flavorDisplayState, flavorStateHint, flavorStateLabel, STATE_NAME, type FlavorDisplayState, type FlavorStateRow,
} from "@/lib/flavor-state";
import { cn } from "@/lib/utils";

const LOOK: Record<FlavorDisplayState, { Icon: typeof CheckCircle2; className: string }> = {
  in_sync: { Icon: CheckCircle2, className: "bg-status-ready/10 text-status-ready-fg" },
  drifted: { Icon: AlertTriangle, className: "bg-status-warning/10 text-status-warning-fg" },
  unknown: { Icon: CircleHelp, className: "bg-status-deleting/10 text-status-deleting-fg" },
  update_available: { Icon: ArrowUpCircle, className: "bg-status-provisioning/10 text-status-provisioning-fg" },
  update_mr_open: { Icon: GitPullRequest, className: "bg-status-provisioning/10 text-status-provisioning-fg" },
  not_linked: { Icon: Unlink, className: "text-muted-foreground" },
};

const PILL = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap";

/** A display state alone, as the legend beside a count. */
export function FlavorStateLegend({ state, className }: { state: FlavorDisplayState; className?: string }) {
  const { Icon, className: tone } = LOOK[state];
  return (
    <span className={cn(PILL, tone, className)}>
      <Icon className="h-3 w-3 shrink-0" aria-hidden />
      {STATE_NAME[state]}
    </span>
  );
}

/**
 * A cluster against its flavor (ADR-0044): drifted or unknown against the
 * version it is on, else its update (an open update MR links to its review
 * page), else in sync at its version. `unknown` is never shown as in sync:
 * the tooltip gives `error`. `data-state` is the display state.
 */
export function FlavorStateBadge({ row, className }: { row: FlavorStateRow; className?: string }) {
  const state = flavorDisplayState(row);
  const { Icon, className: tone } = LOOK[state];
  const label = flavorStateLabel(row, state);
  const hint = flavorStateHint(row, state);
  const mr = state === "update_mr_open" ? row.update!.merge_request! : null;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger
          data-testid="flavor-state"
          data-state={state}
          className={cn(PILL, mr ? "hover:underline underline-offset-2" : "cursor-default", tone, className)}
          render={mr ? <Link href={approvalHref(mr)} aria-label={`${label}: review !${mr.iid}`} /> : undefined}
        >
          <Icon className="h-3 w-3 shrink-0" aria-hidden />
          {label}
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">{hint}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
