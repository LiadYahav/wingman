"use client";

import { CircleArrowUp, Info } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { RefreshButton } from "@/components/common/refresh-button";
import { day1Keys } from "@/lib/api/day1";
import { useFleetUpgrades } from "@/lib/api/upgrades";
import { isOpenUpgrade } from "@/lib/fleet-upgrades";
import { ClustersViewTabs } from "./clusters-view-tabs";
import { UpgradesTable } from "./upgrades-table";

function Content() {
  const { data, error, isLoading } = useFleetUpgrades();
  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (error) return <ProblemList error={error} title="The upgrade runs could not be read" />;
  if (!data || data.state === "off") {
    return (
      <EmptyState
        icon={CircleArrowUp}
        bordered
        title="Upgrades are off on this Wingman"
        description="DAY1_UPGRADES=false: a cluster's version changes by editing its file."
        data-testid="fleet-upgrades-off"
      />
    );
  }
  return <UpgradesTable runs={data.runs} />;
}

function Summary() {
  const { data } = useFleetUpgrades();
  if (data?.state !== "on") return <>Upgrade runs of the platform&apos;s upgrade-cluster workflow</>;
  const open = data.runs.filter(isOpenUpgrade).length;
  return (
    <span data-testid="fleet-upgrades-summary">
      {open} upgrading · {data.runs.length} cluster{data.runs.length !== 1 ? "s" : ""} with a run
    </span>
  );
}

/**
 * The Clusters page's Upgrades view (ADR-0055's amendment): every cluster's
 * newest run of the platform's upgrade-cluster workflow, its status, phase,
 * what it waits for and when it started, as the orchestrator's own page
 * lists them. The fleet overview only: each row opens its cluster's page,
 * whose Upgrade panel shows the plan and takes the decisions.
 */
export function UpgradesView() {
  const { isFetching } = useFleetUpgrades();
  return (
    <div className="p-6 lg:p-8 max-w-[1400px] mx-auto space-y-4 animate-in fade-in duration-300">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            Clusters
          </h1>
          <p className="mt-0.5 flex items-center gap-1 text-sm text-muted-foreground">
            <Summary />
            <Hint
              hint="Each cluster's newest upgrade, open ones first, from the workflows orchestrator. Open a cluster for its plan, its log and the decisions."
              label="About the Upgrades view"
            >
              <Info aria-hidden className="h-3.5 w-3.5" />
            </Hint>
          </p>
        </div>
        <RefreshButton queryKey={day1Keys.clusters.upgrades} fetching={isFetching} title="Refresh upgrade runs" />
      </div>
      <ClustersViewTabs />
      <Content />
    </div>
  );
}
