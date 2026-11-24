"use client";

import { VersionsCard } from "./versions-card";

/**
 * The section below Cluster Health and Pending Approvals: the tenants'
 * OpenShift versions. Where the clusters run and the free servers name the
 * MCEs, so they are the Infrastructure Overview's (ADR-0067).
 */
export function OverviewSections() {
  return (
    <div className="grid gap-4" data-testid="overview-sections">
      <VersionsCard />
    </div>
  );
}
