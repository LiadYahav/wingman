/**
 * What the platform has, as day1 reads it: sites and MCEs (read-only in
 * Wingman), an MCE's InfraEnvs and OpenShift versions (ADR-0034), MCE
 * placement for a new cluster (ADR-0050), the machine configs a nodepool can
 * name (ADR-0027) and Quick Links (ADR-0052).
 */

import { api } from "@/lib/api-client";
import type { PlacementQuery } from "@/lib/placement";
import type { MachineConfigs, Mce, OpenShiftVersions, Placement, QuickLinks } from "@/types";

const mcePath = (mce: string) => `/api/day1/mces/${encodeURIComponent(mce)}`;

/**
 * `/api/day1/placement?...` for `query`; empty parameters are left out, each
 * need is one `need`. With no need, an empty `need=` tells day1 the nodepools
 * name no node type yet, so it does not fall back to the flavor's presets.
 */
function placementPath(query: PlacementQuery): string {
  const params = new URLSearchParams();
  const { needs = [], ...single } = query;
  for (const [key, value] of Object.entries(single)) if (value) params.set(key, value);
  for (const need of needs.length > 0 ? needs : [""]) params.append("need", need);
  return `/api/day1/placement?${params.toString()}`;
}

export const fleetApi = {
  sites: () => api.get<string[]>("/api/day1/sites"),
  /** Every MCE, of every site. */
  allMces: () => api.get<Mce[]>("/api/day1/mces"),
  mcesAt: (site: string) => api.get<Mce[]>(`/api/day1/mces?site=${encodeURIComponent(site)}`),
  /** The InfraEnvs on the MCE hub (501 FEATURE_DISABLED when live status is off). */
  infraEnvs: (mce: string) => api.get<string[]>(`${mcePath(mce)}/infraenvs`),
  /** The versions from the day1 repo's upgrade ladder for the MCE. */
  openshiftVersions: (mce: string) => api.get<OpenShiftVersions>(`${mcePath(mce)}/openshift-versions`),
  placement: (query: PlacementQuery) => api.get<Placement>(placementPath(query)),
  machineConfigs: () => api.get<MachineConfigs>("/api/day1/machine-configs"),
  quickLinks: () => api.get<QuickLinks>("/api/day1/quick-links"),
};
