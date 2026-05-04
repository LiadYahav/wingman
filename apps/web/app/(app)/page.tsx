"use client";

import Link from "next/link";
import { useQuery, useQueries } from "@tanstack/react-query";
import { Server, GitPullRequest, AlertTriangle, CheckCircle2, Clock, ArrowRight, Plus } from "lucide-react";
import { api } from "@/lib/api-client";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useIsAdmin } from "@/stores/auth-store";
import type { ClusterStatus, ClusterLiveStatus, MRDetail } from "@/types";

function liveStatusToPhase(s: ClusterLiveStatus): "Ready" | "Error" | "Provisioning" | "Unknown" {
  if (s.error) return "Error";
  if (s.hc_problems.length > 0) return "Error";
  if (s.node_pools.length === 0) return "Unknown";
  const allReady = s.node_pools.every(
    (np) => np.ready_replicas === np.desired_replicas && np.problems.length === 0
  );
  return allReady ? "Ready" : "Provisioning";
}

interface DashboardStats {
  total_clusters: number;
  provisioning: number;
  ready: number;
  error: number;
  drifted: number;
  total_specs: number;
  open_approvals_day1: number;
  open_approvals_day2: number;
}

function StatCard({
  title, value, icon: Icon, href, loading, color = "blue",
}: {
  title: string; value: number | undefined; icon: React.ElementType;
  href: string; loading: boolean; color?: "blue" | "green" | "orange" | "red";
}) {
  const colorMap = {
    blue:   { icon: "text-[#0073ea]", bg: "bg-[#0073ea]/8 dark:bg-[#0073ea]/15", value: "text-[#0073ea]" },
    green:  { icon: "text-[#00c875]", bg: "bg-[#00c875]/8 dark:bg-[#00c875]/15", value: "text-[#007038] dark:text-[#00c875]" },
    orange: { icon: "text-[#fdab3d]", bg: "bg-[#fdab3d]/8 dark:bg-[#fdab3d]/15", value: "text-[#c07800] dark:text-[#fdab3d]" },
    red:    { icon: "text-[#df2f4a]", bg: "bg-[#df2f4a]/8 dark:bg-[#df2f4a]/15", value: "text-[#a0122a] dark:text-[#df2f4a]" },
  };
  const c = colorMap[color];
  return (
    <Link href={href} className="block group">
      <div className="bg-card rounded-xl border shadow-sm hover:shadow-md hover:border-primary/30 transition-all p-5 cursor-pointer">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{title}</p>
            {loading
              ? <Skeleton className="mt-2 h-9 w-16" />
              : <p className={cn("mt-1 text-3xl font-bold", c.value)}>{value ?? "—"}</p>
            }
          </div>
          <div className={cn("rounded-xl p-2.5", c.bg)}>
            <Icon className={cn("h-5 w-5", c.icon)} />
          </div>
        </div>
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const isAdmin = useIsAdmin();

  const { data: clusters, isLoading: clustersLoading } = useQuery<ClusterStatus[]>({
    queryKey: ["clusters"],
    queryFn: () => api.get<ClusterStatus[]>("/api/day1/clusters"),
    // Use global staleTime (2 min) — no override needed
  });

  const { data: specs } = useQuery<{ name: string }[]>({
    queryKey: ["specs"],
    queryFn: () => api.get<{ name: string }[]>("/api/day1/specs").catch(() => []),
    // Use global staleTime (2 min)
  });

  const { data: approvalsDay1 } = useQuery<MRDetail[]>({
    queryKey: ["approvals", "day1"],
    queryFn: () => api.get<MRDetail[]>("/api/day1/approvals").catch(() => [] as MRDetail[]),
    staleTime: 60_000, // 1 min — approvals change less frequently
  });

  const { data: approvalsDay2 } = useQuery<MRDetail[]>({
    queryKey: ["approvals", "day2"],
    queryFn: () => api.get<MRDetail[]>("/api/day2/approvals").catch(() => [] as MRDetail[]),
    staleTime: 60_000, // 1 min
  });

  // Fire live status queries in parallel for every cluster — same cache keys as clusters page
  const liveStatusResults = useQueries({
    queries: (clusters ?? []).map((c) => ({
      queryKey: ["clusters", c.name, "live-status", c.mce],
      queryFn: async (): Promise<ClusterLiveStatus | null> => {
        try {
          return await api.get<ClusterLiveStatus>(`/api/day1/clusters/${c.name}/status?mce=${c.mce}`);
        } catch (err) {
          if (err instanceof Error && err.message.startsWith("API error 501")) return null;
          throw err;
        }
      },
      staleTime: 2 * 60_000,     // 2 min — match clusters page
      refetchInterval: 2 * 60_000, // 2 min polling
      retry: false,
      enabled: Boolean(c.mce),
    })),
  });

  // Build phase map: cluster name → live phase (or fallback to stored phase)
  const phaseMap = new Map<string, string>();
  (clusters ?? []).forEach((c, i) => {
    const result = liveStatusResults[i];
    if (result?.data) {
      phaseMap.set(c.name, liveStatusToPhase(result.data));
    } else {
      // Feature disabled (null) or still loading — fall back to stored phase
      phaseMap.set(c.name, c.phase ?? "Unknown");
    }
  });

  // Show skeleton only while clusters list itself is loading (live status fills in progressively)
  const statsLoading = clustersLoading;

  const stats: DashboardStats | undefined = clusters ? {
    total_clusters: clusters.length,
    ready: Array.from(phaseMap.values()).filter((p) => p === "Ready").length,
    provisioning: Array.from(phaseMap.values()).filter((p) => p === "Provisioning").length,
    error: Array.from(phaseMap.values()).filter((p) => p === "Error").length,
    drifted: 0,
    total_specs: specs?.length ?? 0,
    open_approvals_day1: approvalsDay1?.length ?? 0,
    open_approvals_day2: approvalsDay2?.length ?? 0,
  } : undefined;

  const { data: driftSummary } = useQuery<{ name: string; is_drifted: boolean }[]>({
    queryKey: ["clusters", "drift-summary"],
    queryFn: () => api.get("/api/day1/clusters/drift-summary"),
    staleTime: 60_000,  // Cache for 1 minute - drift detection is expensive
    gcTime: 5 * 60_000, // Keep in cache for 5 minutes
  });

  const driftedCount = driftSummary?.filter((d) => d.is_drifted).length ?? stats?.drifted ?? 0;

  const recentApprovals = [
    ...(approvalsDay1?.map((mr) => ({ ...mr, repo: "day1" as const })) ?? []),
    ...(approvalsDay2?.map((mr) => ({ ...mr, repo: "day2" as const })) ?? []),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 6);

  const approvalsLoading = !approvalsDay1 && !approvalsDay2;

  const totalApprovals = (stats?.open_approvals_day1 ?? 0) + (stats?.open_approvals_day2 ?? 0);

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
        <StatCard title="Total Clusters" value={stats?.total_clusters} icon={Server} href="/clusters" loading={statsLoading} color="blue" />
        <StatCard title="Ready" value={stats?.ready} icon={CheckCircle2} href="/clusters" loading={statsLoading} color="green" />
        <StatCard title="Pending Approvals" value={totalApprovals} icon={GitPullRequest} href="/approvals" loading={statsLoading} color={totalApprovals > 0 ? "orange" : "blue"} />
        <StatCard title="Drifted" value={driftedCount} icon={AlertTriangle} href="/clusters" loading={statsLoading && driftSummary === undefined} color={driftedCount > 0 ? "red" : "blue"} />
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
          {statsLoading ? (
            <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-11 w-full rounded-lg" />)}</div>
          ) : (
            <div className="space-y-2">
              {[
                { label: "Ready", count: stats?.ready ?? 0, color: "text-[#00c875]", bg: "bg-[#00c875]/8 dark:bg-[#00c875]/15", icon: CheckCircle2 },
                { label: "Provisioning", count: stats?.provisioning ?? 0, color: "text-[#579bfc]", bg: "bg-[#579bfc]/8 dark:bg-[#579bfc]/15", icon: Clock },
                { label: "Error", count: stats?.error ?? 0, color: "text-[#df2f4a]", bg: "bg-[#df2f4a]/8 dark:bg-[#df2f4a]/15", icon: AlertTriangle },
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
          {approvalsLoading ? (
            <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}</div>
          ) : recentApprovals && recentApprovals.length > 0 ? (
            <div className="space-y-1">
              {recentApprovals.map((mr) => (
                <Link key={`${mr.repo}-${mr.iid}`} href={`/approvals/${mr.repo}-${mr.iid}`}
                  className="flex items-center justify-between rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors group">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">{mr.title}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      by {mr.author.username} · {new Date(mr.created_at).toLocaleDateString("en-GB")}
                    </p>
                  </div>
                  <span className={cn(
                    "ml-3 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium",
                    mr.repo === "day1"
                      ? "bg-[#0073ea]/10 text-[#0073ea] dark:bg-[#579bfc]/15 dark:text-[#579bfc]"
                      : "bg-[#00c875]/10 text-[#007038] dark:bg-[#00c875]/15 dark:text-[#00c875]"
                  )}>
                    {mr.repo}
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <div className="rounded-full bg-[#00c875]/10 dark:bg-[#00c875]/15 p-3 mb-3">
                <CheckCircle2 className="h-6 w-6 text-[#00c875]" />
              </div>
              <p className="text-sm font-semibold">All caught up!</p>
              <p className="text-xs text-muted-foreground mt-0.5">No pending approvals</p>
            </div>
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
            New Spec
          </Link>
        )}
        <Link
          href="/specs"
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          Browse Specs
        </Link>
      </div>
    </div>
  );
}
