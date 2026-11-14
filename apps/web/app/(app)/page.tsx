"use client";

import { ApprovalsCard } from "@/components/overview/approvals-card";
import { ClusterHealthCard } from "@/components/overview/cluster-health-card";
import { QuickActions } from "@/components/overview/quick-actions";
import { StatCards } from "@/components/overview/stat-cards";

/** The Overview: the platform at a glance, each card reading its own source. */
export default function DashboardPage() {
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

      <StatCards />

      <div className="grid gap-4 lg:grid-cols-2">
        <ClusterHealthCard />
        <ApprovalsCard />
      </div>

      <QuickActions />
    </div>
  );
}
