import { Activity, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { ClusterLiveStatus } from "@/types";

/** The card's rows while the first read is out: phase and version, the HostedCluster, two node pools. */
function LiveStatusSkeleton() {
  return (
    <>
      <div className="flex items-center gap-4 flex-wrap">
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-5 w-40" />
      </div>
      <div className="flex items-center gap-2">
        <Skeleton className="h-4 w-28 shrink-0" />
        <Skeleton className="h-4 w-20" />
      </div>
      <div>
        <Skeleton className="h-4 w-20 mb-1.5" />
        <div className="divide-y divide-border rounded-md border overflow-hidden">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between gap-3 px-3 py-2">
              <Skeleton className="h-4 w-36" />
              <Skeleton className="h-4 w-24" />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

/**
 * The HostedCluster and NodePools on the MCE hub, as the status stream reports them.
 * `status` is undefined only while the first read is out: the page shows a failed
 * read as a problem instead of this card.
 */
export function LiveStatusCard({ status, isLoading }: { status: ClusterLiveStatus | undefined; isLoading: boolean }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground flex items-center gap-1.5">
          <Activity className="h-3.5 w-3.5" />
          Live Status
          {status && (
            <span className="ml-1 font-mono text-[11px] font-normal text-muted-foreground/70 truncate">
              {status.namespace}/{status.hosted_cluster}
            </span>
          )}
          <span className="ml-auto text-[10px] font-normal text-muted-foreground/60 shrink-0">live</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {isLoading || !status ? (
          <LiveStatusSkeleton />
        ) : status.error ? (
          <div className="flex items-start gap-2 text-status-error-fg text-xs">
            <XCircle className="h-4 w-4 shrink-0" />
            <span className="break-words">{status.error}</span>
          </div>
        ) : (
          <>
            {(status.hc_phase || status.ocp_version) && (
              <div className="flex items-center gap-4 flex-wrap">
                {status.hc_phase && (
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">Phase</span>
                    <Badge
                      variant="outline"
                      className={
                        status.hc_phase === "Running"
                          ? "text-status-ready-fg border-status-ready/40"
                          : status.hc_phase === "Degraded" || status.hc_phase === "Error"
                          ? "text-status-error-fg border-status-error/40"
                          : "text-status-warning-fg border-status-warning/40"
                      }
                    >
                      {status.hc_phase}
                    </Badge>
                  </div>
                )}
                {status.ocp_version && (
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">OCP Version</span>
                    <span className="font-mono font-medium text-xs">{status.ocp_version}</span>
                  </div>
                )}
              </div>
            )}

            <div className="flex items-start gap-2">
              <span className="text-muted-foreground min-w-28 shrink-0">HostedCluster</span>
              {status.hc_problems.length > 0 ? (
                <div className="space-y-1">
                  {status.hc_problems.map((p, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-status-error-fg">
                      <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                      <span className="text-xs break-words">{p}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-status-ready-fg">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span>Healthy</span>
                </div>
              )}
            </div>

            <p className="text-xs text-muted-foreground" data-testid="live-status-node-pools-note">
              {status.node_pools.length === 0
                ? "No node pools reported"
                : `${status.node_pools.length} node pool${status.node_pools.length === 1 ? "" : "s"}: their state and nodes are in Nodepools below`}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
