"use client";

import { Fragment } from "react";
import { FileWarning, TriangleAlert } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/clusters/status-badge";
import { IntentLink } from "@/components/common/intent-link";
import { liveStatusToPhase } from "@/lib/live-status";
import { clusterHref, OWNER_KEYS } from "@/lib/clusters";
import { OWNER_LABEL, ownerOf } from "@/components/clusters/list/model";
import type { ClusterLiveStatus, ClusterStatus } from "@/types";

/*
 * The clusters list's cells that are more than a value: the owner numbers,
 * the flags on a name, and the live status.
 */

export function OwnerCell({ cluster }: { cluster: ClusterStatus }) {
  const parts = OWNER_KEYS.map((k) => ownerOf(cluster, k));
  if (parts.every((p) => !p)) return <span className="text-muted-foreground/60 text-xs">—</span>;
  return (
    <span className="font-mono text-xs text-muted-foreground whitespace-nowrap" data-testid="cluster-owner">
      {OWNER_KEYS.map((k, i) => (
        <Fragment key={k}>
          {i > 0 && " / "}
          <span title={`${OWNER_LABEL[k]} ${parts[i] || "not set"}`}>{parts[i] || "—"}</span>
        </Fragment>
      ))}
    </span>
  );
}

/** A flag whose tooltip lists why: its trigger takes the remaining props. */
function FlagTooltip({ title, problems, ...trigger }: { title: string; problems: string[] } & React.ComponentProps<typeof TooltipTrigger>) {
  return (
    <Tooltip>
      <TooltipTrigger {...trigger} />
      <TooltipContent className="max-w-sm">
        <p className="font-medium mb-1">{title}</p>
        <ul className="list-disc pl-4 space-y-0.5">{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
      </TooltipContent>
    </Tooltip>
  );
}

/** Off-convention names and unreadable files are flagged in place, never hidden. */
export function ClusterFlags({ cluster }: { cluster: ClusterStatus }) {
  const offConvention = !cluster.naming.follows_convention;
  const unreadable = cluster.problems.length > 0;
  if (!offConvention && !unreadable) return null;
  return (
    <TooltipProvider>
      {unreadable && (
        <FlagTooltip
          title="The cluster file does not parse"
          problems={cluster.problems}
          data-testid="cluster-unreadable"
          className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium bg-status-error/10 text-status-error-fg cursor-default"
        >
          <FileWarning className="h-3 w-3" />Unreadable
        </FlagTooltip>
      )}
      {offConvention && (
        <FlagTooltip
          title="Off the naming convention"
          problems={cluster.naming.problems}
          data-testid="cluster-off-convention"
          aria-label="Name does not follow the naming convention"
          className="inline-flex items-center text-status-warning cursor-default"
        >
          <TriangleAlert className="h-3.5 w-3.5" />
        </FlagTooltip>
      )}
    </TooltipProvider>
  );
}

export function ClusterStatusCell({
  cluster,
  status,
  statusOff,
  isLoading,
  failed,
}: {
  cluster: ClusterStatus;
  status: ClusterLiveStatus | undefined;
  statusOff: boolean;
  isLoading: boolean;
  failed: boolean;
}) {
  if (isLoading) return <Skeleton className="h-5 w-16" />;
  if (!status) {
    const reason = statusOff
      ? "Live status is off in this deployment"
      : failed
      ? "Live status could not be read"
      : "No live status for this cluster";
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger className="text-muted-foreground/60 text-xs cursor-default">—</TooltipTrigger>
          <TooltipContent>{reason}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }
  const errorMsg = status.error ?? status.hc_problems[0];
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <IntentLink href={clusterHref(cluster)}>
            <StatusBadge phase={liveStatusToPhase(status)} />
          </IntentLink>
        </TooltipTrigger>
        {errorMsg && <TooltipContent className="max-w-xs">{errorMsg}</TooltipContent>}
      </Tooltip>
    </TooltipProvider>
  );
}
