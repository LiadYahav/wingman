/**
 * A cluster's nodes as server-scan reports them, and the uninstall of one
 * (docs/notes/2026-11-11-cluster-nodes-api.md, ADR-0038). Wingman only starts
 * the platform's `uninstall-server-from-hc` workflow and shows its run: the
 * procedure and its checks are the workflow's, so nothing here knows its
 * phases, and a phase the workflow adds or renames needs no change here.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api-client";
import type { ClusterNode, ClusterNodes, UninstallNodeRequest, WorkflowRun } from "@/types";

/** The nodes, or "off": day1 answers 501 FEATURE_DISABLED when server-scan is not configured. */
export type NodesRead = { off: false; data: ClusterNodes } | { off: true; detail: string };

export const nodesKey = (name: string) => ["clusters", name, "nodes"] as const;

/** How often the nodes are read again while an uninstall runs, and otherwise. */
export const RUNNING_POLL_MS = 10_000;
export const IDLE_POLL_MS = 60_000;

const nodesPath = (name: string) => `/api/day1/clusters/${encodeURIComponent(name)}/nodes`;

export const isRunning = (run: WorkflowRun | null | undefined): boolean => run?.status === "running";

/**
 * Refusals after which the list on screen is out of date (the server left the
 * cluster, a run is already going, or the start may have happened): the
 * nodes are read again, and the dialog offers no retry.
 */
export const STALE_LIST_CODES = ["NODE_NOT_IN_CLUSTER", "UNINSTALL_ALREADY_RUNNING", "AMBIGUOUS_WRITE"] as const;

/**
 * A workflow's own string in words, with no list of them kept:
 * `awaiting-machine-deletion` → "Awaiting machine deletion", `timed_out` →
 * "Timed out". server-scan's upper-case states are lowered first.
 */
export function humanize(slug: string): string {
  const words = (slug === slug.toUpperCase() ? slug.toLowerCase() : slug).replace(/[-_\s]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : slug;
}

/**
 * `GET /clusters/{name}/nodes{where}`. Mount it only where the nodes are
 * shown (`enabled`): a list row reads its cluster's nodes once expanded. It is
 * read again every 10 s while a run is `running` (or `watching`: a run was just
 * started), else every minute.
 */
export function useClusterNodes(
  name: string,
  where: string,
  { enabled = true, watching = false }: { enabled?: boolean; watching?: boolean } = {}
) {
  return useQuery<NodesRead>({
    queryKey: nodesKey(name),
    queryFn: async () => {
      try {
        return { off: false, data: await api.get<ClusterNodes>(`${nodesPath(name)}${where}`) };
      } catch (e) {
        if (isApiError(e, "FEATURE_DISABLED")) return { off: true, detail: e.message };
        throw e;
      }
    },
    enabled,
    staleTime: 30_000,
    // A problem is day1's answer (a 502 says server-scan did not answer): show it, with a retry
    retry: (count, error) => !isApiError(error) && count < 2,
    refetchInterval: (query) => {
      const read = query.state.data;
      if (!read || read.off) return false;
      return watching || read.data.nodes.some((n) => isRunning(n.uninstall)) ? RUNNING_POLL_MS : IDLE_POLL_MS;
    },
  });
}

/**
 * `POST /clusters/{name}/nodes/{server_id}/uninstall{where}` with the name the
 * person typed. Never retried (ADR-0006). On success, and on a refusal that
 * says the list is out of date, the nodes are read again.
 */
export function useUninstallNode(name: string, where: string) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: nodesKey(name) });
  return useMutation({
    mutationFn: ({ node, typed }: { node: ClusterNode; typed: string }) =>
      api.post<WorkflowRun>(
        `${nodesPath(name)}/${encodeURIComponent(node.id)}/uninstall${where}`,
        { server_name: typed } satisfies UninstallNodeRequest
      ),
    onSuccess: () => void refresh(),
    onError: (error) => {
      if (STALE_LIST_CODES.some((code) => isApiError(error, code))) void refresh();
    },
  });
}
