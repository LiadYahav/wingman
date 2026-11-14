"use client";

import Link from "next/link";
import { AlertTriangle, CheckCircle2, GitPullRequest, Server } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, plural } from "@/lib/utils";
import { useOverviewApprovals, useOverviewDrift, useOverviewHealth, useOverviewSpecs } from "./use-overview";

const COLORS = {
  blue: { icon: "text-primary", bg: "bg-primary/15", value: "text-primary" },
  green: { icon: "text-status-ready", bg: "bg-status-ready/15", value: "text-status-ready-fg" },
  orange: { icon: "text-status-warning", bg: "bg-status-warning/15", value: "text-status-warning-fg" },
  red: { icon: "text-status-error", bg: "bg-status-error/15", value: "text-status-error-fg" },
};

function StatCard({
  title, value, hint, icon: Icon, href, loading, color = "blue",
}: {
  title: string; value: number | undefined; hint?: string; icon: React.ElementType;
  href: string; loading: boolean; color?: keyof typeof COLORS;
}) {
  const c = COLORS[color];
  return (
    <Link href={href} className="block group" data-testid={`stat-${title.toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="bg-card rounded-xl border shadow-sm hover:shadow-md hover:border-primary/30 transition-all p-5 cursor-pointer h-full">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{title}</p>
            {loading
              ? <Skeleton className="mt-2 h-9 w-16" />
              : <p className={cn("mt-1 text-3xl font-bold tabular-nums", c.value)}>{value ?? "—"}</p>
            }
            {hint && !loading && <p className="mt-1 text-xs text-muted-foreground truncate">{hint}</p>}
          </div>
          <div className={cn("rounded-xl p-2.5 shrink-0", c.bg)}>
            <Icon className={cn("h-5 w-5", c.icon)} />
          </div>
        </div>
      </div>
    </Link>
  );
}

function ClusterStats() {
  const { clusters, status, health, off, loading } = useOverviewHealth();
  const specs = useOverviewSpecs();
  return (
    <>
      <StatCard
        title="Total Clusters"
        value={clusters.data?.length}
        hint={clusters.error ? "Could not be loaded" : specs.data ? plural(specs.data.length, "spec") : undefined}
        icon={Server} href="/clusters" loading={clusters.isLoading} color="blue"
      />
      <StatCard
        title="Ready"
        value={off || clusters.error || status.error ? undefined : health.ready}
        hint={off ? "Live status is off" : status.error ? "Could not be read" : undefined}
        icon={CheckCircle2} href="/clusters" loading={loading} color="green"
      />
    </>
  );
}

function ApprovalStat() {
  const approvals = useOverviewApprovals();
  return (
    <StatCard
      title="Pending Approvals" value={approvals.allFailed ? undefined : approvals.total}
      hint={
        approvals.allFailed ? "Could not be loaded"
          : approvals.unavailable.length > 0 ? `${approvals.unavailable.join(" and ")} unavailable`
          : undefined
      }
      icon={GitPullRequest} href="/approvals" loading={approvals.loading}
      color={approvals.total > 0 ? "orange" : "blue"}
    />
  );
}

function DriftStat() {
  const { drift, counts } = useOverviewDrift();
  return (
    <StatCard
      title="Drifted" value={drift.data ? counts.drifted : undefined}
      hint={drift.isError ? "Could not be loaded" : counts.hint || undefined}
      icon={AlertTriangle} href="/clusters" loading={drift.isLoading}
      color={counts.drifted > 0 ? "red" : "blue"}
    />
  );
}

/** The four numbers at the top: clusters, ready, pending approvals, drifted. */
export function StatCards() {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <ClusterStats />
      <ApprovalStat />
      <DriftStat />
    </div>
  );
}
