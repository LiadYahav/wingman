/**
 * A cluster's nodes by NodePool, as its MCE reports them with server-scan
 * joined in, and the uninstall of one server
 * (docs/notes/2026-11-11-cluster-nodes-api.md, ADR-0038). Wingman only starts
 * the platform's `uninstall-server-from-hc` workflow and shows its run: the
 * procedure and its checks are the workflow's, so nothing here knows its
 * phases, and a phase the workflow adds or renames needs no change here.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import type { ClusterNodes, NodeState, ServerRecord, UninstallNodeRequest, WorkflowRun } from "@/types";

/** The nodes, or "off": day1 answers 501 FEATURE_DISABLED when it cannot read the MCE (live status is off). */
export type NodesRead = { off: false; data: ClusterNodes } | { off: true; detail: string };

/** How often the nodes are read again while something moves (an update, a Machine coming or going, a run), and otherwise. */
const BUSY_POLL_MS = 10_000;
const IDLE_POLL_MS = 60_000;

/** A Machine on its way somewhere: worth watching. A `waiting` one can wait for hours, so it is not. */
const MOVING: ReadonlySet<NodeState> = new Set(["deleting", "installing", "joining"]);

export const isRunning = (run: WorkflowRun | null | undefined): boolean => run?.status === "running";

/** Something on the page is changing: read it again soon. */
function isBusy(data: ClusterNodes): boolean {
  return (
    data.node_pools.some(
      (pool) => pool.update !== null || pool.nodes.some((n) => n.current || MOVING.has(n.state) || isRunning(n.uninstall))
    ) || data.unassigned.some((s) => isRunning(s.uninstall))
  );
}

/**
 * Refusals after which the page is out of date (the server left the
 * cluster, a run is already going, or the start may have happened): the
 * nodes are read again, and the dialog offers no retry.
 */
export const STALE_LIST_CODES = ["NODE_NOT_IN_CLUSTER", "UNINSTALL_ALREADY_RUNNING", "AMBIGUOUS_WRITE"] as const;

/**
 * Another system's own string in words, with no list of them kept:
 * `awaiting-machine-deletion` → "Awaiting machine deletion", `timed_out` →
 * "Timed out". Upper-case states (server-scan's) are lowered first.
 */
export function humanize(slug: string): string {
  const words = (slug === slug.toUpperCase() ? slug.toLowerCase() : slug).replace(/[-_\s]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : slug;
}

/**
 * `GET /clusters/{name}/nodes{where}`, read where it is shown (`enabled`).
 * Read again every 10 s while something moves (or `watching`: a run was just
 * started here), else every minute.
 */
export function useClusterNodes(
  name: string,
  where: string,
  { enabled = true, watching = false }: { enabled?: boolean; watching?: boolean } = {}
) {
  return useQuery<NodesRead>({
    queryKey: day1Keys.clusters.nodes(name),
    queryFn: async () => {
      try {
        return { off: false, data: await day1Api.clusters.nodes(name, where) };
      } catch (e) {
        if (isApiError(e, "FEATURE_DISABLED")) return { off: true, detail: e.message };
        throw e;
      }
    },
    enabled,
    staleTime: 10_000,
    // A problem is day1's answer (a 502 says the MCE did not answer): show it, with a retry
    retry: (count, error) => !isApiError(error) && count < 2,
    refetchInterval: (query) => {
      const read = query.state.data;
      if (!read || read.off) return false;
      return watching || isBusy(read.data) ? BUSY_POLL_MS : IDLE_POLL_MS;
    },
  });
}

/**
 * `POST /clusters/{name}/nodes/{server_id}/uninstall{where}` with the name the
 * person typed. Never retried (ADR-0006). On success, and on a refusal that
 * says the page is out of date, the nodes are read again.
 */
export function useUninstallNode(name: string, where: string) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: day1Keys.clusters.nodes(name) });
  return useMutation({
    mutationFn: ({ server, typed }: { server: ServerRecord; typed: string }) =>
      day1Api.clusters.uninstallNode(name, server.id, where, { server_name: typed } satisfies UninstallNodeRequest),
    onSuccess: () => void refresh(),
    onError: (error) => {
      if (STALE_LIST_CODES.some((code) => isApiError(error, code))) void refresh();
    },
  });
}
