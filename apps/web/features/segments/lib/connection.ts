/**
 * Whether segments-manager answered the page's last refresh, as the
 * original's connection state (`updateConnectionStatus`) tracks it: the
 * 30-second re-read and the Refresh button are attempts, and the latest one
 * decides. A failed attempt never drops the rows: the page keeps showing the
 * last good read.
 */

/** One refresh: when it ended, and why it failed (`null`: it succeeded). */
export interface Attempt {
  at: number;
  failure: string | null;
}

export interface Connection {
  state: "online" | "offline";
  label: string;
}

/** The dot's words, which its tooltip and its accessible name say. */
export const onlineLabel = "segments-manager answered the last refresh";
export const offlineLabel = (reason: string) =>
  `segments-manager didn't answer the last refresh: ${reason}; showing the last good data`;

/** The latest attempt decides; at the same moment a failure wins. `online` with none yet. */
export function connection(attempts: readonly Attempt[]): Connection {
  const latest = attempts.reduce<Attempt | null>(
    (last, attempt) => (!last || attempt.at > last.at || (attempt.at === last.at && attempt.failure !== null) ? attempt : last),
    null
  );
  return latest?.failure != null ? { state: "offline", label: offlineLabel(latest.failure) } : { state: "online", label: onlineLabel };
}
