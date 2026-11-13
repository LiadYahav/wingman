/**
 * A cluster's upgrade through the platform's upgrade-cluster workflow
 * (docs/notes/2026-11-13-upgrade-cluster-workflow-api.md, ADR-0055): the
 * targets, the start, the run and the decisions. Wingman starts the run,
 * shows it and passes decisions on; the run's validators judge them. Writes
 * are never retried (ADR-0006): a refusal that says the page is out of date
 * reads the run again instead.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { isOpen } from "@/lib/upgrade";
import type {
  ErrorCode,
  FleetUpgrade,
  StartUpgradeRequest,
  UpgradeDecision,
  UpgradeDecisionRequest,
  UpgradeRun,
  UpgradeTargets,
} from "@/types";

/** Upgrades off (501 FEATURE_DISABLED: the web shows nothing), on with no run yet, or the newest run. */
export type UpgradeRead = { state: "off" } | { state: "none" } | { state: "run"; run: UpgradeRun };

/** Upgrades off, or every cluster's newest run (`GET /api/day1/upgrades`). */
export type FleetUpgradesRead = { state: "off" } | { state: "on"; runs: FleetUpgrade[] };

/** How often an open run is read again. */
const RUN_POLL_MS = 10_000;

/** How often the fleet's runs are read again while shown; day1 keeps the orchestrator's answer 10 s. */
const FLEET_POLL_MS = 15_000;

/** Refusals after which the run on the page is out of date: it is read again. */
const STALE_RUN_CODES: readonly ErrorCode[] = [
  "AMBIGUOUS_WRITE",
  "UPGRADE_ALREADY_RUNNING",
  "UPGRADE_DECISION_REFUSED",
  "NOT_FOUND",
];

const runKey = day1Keys.clusters.upgradeRun;

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
        return { state: "run", run: await day1Api.clusters.upgradeRun(name, where) };
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
    queryKey: day1Keys.clusters.upgradeTargets(name),
    queryFn: () => day1Api.clusters.upgradeTargets(name, where),
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
    mutationFn: (body: StartUpgradeRequest) => day1Api.clusters.startUpgrade(name, where, body),
    onSuccess: (run) => updates.show(run),
    onError: updates.refreshIfStale,
  });
}

/** `POST /clusters/{name}/upgrade-run/{decision}{where}`: day1 adds who decided. Never retried. */
export function useUpgradeDecision(name: string, where: string) {
  const updates = useRunUpdates(name);
  return useMutation({
    mutationFn: ({ decision, body }: { decision: UpgradeDecision; body: UpgradeDecisionRequest }) =>
      day1Api.clusters.decideUpgrade(name, where, decision, body),
    onSuccess: (result) => updates.show(result.run),
    onError: updates.refreshIfStale,
  });
}

/** `POST /clusters/{name}/upgrade-run/actions/{id}/approve|reject{where}`: an agent's proposal. */
export function useUpgradeActionDecision(name: string, where: string) {
  const updates = useRunUpdates(name);
  return useMutation({
    mutationFn: ({ actionId, approve }: { actionId: string; approve: boolean }) =>
      day1Api.clusters.decideUpgradeAction(name, where, actionId, approve),
    onSuccess: (result) => updates.show(result.run),
    onError: updates.refreshIfStale,
  });
}

/**
 * Every cluster's newest upgrade run, for the Clusters page's Upgrades view
 * and its "Upgrading" badges, which share this one query (ADR-0055's
 * amendment). Upgrades off (501 FEATURE_DISABLED): the page shows neither.
 */
export function useFleetUpgrades() {
  return useQuery<FleetUpgradesRead>({
    queryKey: day1Keys.clusters.upgrades,
    queryFn: async () => {
      try {
        return { state: "on", runs: (await day1Api.clusters.upgrades()).runs };
      } catch (e) {
        if (isApiError(e, "FEATURE_DISABLED")) return { state: "off" };
        throw e;
      }
    },
    staleTime: 10_000,
    refetchInterval: FLEET_POLL_MS,
    retry: false,
  });
}
