"use client";

import { Activity, AlertTriangle, CheckCircle2, CircleHelp, Clock, Server } from "lucide-react";
import { EmptyState, EmptyStateLink } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { useIsAdmin } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import type { HealthCounts } from "@/lib/overview/health";
import { OverviewCard, RowsSkeleton } from "./overview-card";
import { useOverviewHealth } from "./use-overview";

function HealthRows({ health }: { health: HealthCounts }) {
  const rows = [
    { label: "Ready", count: health.ready, color: "text-status-ready", bg: "bg-status-ready/15", icon: CheckCircle2 },
    { label: "Provisioning", count: health.provisioning, color: "text-status-provisioning", bg: "bg-status-provisioning/15", icon: Clock },
    { label: "Error", count: health.error, color: "text-status-error", bg: "bg-status-error/15", icon: AlertTriangle },
    { label: "Unknown", count: health.unknown, color: "text-muted-foreground", bg: "bg-muted", icon: CircleHelp },
  ];
  return (
    <div className="space-y-2">
      {rows.map(({ label, count, color, bg, icon: Icon }) => (
        <div key={label} className="flex items-center justify-between rounded-lg px-3 py-2.5 bg-muted/40 hover:bg-muted/60 transition-colors">
          <div className="flex items-center gap-2.5">
            <div className={cn("rounded-lg p-1.5", bg)}>
              <Icon className={cn("h-3.5 w-3.5", color)} />
            </div>
            <span className="text-sm font-medium">{label}</span>
          </div>
          <span className="text-sm font-bold tabular-nums">{count}</span>
        </div>
      ))}
    </div>
  );
}

function HealthBody() {
  const isAdmin = useIsAdmin();
  const { clusters, status, health, off, loading } = useOverviewHealth();
  if (loading) return <RowsSkeleton />;
  if (clusters.error) return <ProblemList error={clusters.error} title="The clusters could not be loaded" />;
  if (clusters.data?.length === 0) {
    return (
      <EmptyState
        icon={Server}
        title="No clusters yet"
        description="Their health shows here once the day1 repo has hosted clusters."
        action={isAdmin && <EmptyStateLink href="/clusters/new">New cluster</EmptyStateLink>}
        data-testid="health-empty"
      />
    );
  }
  if (off) {
    return (
      <EmptyState
        icon={Activity}
        title="Live status is off"
        description="This deployment does not read HostedClusters from the MCE hubs (CLUSTER_STATUS_ENABLED)."
      />
    );
  }
  if (status.error) return <ProblemList error={status.error} title="Live status could not be read from the MCE hubs" />;
  return <HealthRows health={health} />;
}

/** Each cluster's live phase from its MCE hub, counted. */
export function ClusterHealthCard() {
  return (
    <OverviewCard title="Cluster Health" href="/clusters">
      <HealthBody />
    </OverviewCard>
  );
}
