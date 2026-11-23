"use client";

import { ClustersBySiteCard } from "./clusters-by-site-card";
import { FreeServersCard } from "./free-servers-card";
import { VersionsCard } from "./versions-card";

/** Two columns on a wide screen; a card left alone on its row takes both. */
const GRID = "grid gap-4 lg:grid-cols-2 lg:[&>*:last-child:nth-child(odd)]:col-span-2";

/** The sections below Cluster Health and Pending Approvals, each reading its own source. */
export function OverviewSections() {
  return (
    <div className={GRID} data-testid="overview-sections">
      <ClustersBySiteCard />
      <VersionsCard />
      <FreeServersCard />
    </div>
  );
}
