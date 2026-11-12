/**
 * A cluster's network: the VLAN and segment from its file, the EPG from
 * segments-manager, and what segments-manager says that disagrees with the
 * file (docs/notes/2026-11-11-cluster-network-api.md, ADR-0039). A
 * segments-manager failure never fails the read: it comes back as
 * `ledger_error`, beside the file's values.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { ClusterNetworkRead } from "@/types";

export const networkKey = (name: string) => ["clusters", name, "network"] as const;

/** `GET /clusters/{name}/network{where}`, read with the page: the detail does not wait on it. */
export function useClusterNetwork(name: string, where: string) {
  return useQuery<ClusterNetworkRead>({
    queryKey: networkKey(name),
    queryFn: () => api.get<ClusterNetworkRead>(`/api/day1/clusters/${encodeURIComponent(name)}/network${where}`),
    staleTime: 60_000,
    retry: false,
  });
}
