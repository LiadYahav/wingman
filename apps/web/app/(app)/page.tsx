"use client";

import { ApprovalsCard } from "@/components/overview/approvals-card";
import { ClusterHealthCard } from "@/components/overview/cluster-health-card";
import { OverviewHeader } from "@/components/overview/overview-header";
import { OverviewSections } from "@/components/overview/overview-sections";
import { StatCards } from "@/components/overview/stat-cards";

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

      <OverviewSections />
    </div>
  );
}
