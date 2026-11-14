"use client";

import Link from "next/link";
import { CircleArrowUp, Loader2, Tag } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError } from "@/lib/api-client";
import { useFleetUpgrades } from "@/lib/api/upgrades";
import { withUpgradeFilter } from "@/lib/fleet-upgrades";
import { percent, upgradeSummary, versionSpread, type VersionCount } from "@/lib/overview/clusters";
import { cn, plural } from "@/lib/utils";
import type { ClusterStatus } from "@/types";
import { Bar } from "./bars";
import { CardNote, OverviewCard, RowsSkeleton } from "./overview-card";
import { useOverviewClusters } from "./use-overview";

const ROW_LINK = "rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring/50";

function VersionRow({ row, total }: { row: VersionCount; total: number }) {
  const label = row.version ?? "Not set";
  return (
    <Link
      href="/clusters"
      data-testid="overview-version"
      data-version={row.version ?? ""}
      aria-label={`${label}: ${plural(row.count, "cluster")}`}
      className={cn(ROW_LINK, "grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_2.5rem] items-center gap-3 px-3 py-1.5 hover:bg-muted/50 transition-colors")}
    >
      <span className={cn("truncate text-xs", row.version ? "font-mono" : "text-muted-foreground")}>{label}</span>
      <Bar percent={percent(row.count, total)} />
      <span className="text-right text-sm font-semibold tabular-nums">{row.count}</span>
    </Link>
  );
}

const upgradesHref = (filter: "available" | "upgrading") =>
  withUpgradeFilter({ pathname: "/clusters", search: "", hash: "" }, filter);

const PILL = "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/50";

/** Upgrade available and Upgrading, each opening the clusters list with that filter; nothing while upgrades are off. */
function UpgradeCounts({ clusters }: { clusters: ClusterStatus[] }) {
  const fleet = useFleetUpgrades();
  if (fleet.isPending) return <Skeleton className="mt-4 h-6 w-56 rounded-full" />;
  const runs = fleet.data?.state === "on" ? fleet.data.runs : null;
  const failed = Boolean(fleet.error) && !isApiError(fleet.error, "FEATURE_DISABLED");
  const summary = upgradeSummary(clusters, runs, { failed });
  if (!summary.on) return null;
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-4" data-testid="overview-upgrades">
      <Link href={upgradesHref("available")} data-testid="overview-upgrade-available"
        title="Clusters whose MCE offers a newer OpenShift release than their mastertag"
        className={cn(PILL, "bg-primary/8 text-primary hover:bg-primary/15")}>
        <CircleArrowUp aria-hidden className="h-3.5 w-3.5" />
        <span><span className="tabular-nums">{summary.available}</span> {summary.available === 1 ? "upgrade" : "upgrades"} available</span>
      </Link>
      <Link href={upgradesHref("upgrading")} data-testid="overview-upgrading"
        title={summary.upgrading === null ? "The upgrade runs could not be read" : "Clusters with an upgrade-cluster run open"}
        className={cn(PILL, "bg-status-provisioning/12 text-status-provisioning-fg hover:bg-status-provisioning/20")}>
        <Loader2 aria-hidden className={cn("h-3.5 w-3.5", summary.upgrading ? "animate-spin motion-reduce:animate-none" : "")} />
        <span><span className="tabular-nums">{summary.upgrading ?? "—"}</span> upgrading</span>
      </Link>
    </div>
  );
}

function VersionsBody() {
  const clusters = useOverviewClusters();
  if (clusters.isLoading) return <RowsSkeleton rows={4} className="h-7" />;
  if (clusters.error) return <CardNote data-testid="overview-versions-failed">The clusters could not be loaded: Cluster Health says why.</CardNote>;
  const list = clusters.data ?? [];
  if (list.length === 0) {
    return <EmptyState icon={Tag} title="No clusters yet" description="Their OpenShift versions show here once the day1 repo has hosted clusters." data-testid="overview-versions-empty" />;
  }
  const spread = versionSpread(list);
  return (
    <>
      <div className="-mx-3 space-y-0.5">
        {spread.rows.map((row) => <VersionRow key={row.version ?? ""} row={row} total={list.length} />)}
      </div>
      {spread.rest && (
        <p className="mt-1 text-xs text-muted-foreground" data-testid="overview-versions-more">
          {plural(spread.rest.versions, "more version")} · {plural(spread.rest.clusters, "cluster")}
        </p>
      )}
      <UpgradeCounts clusters={list} />
    </>
  );
}

/** The clusters' OpenShift versions (each file's mastertag), and their upgrades. */
export function VersionsCard() {
  return (
    <OverviewCard
      title="OpenShift Versions"
      hint="Clusters per mastertag, the OpenShift release each cluster file asks for, newest first; each bar is that version's share of all clusters. With upgrades on, how many clusters' MCE offers a newer release, and how many have an upgrade run open."
      href="/clusters"
      data-testid="overview-versions"
    >
      <VersionsBody />
    </OverviewCard>
  );
}
