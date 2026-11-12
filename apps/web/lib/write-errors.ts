/**
 * How a write that did not go through is told to the person who asked for
 * it, on day1 and day2 pages alike. Most failed writes were refused: nothing
 * changed. An unconfirmed one (`AMBIGUOUS_WRITE`, ADR-0006) was not: GitLab
 * did not answer the commit, merge or close, so it may have happened, and
 * Wingman never retries it. Calling it "refused" or "failed" invites a retry
 * that opens a second merge request.
 */

/** What an unconfirmed write means for the person who asked for it. */
export const AMBIGUOUS_WRITE_HINT =
  "GitLab did not confirm the change, so it may or may not have been made. Check GitLab for the merge request before trying again.";

/**
 * GitLab did not confirm a write; it may have happened. Reads `code` from
 * an `ApiError` or from a problem read off one (`problemOf` in lib/day2).
 */
export function isAmbiguousWrite(error: unknown): boolean {
  return typeof error === "object" && error !== null && (error as { code?: unknown }).code === "AMBIGUOUS_WRITE";
}

/**
 * The heading of a failed write: `refused` (what the page calls a refusal
 * there), or what an unconfirmed write means.
 */
export function writeErrorTitle(error: unknown, refused = "The change was refused"): string {
  if (isAmbiguousWrite(error)) return AMBIGUOUS_WRITE_HINT;
  return isTeamReadOnlyError(error) ? "This team is read-only in Wingman" : refused;
}

/**
 * A day2 team that has not given Wingman's GitLab account write access to its
 * project (`TEAM_READ_ONLY`, ADR-0043): nothing was written, and retrying
 * will not help until the team opts in. The problem's detail says how.
 */
export function isTeamReadOnlyError(error: unknown): boolean {
  return typeof error === "object" && error !== null && (error as { code?: unknown }).code === "TEAM_READ_ONLY";
}
