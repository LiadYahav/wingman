/**
 * A cluster's upgrade through the platform's upgrade-cluster workflow
 * (docs/notes/2026-11-13-upgrade-cluster-workflow-api.md, ADR-0055): the
 * targets, the start, the run and the decisions. Wingman starts the run,
 * shows it and passes decisions on; the run's validators judge them. Writes
 * are never retried (ADR-0006): a refusal that says the page is out of date
 * reads the run again instead.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api-client";
import { isOpen } from "@/lib/upgrade";
import type {
  ErrorCode,
  StartUpgradeRequest,
  UpgradeDecision,
  UpgradeDecisionRequest,
  UpgradeDecisionResult,
  UpgradeRun,
  UpgradeTargets,
} from "@/types";

/** Upgrades off (501 FEATURE_DISABLED: the web shows nothing), on with no run yet, or the newest run. */
export type UpgradeRead = { state: "off" } | { state: "none" } | { state: "run"; run: UpgradeRun };

/** How often an open run is read again. */
const RUN_POLL_MS = 10_000;

/** Refusals after which the run on the page is out of date: it is read again. */
const STALE_RUN_CODES: readonly ErrorCode[] = [
  "AMBIGUOUS_WRITE",
  "UPGRADE_ALREADY_RUNNING",
  "UPGRADE_DECISION_REFUSED",
  "NOT_FOUND",
];

const runKey = (name: string) => ["clusters", name, "upgrade-run"] as const;
const targetsKey = (name: string) => ["clusters", name, "upgrade-targets"] as const;
const clusterPath = (name: string) => `/api/day1/clusters/${encodeURIComponent(name)}`;

/** Whether a failed write leaves the page's run out of date. */
export const staleRun = (error: unknown): boolean => STALE_RUN_CODES.some((code) => isApiError(error, code));

/**
 * `GET /clusters/{name}/upgrade-run{where}`, shared by the Upgrade action and
 * the panel. Read again every 10 s while the run is open.
 */
export function useUpgradeRun(name: string, where: string, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery<UpgradeRead>({
    queryKey: runKey(name),
    queryFn: async () => {
      try {
        return { state: "run", run: await api.get<UpgradeRun>(`${clusterPath(name)}/upgrade-run${where}`) };
      } catch (e) {
        if (isApiError(e, "FEATURE_DISABLED")) return { state: "off" };
        if (isApiError(e, "NOT_FOUND")) return { state: "none" };
        throw e;
      }
    },
    enabled,
    staleTime: 10_000,
    retry: false,
    refetchInterval: (query) => {
      const read = query.state.data;
      return read?.state === "run" && isOpen(read.run) ? RUN_POLL_MS : false;
    },
  });
}

/**
 * `GET /clusters/{name}/upgrade-targets{where}`, read while the dialog is
 * open. It starts a short run of the workflow and can take up to a minute;
 * never retried, and kept for half a minute.
 */
export function useUpgradeTargets(name: string, where: string, enabled: boolean) {
  return useQuery<UpgradeTargets>({
    queryKey: targetsKey(name),
    queryFn: () => api.get<UpgradeTargets>(`${clusterPath(name)}/upgrade-targets${where}`),
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}

/** Keeps the run query current after a write: the run it answered, or a fresh read. */
function useRunUpdates(name: string) {
  const queryClient = useQueryClient();
  return {
    show: (run: UpgradeRun | null) =>
      run
        ? queryClient.setQueryData<UpgradeRead>(runKey(name), { state: "run", run })
        : void queryClient.invalidateQueries({ queryKey: runKey(name) }),
    refreshIfStale: (error: unknown) => {
      if (staleRun(error)) void queryClient.invalidateQueries({ queryKey: runKey(name) });
    },
  };
}

/** `POST /clusters/{name}/upgrade{where}`: day1 adds the cluster and who asked. Never retried. */
export function useStartUpgrade(name: string, where: string) {
  const updates = useRunUpdates(name);
  return useMutation({
    mutationFn: (body: StartUpgradeRequest) => api.post<UpgradeRun>(`${clusterPath(name)}/upgrade${where}`, body),
    onSuccess: (run) => updates.show(run),
    onError: updates.refreshIfStale,
  });
}

/** `POST /clusters/{name}/upgrade-run/{decision}{where}`: day1 adds who decided. Never retried. */
export function useUpgradeDecision(name: string, where: string) {
  const updates = useRunUpdates(name);
  return useMutation({
    mutationFn: ({ decision, body }: { decision: UpgradeDecision; body: UpgradeDecisionRequest }) =>
      api.post<UpgradeDecisionResult>(`${clusterPath(name)}/upgrade-run/${decision}${where}`, body),
    onSuccess: (result) => updates.show(result.run),
    onError: updates.refreshIfStale,
  });
}

/** `POST /clusters/{name}/upgrade-run/actions/{id}/approve|reject{where}`: an agent's proposal. */
export function useUpgradeActionDecision(name: string, where: string) {
  const updates = useRunUpdates(name);
  return useMutation({
    mutationFn: ({ actionId, approve }: { actionId: string; approve: boolean }) =>
      api.post<UpgradeDecisionResult>(
        `${clusterPath(name)}/upgrade-run/actions/${encodeURIComponent(actionId)}/${approve ? "approve" : "reject"}${where}`
      ),
    onSuccess: (result) => updates.show(result.run),
    onError: updates.refreshIfStale,
  });
}
