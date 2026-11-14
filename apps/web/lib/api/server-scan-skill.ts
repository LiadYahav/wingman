/**
 * day1's Claude page routes (docs/notes/2026-11-13-server-scan-area-api.md
 * §12, ADR-0048's 3.29.0 amendment): server-scan's skill, read through day1,
 * and its zip. Admins only, as the area; `501` when server-scan is not
 * configured, `404` when it carries no skill.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import { saveBlob } from "@/components/data-table/download";
import { api } from "@/lib/api-client";
import { retryUnlessProblem } from "@/lib/api/server-scan";
import type { SkillAnswer } from "@/types/server-scan-skill";

/** As server-scan's page: the skill is read again every minute and on window focus, so an edit shows up. */
const SKILL_POLL_MS = 60_000;
const SKILL_PATH = "/api/day1/server-scan/skill";

/** server-scan's Claude Code skill, with where server-scan is for people and the token line its zip names. */
export function useServerScanSkill() {
  return useQuery<SkillAnswer>({
    queryKey: ["server-scan", "skill"],
    queryFn: () => api.get<SkillAnswer>(SKILL_PATH),
    staleTime: 0,
    refetchInterval: SKILL_POLL_MS,
    refetchOnWindowFocus: true,
    retry: retryUnlessProblem,
  });
}

/**
 * The download: server-scan's zip of the skill, its address already in it,
 * fetched through day1 with the session's token and handed to the browser
 * as `<name>.zip`. A read, so a failure is shown, not retried.
 */
export function useSkillDownload(name: string) {
  return useMutation({
    mutationFn: async () => saveBlob(`${name}.zip`, await api.getBlob(`${SKILL_PATH}/download`)),
    retry: false,
  });
}
