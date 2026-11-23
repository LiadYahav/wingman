import { useQuery } from "@tanstack/react-query";
import { isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";
import type { Platform } from "@/types";

/** How long the top bar trusts the list: it changes only with day1's settings. */
const PLATFORMS_STALE_MS = 5 * 60_000;

/**
 * The systems beside Wingman, each with its own UI's address (ADR-0066).
 * Asked by admins only, as
 * day1 answers it; a viewer, an answer still on its way and a failed read are
 * all `[]`: no link out.
 */
export function usePlatforms(): Platform[] {
  const admin = useIsAdmin();
  const mounted = useMounted();
  const read = useQuery({
    queryKey: day1Keys.fleet.platforms,
    queryFn: day1Api.fleet.platforms,
    staleTime: PLATFORMS_STALE_MS,
    // A problem is day1's answer (403 for a viewer): don't ask again
    retry: (count, error) => !isApiError(error) && count < 2,
    enabled: admin && mounted,
  });
  return (admin && mounted && read.data?.platforms) || [];
}
