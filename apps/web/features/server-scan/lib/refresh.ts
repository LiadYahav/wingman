/**
 * Fetch now's words and decisions (docs/notes/2026-11-13-server-scan-area-api.md
 * §9.9, ADR-0048's v6.6.0 amendment): one server read from its vendor
 * manager now, from a server's page or a Servers row.
 *
 * Ported from team-redbull/server-scan (decision 18): `RefreshButton.tsx`
 * (v6.5.0, its 827cd97), `RowRefreshButton.tsx` (v6.6.0, its 55b6391) and
 * `refreshError.ts`, their words and their tests' cases (`refresh.test.ts`).
 * server-scan greys the buttons for a viewer or an auditor; here the area is
 * for admins already, so they are greyed when Wingman holds no admin token
 * (`refresh_available`), with day1's line saying so.
 *
 * What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
 */

import { errorMessages } from "@/lib/api-client";

/** The server page's button: its tooltip, in server-scan's words. */
export const FETCH_TITLE = "Read this server from its vendor manager now, instead of waiting for the collector";
/** The server page's button's name: never "maintenance" nor the bare server name (two other controls have them). */
export const FETCH_LABEL = "Fetch this server's data now";
/** What the buttons say while day1 waits, which can be minutes for a UCS Central server. */
export const FETCHING = "Fetching…";

/** A row's button's name and tooltip. */
export const rowFetchLabel = (name: string) => `Fetch data of ${name} now`;

/** What a Fetch now that read the server says: who, and from which manager. */
export interface FetchedToast {
  title: string;
  description: string;
}

/**
 * The toast after a Fetch now. With `before`, the revision the page showed,
 * it also says whether server-scan found anything new: `revision` moves only
 * when the content changed. A row does not know its revision, so it says less.
 */
export function fetchedToast(fresh: { name: string; source_provider: string | null; revision: number | null }, before?: number | null): FetchedToast {
  const from = `From ${fresh.source_provider ?? "its manager"}`;
  if (before === undefined || before === null || fresh.revision === null) return { title: `Fetched ${fresh.name}`, description: from };
  return { title: `Fetched ${fresh.name}`, description: `${from}${fresh.revision === before ? " — no changes" : " — data updated"}` };
}

/** Why a Fetch now failed, in the API's words (server-scan's own, when it refused). */
export function fetchFailure(error: unknown): string {
  return errorMessages(error)[0] ?? "Failed to fetch the server.";
}

/** A button's state: its name and tooltip, and whether pressing it does anything. */
export interface FetchControl {
  label: string;
  title: string;
  /** `aria-disabled`, not `disabled`, so the tooltip still shows. */
  off: boolean;
}

/** The control for this deployment: off, with day1's line as its name, without the admin token. */
export function fetchControl(available: boolean, detail: string | null, label: string, title: string = label): FetchControl {
  if (available) return { label, title, off: false };
  const why = detail ?? "Fetch now is not available here";
  return { label: why, title: why, off: true };
}
