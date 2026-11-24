/**
 * The query cache is one user's. providers.tsx keeps it in localStorage for
 * minutes (`QUERY_CACHE_KEY`), and an admin's reads hold what a viewer never
 * knows (the MCEs, the KV clusters, Inventory, ADR-0068): so a sign-out, an
 * expired session and a sign-in as someone else start it empty, in memory and
 * in storage.
 */

export const QUERY_CACHE_KEY = "wingman-query-cache";

/** Drop the stored cache; storage may be unavailable (a private window). */
export function forgetStoredQueries(): void {
  try {
    window.localStorage.removeItem(QUERY_CACHE_KEY);
  } catch {
    /* storage unavailable */
  }
}

/** Whether two signed-in users are the same one, in the same role. */
export function sameUser(
  a: { username: string; role: string } | null,
  b: { username: string; role: string } | null
): boolean {
  return a?.username === b?.username && a?.role === b?.role;
}
