"use client";

import { createContext, use, useCallback, useState, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { day1Keys } from "@/lib/api/day1";
import { useMounted } from "@/hooks/use-mounted";
import { clusterOfPath, isKvCluster, workspaceOf, type WorkspaceId } from "@/lib/workspaces";
import { useIsAdmin } from "@/stores/auth-store";
import type { ClusterDetail, ClusterStatus } from "@/types";

/** The workspace the shell shows: the switch and the sidebar read it (ADR-0067). */
export const WorkspaceContext = createContext<WorkspaceId>("customers");

export const useWorkspace = (): WorkspaceId => use(WorkspaceContext);

/**
 * What the cache holds under `key`, kept current. Not an observer of the
 * query: an observer without the page's own `queryFn` would become the
 * query's fetcher, so this only listens to the cache.
 */
function useCached<T>(key: QueryKey): T | undefined {
  const client = useQueryClient();
  const subscribe = useCallback((onChange: () => void) => client.getQueryCache().subscribe(onChange), [client]);
  return useSyncExternalStore(subscribe, () => client.getQueryData<T>(key), () => undefined);
}

/** Whether `name` is a KV cluster, from what the page already read; `undefined` until known. */
function useIsKvCluster(name: string | null, enabled: boolean): boolean | undefined {
  const detail = useCached<ClusterDetail>(day1Keys.clusters.detail(name ?? ""));
  const list = useCached<ClusterStatus[]>(day1Keys.clusters.all);
  if (!enabled || name === null) return undefined;
  const known = detail ?? list?.find((cluster) => cluster.name === name);
  return known ? isKvCluster(known) : undefined;
}

/**
 * The workspace of the page shown, for the shell (`WorkspaceContext`): by
 * its path, a cluster's by its kind, a shared page's the one before. A
 * viewer's, and anyone's before the role is known (the server's render), is
 * Customers.
 */
export function useWorkspaceOfPage(): WorkspaceId {
  const pathname = usePathname();
  const isAdmin = useIsAdmin();
  const mounted = useMounted();
  const admin = isAdmin && mounted;
  const name = clusterOfPath(pathname);
  const kvCluster = useIsKvCluster(name, admin);
  // The workspace of the page before: a shared page, or a cluster not read yet, keeps it
  const [previous, setPrevious] = useState<WorkspaceId>("customers");
  const id = workspaceOf(pathname, { admin, kvCluster, previous });
  if (id !== previous) setPrevious(id);
  return id;
}
