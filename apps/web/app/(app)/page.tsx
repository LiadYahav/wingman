"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Server, GitPullRequest, AlertTriangle, CheckCircle2, Clock, ArrowRight, Plus, CircleHelp, Activity } from "lucide-react";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { RepoBadge } from "@/components/common/repo-badge";
import { ApprovalLink, WorkflowBadge } from "@/components/common/workflow-mr";
import { ProblemList } from "@/components/common/problem-list";
import { EmptyState, EmptyStateLink } from "@/components/common/empty-state";
import { cn, formatDate, newestFirst, plural } from "@/lib/utils";
import { useIsAdmin } from "@/stores/auth-store";
import { useBulkStatus } from "@/hooks/use-bulk-status";
import { liveStatusToPhase } from "@/lib/live-status";
import { mrKey } from "@/lib/approvals";
import type { ClusterStatus, DriftSummaryItem, MRDetail, SpecEntry } from "@/types";

function StatCard({
  title, value, hint, icon: Icon, href, loading, color = "blue",
}: {
  title: string; value: number | undefined; hint?: string; icon: React.ElementType;
  href: string; loading: boolean; color?: "blue" | "green" | "orange" | "red";
}) {
  const colorMap = {
    blue:   { icon: "text-primary", bg: "bg-primary/15", value: "text-primary" },
    green:  { icon: "text-status-ready", bg: "bg-status-ready/15", value: "text-status-ready-fg" },
    orange: { icon: "text-status-warning", bg: "bg-status-warning/15", value: "text-status-warning-fg" },
    red:    { icon: "text-status-error", bg: "bg-status-error/15", value: "text-status-error-fg" },
  };
  const c = colorMap[color];
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

// eslint-disable-next-line max-lines-per-function, complexity -- size baseline (ADR-0056)
export default function DashboardPage() {
  const isAdmin = useIsAdmin();

  const { data: clusters, isLoading: clustersLoading, error: clustersError } = useQuery<ClusterStatus[]>({
    queryKey: day1Keys.clusters.all,
    queryFn: day1Api.clusters.list,
  });

  // Same cache entries as the specs and approvals pages
  const { data: specs } = useQuery<SpecEntry[]>({
    queryKey: day1Keys.specs.all,
    queryFn: day1Api.specs.list,
  });

  const { data: approvalsDay1, isPending: day1ApprovalsPending, error: day1ApprovalsError } = useQuery<MRDetail[]>({
    queryKey: day1Keys.approvals.list("day1"),
    queryFn: () => day1Api.approvals.list("day1"),
    staleTime: 60_000,
  });

  const { data: approvalsDay2, isPending: day2ApprovalsPending, error: day2ApprovalsError } = useQuery<MRDetail[]>({
    queryKey: day1Keys.approvals.list("day2"),
    queryFn: () => day1Api.approvals.list("day2"),
    staleTime: 60_000,
  });

  const { data: liveStatuses, isLoading: statusLoading, error: statusError } = useBulkStatus(clusters);

  const { data: driftSummary, isLoading: driftLoading, isError: driftFailed } = useQuery<DriftSummaryItem[]>({
    queryKey: day1Keys.clusters.driftSummary,
    queryFn: day1Api.clusters.driftSummary,
    staleTime: 60_000, // drift asks day2 about every linked cluster
    gcTime: 5 * 60_000,
  });

  const phases = (clusters ?? []).flatMap((c) => {
    const status = liveStatuses?.[c.name];
    return status ? [liveStatusToPhase(status)] : [];
  });
  const health = {
    ready: phases.filter((p) => p === "Ready").length,
    provisioning: phases.filter((p) => p === "Provisioning").length,
    error: phases.filter((p) => p === "Error").length,
  };
  const statusOff = liveStatuses === null;

  // Against the version each cluster is on (ADR-0044): a newer flavor version is an update, never drift
  const drifted = driftSummary?.filter((d) => d.state === "drifted").length ?? 0;
  const driftUnknown = driftSummary?.filter((d) => d.state === "unknown").length ?? 0;
  const withUpdate = driftSummary?.filter((d) => d.state === "in_sync" && d.update).length ?? 0;
  const driftHint = [
    driftUnknown > 0 && `${driftUnknown} unknown`,
    withUpdate > 0 && `${withUpdate} with an update`,
  ].filter(Boolean).join(" · ");

  const allApprovals = newestFirst([approvalsDay1, approvalsDay2], (mr) => mr.created_at);
  const recentApprovals = allApprovals.slice(0, 6);
  // Until both sources answered (or failed), a count or "all caught up" would be one source's.
  const approvalsLoading = day1ApprovalsPending || day2ApprovalsPending;
  const unavailableApprovals = [day1ApprovalsError && "day1", day2ApprovalsError && "day2"].filter(Boolean);
  const totalApprovals = allApprovals.length;
  // Neither source answered: there is no count to show, not a count of zero.
  const allApprovalsFailed = Boolean(day1ApprovalsError && day2ApprovalsError);

  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-8 animate-in fade-in duration-300">
      <div>
        <h1
          className="text-2xl font-bold tracking-tight"
          style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
        >
          Overview
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">OpenShift cluster platform at a glance</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          title="Total Clusters"
          value={clusters?.length}
          hint={clustersError ? "Could not be loaded" : specs ? plural(specs.length, "spec") : undefined}
          icon={Server} href="/clusters" loading={clustersLoading} color="blue"
        />
        <StatCard
          title="Ready"
          value={statusOff || clustersError || statusError ? undefined : health.ready}
          hint={statusOff ? "Live status is off" : statusError ? "Could not be read" : undefined}
          icon={CheckCircle2} href="/clusters" loading={clustersLoading || statusLoading} color="green"
        />
        <StatCard
          title="Pending Approvals" value={allApprovalsFailed ? undefined : totalApprovals}
          hint={
            allApprovalsFailed ? "Could not be loaded"
              : unavailableApprovals.length > 0 ? `${unavailableApprovals.join(" and ")} unavailable`
              : undefined
          }
          icon={GitPullRequest} href="/approvals" loading={approvalsLoading}
          color={totalApprovals > 0 ? "orange" : "blue"}
        />
        <StatCard
          title="Drifted" value={driftSummary ? drifted : undefined}
          hint={driftFailed ? "Could not be loaded" : driftHint || undefined}
          icon={AlertTriangle} href="/clusters" loading={driftLoading}
          color={drifted > 0 ? "red" : "blue"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Cluster health */}
        <div className="bg-card rounded-xl border shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold">Cluster Health</h2>
            <Link href="/clusters" className="text-xs text-primary hover:underline flex items-center gap-1">
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          {clustersLoading || statusLoading ? (
            <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-11 w-full rounded-lg" />)}</div>
          ) : clustersError ? (
            <ProblemList error={clustersError} title="The clusters could not be loaded" />
          ) : clusters?.length === 0 ? (
            <EmptyState
              icon={Server}
              title="No clusters yet"
              description="Their health shows here once the day1 repo has hosted clusters."
              action={isAdmin && <EmptyStateLink href="/clusters/new">New cluster</EmptyStateLink>}
              data-testid="health-empty"
            />
          ) : statusOff ? (
            <EmptyState
              icon={Activity}
              title="Live status is off"
              description="This deployment does not read HostedClusters from the MCE hubs (CLUSTER_STATUS_ENABLED)."
            />
          ) : statusError ? (
            <ProblemList error={statusError} title="Live status could not be read from the MCE hubs" />
          ) : (
            <div className="space-y-2">
              {[
                { label: "Ready", count: health.ready, color: "text-status-ready", bg: "bg-status-ready/15", icon: CheckCircle2 },
                { label: "Provisioning", count: health.provisioning, color: "text-status-provisioning", bg: "bg-status-provisioning/15", icon: Clock },
                { label: "Error", count: health.error, color: "text-status-error", bg: "bg-status-error/15", icon: AlertTriangle },
                { label: "Unknown", count: (clusters?.length ?? 0) - phases.length + phases.filter((p) => p === "Unknown").length, color: "text-muted-foreground", bg: "bg-muted", icon: CircleHelp },
              ].map(({ label, count, color, bg, icon: Icon }) => (
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
          )}
        </div>

        {/* Pending approvals */}
        <div className="bg-card rounded-xl border shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold">Pending Approvals</h2>
            <Link href="/approvals" className="text-xs text-primary hover:underline flex items-center gap-1">
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          {(day1ApprovalsError || day2ApprovalsError) && (
            <div className="mb-3 space-y-2">
              {day1ApprovalsError && <ProblemList error={day1ApprovalsError} title="Day1 and spec MRs could not be loaded" />}
              {day2ApprovalsError && <ProblemList error={day2ApprovalsError} title="Day2 team MRs could not be loaded" />}
            </div>
          )}
          {approvalsLoading ? (
            <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}</div>
          ) : recentApprovals.length > 0 ? (
            <div className="space-y-1">
              {recentApprovals.map((mr) => (
                <ApprovalLink key={mrKey(mr)} mr={mr}
                  className="flex items-center justify-between rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">{mr.title}</p>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">
                      by {mr.author.username} · {formatDate(mr.created_at)}
                    </p>
                  </div>
                  <div className="ml-3 flex shrink-0 items-center gap-1.5">
                    <WorkflowBadge mr={mr} />
                    <RepoBadge repo={mr.repo} />
                  </div>
                </ApprovalLink>
              ))}
            </div>
          ) : unavailableApprovals.length > 0 ? null : (
            <EmptyState
              icon={CheckCircle2}
              tone="success"
              title="All caught up"
              description="No merge request is waiting for an approval."
              data-testid="approvals-empty"
            />
          )}
        </div>
      </div>

      {/* Quick actions */}
      <div className="flex gap-3 flex-wrap">
        {isAdmin && (
          <Link
            href="/clusters/new"
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors shadow-sm"
          >
            <Plus className="h-4 w-4" />New Cluster
          </Link>
        )}
        {isAdmin && (
          <Link
            href="/specs/new"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            New Flavor
          </Link>
        )}
        <Link
          href="/specs"
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          Browse Flavors
        </Link>
      </div>
    </div>
  );
}
