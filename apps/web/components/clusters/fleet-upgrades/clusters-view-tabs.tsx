"use client";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isApiError } from "@/lib/api-client";
import { useFleetUpgrades } from "@/lib/api/upgrades";
import { isOpenUpgrade, type ClustersView } from "@/lib/fleet-upgrades";
import { showClustersView, useClustersView } from "./use-clusters-view";

/**
 * Clusters | Upgrades, under the Clusters page's heading. Shown only while
 * upgrades are on (DAY1_UPGRADES): off, the page is the clusters list alone.
 */
export function ClustersViewTabs() {
  const view = useClustersView();
  const { data, error } = useFleetUpgrades();
  const on = data?.state === "on" || (Boolean(error) && !isApiError(error, "FEATURE_DISABLED"));
  if (!on) return null;
  const open = data?.state === "on" ? data.runs.filter(isOpenUpgrade).length : 0;
  return (
    <Tabs value={view} onValueChange={(next) => showClustersView(next as ClustersView)}>
      <TabsList aria-label="Clusters views">
        <TabsTrigger value="clusters" data-testid="clusters-view-clusters">Clusters</TabsTrigger>
        <TabsTrigger value="upgrades" data-testid="clusters-view-upgrades">
          Upgrades
          {open > 0 && (
            <span className="ml-1 rounded-full bg-status-provisioning/15 px-1.5 text-[11px] tabular-nums text-status-provisioning-fg" data-testid="upgrades-open-count">
              {open}
            </span>
          )}
        </TabsTrigger>
      </TabsList>
    </Tabs>
  );
}
