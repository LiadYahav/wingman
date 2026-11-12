"use client";

import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { api } from "@/lib/api-client";
import { day2Api, day2Keys, teamAccess, type TeamAccess } from "@/lib/day2";
import { cn } from "@/lib/utils";
import type { Team } from "@/types/day2";

/**
 * Every team and whether Wingman may write to its repo (ADR-0043). A team
 * opts in by giving Wingman's GitLab account Developer on `sigs/<team>`.
 */
export function useTeams() {
  return useQuery<Team[]>({
    queryKey: day2Keys.teams,
    queryFn: () => api.get<Team[]>(day2Api.teams),
    staleTime: 60_000,
  });
}

/**
 * `team`'s write access, from the teams list: not writable until the list
 * says so (fail closed). `pending` is true while the list is loading, when a
 * page holds the reason back rather than flash it.
 */
export function useTeamAccess(team: string): TeamAccess & { pending: boolean } {
  const teams = useTeams();
  return { ...teamAccess(teams.data, team), pending: teams.isPending };
}

/**
 * Why a team's writes are off, next to the action it disables: a sentence on
 * the page, never only a tooltip.
 */
export function ReadOnlyNote({ reason, className }: { reason: string; className?: string }) {
  return (
    <p
      role="note"
      data-testid="read-only-note"
      className={cn(
        "flex items-start gap-1.5 rounded-lg border border-status-warning/30 bg-status-warning/8 px-3 py-2 text-xs text-status-warning-fg",
        className,
      )}
    >
      <Lock className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
      <span className="min-w-0 break-words">{reason}</span>
    </p>
  );
}

/** A small "read-only" chip for a team heading. */
export function ReadOnlyBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-status-warning/12 px-2 py-0.5 text-xs font-medium text-status-warning-fg">
      <Lock className="h-3 w-3" aria-hidden />
      read-only
    </span>
  );
}
