"use client";

import { useSegmentsArea } from "@/lib/api/segments";
import { ClustersBySiteCard } from "./clusters-by-site-card";
import { FreeSegmentsCard } from "./free-segments-card";
import { FreeServersCard } from "./free-servers-card";
import { VersionsCard } from "./versions-card";

/** Two columns on a wide screen; a card left alone on its row takes both. */
const GRID = "grid gap-4 lg:grid-cols-2 lg:[&>*:last-child:nth-child(odd)]:col-span-2";

/**
 * The sections below Cluster Health and Pending Approvals. A card shows only
 * to people who can open the page it links to: Free Segments to those with
 * the Segments area (admins, segments-manager set up), mounted only then,
 * so nobody else asks for what day1 would refuse.
 */
export function OverviewSections() {
  const segments = useSegmentsArea();
  return (
    <div className={GRID} data-testid="overview-sections">
      <ClustersBySiteCard />
      <VersionsCard />
      <FreeServersCard />
      {segments === true && <FreeSegmentsCard />}
    </div>
  );
}
