"use client";

import { Network } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { useSegmentStats } from "@/lib/api/segments";
import { segmentCapacity } from "@/lib/overview/capacity";
import { DEFAULT_VIEW, viewHref } from "@/lib/segments/view";
import { plural } from "@/lib/utils";
import { CapacityRow, CapacityTotal } from "./capacity-row";
import { OverviewCard, RowsSkeleton } from "./overview-card";

/** The Segments page showing a site's Available segments. */
const freeAt = (site: string) => viewHref({ ...DEFAULT_VIEW, status: "available", site });

function SegmentsBody() {
  const stats = useSegmentStats();
  if (stats.isLoading) return <RowsSkeleton className="h-10" />;
  if (!stats.data) return <ProblemList error={stats.error} title="segments-manager's statistics could not be read" />;
  const capacity = segmentCapacity(stats.data.sites);
  if (capacity.sites.length === 0) {
    return <EmptyState icon={Network} title="No sites yet" description="segments-manager lists no site." data-testid="overview-segments-empty" />;
  }
  return (
    <>
      <CapacityTotal free={capacity.free} what={`free across ${plural(capacity.sites.length, "site")}`} data-testid="overview-segments-total" />
      <div className="-mx-3 space-y-0.5">
        {capacity.sites.map((site) => (
          <CapacityRow key={site.site} href={freeAt(site.site)} name={site.site} free={site.free} of={site.total} usedPercent={site.usedPercent}
            label={`${site.site}: ${site.free} free of ${plural(site.total, "segment")}`} data-testid="overview-segment-site" />
        ))}
      </div>
    </>
  );
}

/**
 * segments-manager's numbers: each site's segments that no cluster holds.
 * Shown only to people with the Segments area (admins, segments-manager
 * set up): the page mounts it then, so nobody else asks.
 */
export function FreeSegmentsCard() {
  return (
    <OverviewCard
      title="Free Segments"
      hint="Each site's network segments that are Available in segments-manager, out of all its segments; the allocate-segment workflow gives a new cluster one. The bar is the share already allocated."
      href={viewHref({ ...DEFAULT_VIEW, status: "available" })}
      linkLabel="Segments"
      data-testid="overview-segments"
    >
      <SegmentsBody />
    </OverviewCard>
  );
}
