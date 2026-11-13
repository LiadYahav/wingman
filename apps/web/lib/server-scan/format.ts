/**
 * `45m`, `20h`, `3d`: how old an instant is, for a chip with no room for
 * words (server-scan's Stale chip). Ported from team-redbull/server-scan at
 * 92146d3, `frontend/src/lib/datetime.ts` (decision 18).
 */
export function formatAge(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000));
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}
