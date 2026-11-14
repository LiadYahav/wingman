"use client";

import { useState } from "react";
import { useSegmentsArea } from "@/lib/api/segments";
import { useServerScanArea } from "@/lib/api/server-scan";
import { ClustersBySiteCard } from "./clusters-by-site-card";
import { FleetHealthCard } from "./fleet-health-card";
import { FreeSegmentsCard } from "./free-segments-card";
import { FreeServersCard } from "./free-servers-card";
import { VersionsCard } from "./versions-card";

/** Two columns on a wide screen; a card left alone on its row takes both. */
const GRID = "grid gap-4 lg:grid-cols-2 lg:[&>*:last-child:nth-child(odd)]:col-span-2";

/**
 * Whether this person has an area, as last known: while the area's read is
 * asked again (an errored read is, whenever a reader mounts) it is
 * `undefined`, and a card that came and went with it would mount, ask, and
 * unmount again, without end. A card stays until the answer changes.
 */
function useKnownArea(area: boolean | undefined): boolean | undefined {
  const [known, setKnown] = useState(area);
  if (area !== undefined && area !== known) setKnown(area);
  return area ?? known;
}

/**
 * The sections below Cluster Health and Pending Approvals. A card shows only
 * to people who can open the page it links to: Free Segments to those with
 * the Segments area, Server Fleet Health to those with the Server Scan area
 * (admins, with segments-manager or server-scan set up), each mounted only
 * then, so nobody else asks for what day1 would refuse.
 */
export function OverviewSections() {
  const segments = useKnownArea(useSegmentsArea());
  const serverScan = useKnownArea(useServerScanArea());
  return (
    <div className={GRID} data-testid="overview-sections">
      <ClustersBySiteCard />
      <VersionsCard />
      <FreeServersCard />
      {segments === true && <FreeSegmentsCard />}
      {serverScan === true && <FleetHealthCard />}
    </div>
  );
}
