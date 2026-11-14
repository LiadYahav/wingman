"use client";

import { ApprovalsCard } from "@/components/overview/approvals-card";
import { ClusterHealthCard } from "@/components/overview/cluster-health-card";
import { ClustersBySiteCard } from "@/components/overview/clusters-by-site-card";
import { OverviewHeader } from "@/components/overview/overview-header";
import { StatCards } from "@/components/overview/stat-cards";
import { VersionsCard } from "@/components/overview/versions-card";

/** Two columns on a wide screen; a card left alone on its row takes both. */
const SECTIONS = "grid gap-4 lg:grid-cols-2 lg:[&>*:last-child:nth-child(odd)]:col-span-2";

/** The Overview: the platform at a glance, each card reading its own source. */
export default function DashboardPage() {
  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-8 animate-in fade-in duration-300">
      <OverviewHeader />

      <StatCards />

      <div className="grid gap-4 lg:grid-cols-2">
        <ClusterHealthCard />
        <ApprovalsCard />
      </div>

      <div className={SECTIONS} data-testid="overview-sections">
        <ClustersBySiteCard />
        <VersionsCard />
      </div>
    </div>
  );
}
