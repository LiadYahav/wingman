"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { day1Api, day1Keys } from "@/lib/api/day1";
import type { CreateKvCluster, KvChoices, KvDraft, ProvisionRun } from "@/types";

/**
 * A seed's next KV cluster for the dialog's choices (ADR-0069), read again as
 * they change; the last draft stays shown while the next one is read.
 */
export function useKvDraft(seed: string, choices: KvChoices) {
  return useQuery<KvDraft>({
    queryKey: day1Keys.seeds.kvDraft(seed, choices),
    queryFn: () => day1Api.seeds.kvDraft(seed, choices),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

/** Start provision-cluster on the seed with the draft's file: sent once, never retried (ADR-0006). */
export function useCreateKvCluster(seed: string) {
  return useMutation<ProvisionRun, unknown, CreateKvCluster>({
    mutationFn: (body) => day1Api.seeds.createKvCluster(seed, body),
  });
}
