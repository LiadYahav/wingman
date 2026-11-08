"use client";

import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { day2Api, day2Keys } from "@/lib/day2";
import { sameValues, stableStringify, type Values } from "@/lib/values";
import type { MergePreviewBody, ValuesPreview } from "@/types/day2";

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

/**
 * The service's preview of a chart on a destination with `draft` as the
 * file the edit writes. The merge is the service's (Helm's, null deletes a
 * key), never redone here: an unedited draft reads the stored preview, an
 * edited one asks `merge-preview`, a few hundred milliseconds after typing stops.
 */
export function useValuesPreview({
  clusterId,
  team,
  chart,
  version,
  draft,
  baseline,
  enabled = true,
}: {
  clusterId: string;
  team: string;
  chart: string;
  /** Another chart revision to preview; the inherited one when absent. */
  version?: string;
  draft: Values;
  /** The file's current content: a draft equal to it is not an edit. */
  baseline: Values;
  enabled?: boolean;
}) {
  const debounced = useDebounced(draft, 300);
  const edited = !sameValues(debounced, baseline);
  const query = useQuery<ValuesPreview>({
    queryKey: day2Keys.preview(clusterId, team, chart, version ?? "", edited ? stableStringify(debounced) : null),
    queryFn: () => {
      if (!edited) return api.get<ValuesPreview>(day2Api.chart(clusterId, team, chart, version));
      const body: MergePreviewBody = { team, addon: chart, cluster: clusterId, version, override_values: debounced };
      return api.post<ValuesPreview>(day2Api.mergePreview, body);
    },
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
  return {
    ...query,
    /** True while the shown preview is for an older draft. */
    stale: query.isPlaceholderData || !sameValues(draft, debounced),
  };
}
