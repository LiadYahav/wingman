/**
 * A pool's free servers, ready or needing a fix, and installing one that
 * needs a fix (ADR-0057's 3.38.0 amendment). The platform's add-server-to-mce
 * waives its health checks for named servers when asked (`allow_unhealthy`),
 * never its safety refusals and never on a pool draw. The dialog sends it
 * only once the person confirms; these are its pure parts. The numbers and
 * each server's group are day1's: nothing is recounted here.
 */

import type { AddServersRequest, Candidate, PoolCount } from "@/types/inventory";

export type CandidateGroup = "ready" | "needs-fix" | "not-offered";

/** A group's heading and what it means. */
export interface GroupInfo {
  group: CandidateGroup;
  label: string;
  hint: string;
}

/** Each group, in the order they are listed. */
const GROUPS: readonly GroupInfo[] = [
  {
    group: "ready",
    label: "Ready",
    hint: "Healthy and reachable in server-scan, unlocked, out of maintenance: a pool draw could pick these today. The workflow still checks each one itself (its NICs' links, a live recheck), so a run may still refuse one.",
  },
  {
    group: "needs-fix",
    label: "Needs fix",
    hint: "server-scan does not call these healthy, or cannot reach their BMC: a pool draw never picks them. An admin may install one by name, with the workflow's health checks waived, after confirming.",
  },
  {
    group: "not-offered",
    label: "Not offered",
    hint: "Locked, in maintenance or contested: the workflow refuses these whatever is asked, so they cannot be picked.",
  },
];

function candidateGroup(candidate: Candidate): CandidateGroup {
  if (!candidate.offered) return "not-offered";
  return candidate.ready ? "ready" : "needs-fix";
}

/** The candidates by group, in `GROUPS`' order, leaving out the empty groups; day1's order within each. */
export function groupCandidates(candidates: readonly Candidate[]): { group: GroupInfo; candidates: Candidate[] }[] {
  return GROUPS.map((group) => ({ group, candidates: candidates.filter((c) => candidateGroup(c) === group.group) })).filter(
    (found) => found.candidates.length > 0
  );
}

/** The chosen servers that need a fix, in the order chosen; a name the list lacks is left out. */
export function needsFixChosen(names: readonly string[], candidates: readonly Candidate[] | undefined): Candidate[] {
  const byName = new Map((candidates ?? []).map((c) => [c.name, c]));
  return names.flatMap((name) => {
    const found = byName.get(name);
    return found && candidateGroup(found) === "needs-fix" ? [found] : [];
  });
}

/** The body with the health waiver. Only a named install carries it: a pool draw is sent as it is. */
export function withWaiver(body: AddServersRequest): AddServersRequest {
  return "server_names" in body ? { server_names: body.server_names, allow_unhealthy: true } : body;
}

/** The health checks the workflow waives for every server of the request, in its terms. */
export const WAIVED =
  "server-scan's health, its network (two link-up NICs), the BMC's reachability, server-scan's live recheck, and a bond member whose link is down";

/** What the waiver never passes. */
export const STILL_REFUSED =
  "a server a cluster claims, contested, in maintenance or locked by another run, and an InfraEnv the MCE lacks";

/** `2 available + 1 ready + 1 needs a fix`: the sum behind a total. */
export function totalSum({ available, ready, needs_fix }: Pick<PoolCount, "available" | "ready" | "needs_fix">): string {
  const fix = needs_fix ?? 0;
  return `${available} available + ${ready ?? 0} ready + ${fix} ${fix === 1 ? "needs" : "need"} a fix`;
}
