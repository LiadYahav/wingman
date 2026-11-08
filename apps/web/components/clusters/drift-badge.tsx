import { AlertTriangle, CheckCircle2, CircleHelp, Unlink } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { DriftState } from "@/types";

const DRIFT: Record<DriftState, { label: string; Icon: typeof CheckCircle2; className: string; hint: string }> = {
  in_sync: {
    label: "In sync",
    Icon: CheckCircle2,
    className: "bg-status-ready/10 text-status-ready-fg",
    hint: "Every addon the spec lists is installed",
  },
  drifted: {
    label: "Drifted",
    Icon: AlertTriangle,
    className: "bg-status-warning/10 text-status-warning-fg",
    hint: "An addon the spec lists is not installed",
  },
  unknown: {
    label: "Unknown",
    Icon: CircleHelp,
    className: "bg-status-deleting/10 text-status-deleting-fg",
    hint: "Drift could not be determined",
  },
  not_linked: {
    label: "Not linked",
    Icon: Unlink,
    className: "text-muted-foreground",
    hint: "The cluster is not linked to a spec, so there is nothing to drift from",
  },
};

/**
 * A cluster's drift against its spec. `unknown` is never shown as in sync:
 * day2 did not answer or the spec is gone, and `error` says which.
 */
export function DriftBadge({ state, error, className }: { state: DriftState; error?: string | null; className?: string }) {
  const { label, Icon, className: tone, hint } = DRIFT[state];
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap cursor-default",
            tone,
            className
          )}
        >
          <Icon className="h-3 w-3 shrink-0" />
          {label}
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">{error || hint}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
