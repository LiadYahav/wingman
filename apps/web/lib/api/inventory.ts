/**
 * day1's Inventory Management routes (docs/notes/2026-11-13-inventory-management-api.md,
 * ADR-0057): typed calls, query keys and hooks. Everyone signed in reads;
 * only admins add (403 for anyone else). `501 FEATURE_DISABLED` without
 * server-scan (the page), the orchestrator (the runs) or `DAY1_ADD_SERVERS`
 * (adding). A start is never retried (ADR-0006).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api-client";
import type {
  AddServersRequest,
  AddServersResult,
  Candidates,
  InventoryOverview,
  InventoryRuns,
} from "@/types/inventory";

/** The pools are re-read every 30 seconds, the runs every 10, while the page is open. */
const POOLS_REFRESH_MS = 30_000;
const RUNS_REFRESH_MS = 10_000;

const BASE = "/api/day1/inventory";
const poolPath = (mce: string, infraEnv: string) =>
  `${BASE}/mces/${encodeURIComponent(mce)}/infra-envs/${encodeURIComponent(infraEnv)}`;

const inventoryKeys = {
  overview: ["inventory", "overview"] as const,
  runs: ["inventory", "runs"] as const,
  candidates: (mce: string, infraEnv: string) => ["inventory", "candidates", mce, infraEnv] as const,
};

const inventoryApi = {
  overview: () => api.get<InventoryOverview>(BASE),
  runs: () => api.get<InventoryRuns>(`${BASE}/runs`),
  candidates: (mce: string, infraEnv: string) => api.get<Candidates>(`${poolPath(mce, infraEnv)}/candidates`),
  addServers: (mce: string, infraEnv: string, body: AddServersRequest) =>
    api.post<AddServersResult>(`${poolPath(mce, infraEnv)}/add-servers`, body),
};

/** A problem is day1's answer (403 for a viewer, 501 when off): show it, don't ask again. */
const retryUnlessProblem = (count: number, error: unknown) => !isApiError(error) && count < 2;

export function useInventory() {
  return useQuery<InventoryOverview>({
    queryKey: inventoryKeys.overview,
    queryFn: inventoryApi.overview,
    staleTime: 10_000,
    refetchInterval: POOLS_REFRESH_MS,
    retry: retryUnlessProblem,
  });
}

/** The add-server runs, herzi's included; read only where the orchestrator is configured. */
export function useInventoryRuns({ enabled }: { enabled: boolean }) {
  return useQuery<InventoryRuns>({
    queryKey: inventoryKeys.runs,
    queryFn: inventoryApi.runs,
    staleTime: 5_000,
    refetchInterval: RUNS_REFRESH_MS,
    retry: retryUnlessProblem,
    enabled,
  });
}

/** A pool's servers for a named install, read while its list or the picker is open. */
export function useCandidates(mce: string, infraEnv: string, { enabled }: { enabled: boolean }) {
  return useQuery<Candidates>({
    queryKey: inventoryKeys.candidates(mce, infraEnv),
    queryFn: () => inventoryApi.candidates(mce, infraEnv),
    staleTime: 10_000,
    retry: retryUnlessProblem,
    enabled,
  });
}

/** One start: the pool it fills and what to install. */
export interface AddServersVariables {
  mce: string;
  infraEnv: string;
  body: AddServersRequest;
}

/**
 * Start add-server-to-mce on one pool (any InfraEnv name; the workflow checks
 * the MCE has it). Never retried: sent again, it installs more. Whatever the
 * answer, the runs and the pools are read again.
 */
export function useAddServers() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ mce, infraEnv, body }: AddServersVariables) => inventoryApi.addServers(mce, infraEnv, body),
    retry: false,
    onSettled: (_data, _error, { mce, infraEnv }) => {
      void client.invalidateQueries({ queryKey: inventoryKeys.runs });
      void client.invalidateQueries({ queryKey: inventoryKeys.overview });
      void client.invalidateQueries({ queryKey: inventoryKeys.candidates(mce, infraEnv) });
    },
  });
}
