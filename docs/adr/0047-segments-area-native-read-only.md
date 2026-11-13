# ADR-0047: The Segments area is Wingman's own read-only page over segments-manager's open reads, for admins, built as an alpha

Date: 2026-11-13
Status: Accepted

## Context

segments-manager's UI is one read-only page (it lost its writes in July):
per-site cards, then every segment in a table with status tabs, a site
filter, a search, Excel-style column filters, a column picker, copy on click,
CSV and Excel exports, and a refresh every 30 seconds
(`docs/ecosystem/notes/segments-manager.md`). The single-pane plan
(`docs/ideas/single-pane.md`, decisions 10, 13 and 18) moves that UI into
Wingman: an administrator switches between Wingman and Segments from the top
bar, segments-manager's API does not change, and Wingman may reuse its code.
Its reads need no token; its writes need the workflow worker's token, which
Wingman does not hold (ADR-0039).

Wingman already reads one segment for the cluster page (ADR-0039:
`SegmentLedger.segment`, its adapter, cache and fake). segments-manager's GET
answers carry no schema. Its UI reads no URL parameters, so nothing can link
to one cluster's segments in it.

The user asked for the area explicitly (so it is not a thin extra), as an
alpha to look at before deciding what stays.

## Decision

- **A native page, `/segments`, read only.** Wingman's design and states,
  segments-manager's columns and words (Type, Site, VLAN ID, EPG Name,
  Network Segment, DHCP, Cluster, Status). Nothing is ever written to
  segments-manager, and its API does not change. The contract is
  `docs/notes/2026-11-13-segments-area-api.md`.
- **The `SegmentLedger` port grows three reads**, on the same adapter, cache
  and fake (no new adapter, no new Secret): `sites()` (`GET /api/sites`),
  `stats()` (`GET /api/stats`) and `segments(query, fresh=)` (`GET
  /api/segments` with its `site`, `status` and `type` filters). Wingman types
  the answers itself; a record it cannot read is listed as unreadable, and the
  rest are shown.
- **day1 serves them under `/api/day1/segments`**, admins only (`AdminUser`,
  decision 13), `501 FEATURE_DISABLED` while `SEGMENTS_MANAGER_URL` is empty,
  `502 DEPENDENCY_UNAVAILABLE` when segments-manager fails. A failure here
  never reaches a cluster read.
- **Cached for 10 seconds per replica** (ADR-0011), failures never.
  `fresh=true` (the Refresh button) drops day1's cached segments-manager
  answers and asks segments-manager to drop its own, at most once per 5
  seconds per replica, so a held button cannot hammer it; a fresh read inside
  that window is answered from the cache the last one filled, and says so.
- **Holders are joined to the day1 repo.** A holder whose cluster file is in
  day1 links to Wingman's cluster page; any other holder is text. Each row
  carries where segments-manager disagrees with a cluster file, ADR-0039's
  checks seen from the segment, computed from the answer and the cached
  cluster files with no further call.
- **Filters live in the URL**, so the cluster page's link opens
  `/segments?cluster=<name>`: Wingman's own view of that cluster's segments.
  Every link into segments-manager's data goes through one web helper, so a
  link can become a native page in one place.
- **Groundwork, only what this page needs**: the top bar's area switch
  (links, the current area marked, only the areas that exist), one shared
  table on TanStack Table v8 (pinned exactly, ADR-0003) that the Servers
  area can reuse, and Vitest (pinned exactly) for the web's pure logic.
- **The alpha's cuts**, each listed in the contract note: no Excel export
  (the CSV opens in Excel), no connection-status dot (Wingman's error state),
  never the original's `/api/logs`, and a Type filter row instead of
  per-column filter popovers.

## Alternatives rejected

- **Linking to, or framing, segments-manager's UI.** It reads no URL
  parameters, has its own dark-only look, and no cluster link could open it
  filtered.
- **Calling segments-manager from the browser.** Its CORS is open, but the
  plan keeps every system behind a port and an adapter (ADR-0001) with
  Wingman's errors and metrics; the browser never holds a second origin.
- **A per-filter call, as the original makes on every tab and site change.**
  The page reads the whole list once and filters in the browser: switching a
  tab is instant, the CSV is exactly what is shown, and the count stays one
  call per 30 seconds. The route keeps segments-manager's filters for other
  callers.
- **An error for a `fresh` read inside the cool-down.** The cached answer is
  at most seconds old, and a person pressing Refresh twice wants data, not a
  problem.
- **TanStack Table v9** (stable since August 2026). Its API differs from v8's
  throughout; v8 is what the team knows and is enough for these tables. A move
  is one component's change.
- **Porting server-scan's filter tests to Playwright** instead of Vitest:
  pure functions want a unit runner, and Playwright needs a browser and a
  build for each.

## Consequences

- A deployment with `segmentsManager.url` set gets the area for its admins on
  upgrade; nothing else to set (`docs/upgrade/README.md`, 3.15.0).
- Building the web image from source needs Vitest and its dependencies in the
  npm mirror, as with knip; the running image is unchanged (Vitest is a dev
  dependency, kept out of the Next build).
- The Servers area (ADR-0048) builds on the same table, switch and Vitest.

## Verification

- `apps/day1-service/tests/unit/infrastructure/test_segments_manager_reads.py`:
  the three reads against segments-manager's answers, unreadable records,
  failures, the metrics, the cache and `fresh`, and the fake.
- `apps/day1-service/tests/unit/domain/test_segments.py`: holders and the
  mismatch checks.
- `apps/day1-service/tests/api/test_segments_api.py`: admins only, 501 when
  off, 502 when failing, the shapes, the filters and the cool-down.
- `apps/web/lib/segments/*.test.ts` (Vitest): URL state, filter, search, sort
  and the CSV.
- `apps/web/e2e/tests/segments.spec.ts`: the page, the switch, the URL, the
  CSV, and the cluster page's link.
