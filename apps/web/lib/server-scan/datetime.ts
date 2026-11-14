/**
 * The one place a Server Scan page formats an instant, as server-scan's UI
 * does: pinned to Israel's zone (`Asia/Jerusalem`) and to day/month/year with
 * a 24-hour clock (`en-GB`), whatever the browser's own zone and locale;
 * relative ("3 hours ago") where a glance is what counts; and a compact age
 * (`20h`) for a chip.
 *
 * Ported from team-redbull/server-scan at 92146d3, `frontend/src/lib/datetime.ts`
 * (decision 18 of the single-pane plan).
 */

const DISPLAY_TIME_ZONE = "Asia/Jerusalem";
const DISPLAY_LOCALE = "en-GB";

/** `15/07/2026, 16:05:00 GMT+3`: the exact instant, in Israel's time. */
export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(DISPLAY_LOCALE, {
    timeZone: DISPLAY_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
    timeZoneName: "short",
  });
}

const RELATIVE = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

/**
 * "3 hours ago", "2 days ago": coarser with distance. Pair it with
 * `formatTimestamp` in a tooltip, so the exact moment is a hover away.
 */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 60) return RELATIVE.format(seconds, "second");
  if (abs < 3600) return RELATIVE.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return RELATIVE.format(Math.round(seconds / 3600), "hour");
  return RELATIVE.format(Math.round(seconds / 86400), "day");
}

/** `45m`, `20h`, `3d`: how old an instant is, for a chip with no room for words (the Stale chip). */
export function formatAge(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000));
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}
