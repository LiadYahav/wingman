import { Activity, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { ClusterLiveStatus } from "@/types";

/** The HostedCluster and NodePools on the MCE hub, as the status stream reports them. */
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
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)
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

            {status.node_pools.length > 0 && (
              <div>
                <p className="text-muted-foreground mb-1.5">Node Pools</p>
                <div className="divide-y divide-border rounded-md border overflow-hidden">
                  {status.node_pools.map((np) => (
                    <div key={np.name} className="flex items-center justify-between gap-3 px-3 py-2">
                      <span className="font-mono text-xs truncate" title={np.name}>{np.name}</span>
                      <div className="flex items-center gap-3 text-xs shrink-0">
                        <span className="text-muted-foreground tabular-nums">
                          {np.ready_replicas}/{np.desired_replicas} ready
                        </span>
                        {np.problems.length > 0 ? (
                          <div className="flex items-center gap-1 text-status-error-fg" title={np.problems.join("\n")}>
                            <XCircle className="h-3.5 w-3.5" />
                            <span className="max-w-48 truncate">{np.problems[0]}</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1 text-status-ready-fg">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            <span>OK</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
