/**
 * A seed's own calls (ADR-0069): the next KV cluster's draft, and its create
 * through provision-cluster. Admins only; the run is read as any create's
 * (`day1Api.clusters.provisionRun`).
 */

import { api } from "@/lib/api-client";
import type { CreateKvCluster, KvChoices, KvDraft, ProvisionRun } from "@/types";

const seedPath = (seed: string) => `/api/day1/seeds/${encodeURIComponent(seed)}`;

/** The draft's query: each choice made, the owner's numbers as `owner_<key>`. */
function draftQuery(choices: KvChoices): string {
  const params = new URLSearchParams();
  for (const key of ["zone", "infra_env", "mastertag"] as const) {
    const value = choices[key];
    if (value) params.set(key, value);
  }
  if (choices.workers !== undefined) params.set("workers", String(choices.workers));
  for (const [key, value] of Object.entries(choices.owner ?? {})) if (value) params.set(`owner_${key}`, value);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export const seedsApi = {
  kvDraft: (seed: string, choices: KvChoices) => api.get<KvDraft>(`${seedPath(seed)}/kv-cluster-draft${draftQuery(choices)}`),
  createKvCluster: (seed: string, body: CreateKvCluster) => api.post<ProvisionRun>(`${seedPath(seed)}/kv-clusters`, body),
};
