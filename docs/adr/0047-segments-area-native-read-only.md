# ADR-0047: The Segments area is Wingman's own read-only page over segments-manager's open reads, for admins, built as an alpha

Date: 2026-11-13
Status: Accepted; amended 2026-11-13 (each area has its own sidebar and brand), and 2026-11-13 for 3.21.0 (full parity)

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

## Amendments

**2026-11-13, 3.17.0: each area has its own sidebar and brand.** The user,
on seeing the alpha: in Segments the sidebar should be segments-manager's,
not Wingman's, and the top left should say which platform you are in.

- **The brand** (top left) is the current area's: Wingman's logo and name in
  Wingman; in Segments, a server-rack mark (lucide's `Server`, as the
  original's header) and "Segments Manager". It links to the area's home.
- **The sidebar** is the area's. Wingman's stays its own list
  (`sidebar-nav.tsx`, unchanged). The original has no sidebar, so the
  Segments one is the page's own options, each a link that sets the URL
  filters (the rest of the view stays) and is marked from the URL:
  **Segments** (All, Available, Allocated, Disagrees with Git), **Sites**
  (every site with used out of total, from the same stats query and cache
  as the cards; a site without segments too) and **Help** (Documentation:
  Wingman's docs page, which has no Segments part yet).
- **The top bar's switch** is the "Platform" landmark, the current one
  marked with `aria-current`; no text was added.
- **Data, not layout.** `apps/web/lib/areas.ts` holds each area's switch
  label, home and brand, and the types of a data-driven sidebar
  (`NavSection`); `lib/segments/sidebar.ts` builds the Segments sections;
  the shell picks the brand and the sidebar by area. A page wears its
  area's chrome only for someone who has the area: a viewer on `/segments`
  sees Wingman's.

Verification: `apps/web/lib/areas.test.ts` and
`apps/web/lib/segments/sidebar.test.ts` (Vitest), and
`apps/web/e2e/tests/area-chrome.spec.ts`.

**2026-11-13, 3.21.0: full parity (decision 22).** The user chose Option C:
every feature of segments-manager's page, in Wingman's look. The alpha's
cuts are built; the original's `/api/logs` never is.

- **A filter on every column, in the shared table.** A column opts in with
  `meta.filterValue` (its cell as text). With `DataTable`'s `filters` prop
  (`rows`, `value`, `onChange`), its header gets a funnel. The funnel opens
  the column's distinct values with checkboxes, a search among them, select
  all or none, Apply and Clear, and stays marked while the column filters.
  The table only draws. The caller keeps the `ColumnFilters` (a column id
  to the values it keeps) and filters with `applyColumnFilters` from
  `apps/web/lib/table/column-filters.ts`, which also reads and writes them
  as URL parameters (`f.<column>`, once per value). The Server Scan area
  reuses it as is.
  - As in the original: the values come from the rows before any column
    filter (its `lastBaseSegments`: after the status, the site and the
    search; here also the holder and "Disagrees with Git"). A value is the
    cell's text, and keeping every value is no filter.
  - Unlike the original: the filters live in the URL, and the status tabs
    count under them. An active filter is also a chip, so a filter on a
    hidden column stays in sight. Apply is disabled with nothing kept, so a
    filter never empties the table by accident.
  - The Type row (the alpha's stand-in) is gone. A `type=HC,UPI` link from
    3.15 to 3.20 still opens with the Type column filtered.
- **The Excel export, written in the browser** from the rows shown, beside
  the CSV: one `ExportTable` (`apps/web/lib/table/export.ts`) that both
  write, so the files hold the same rows and columns (a VLAN ID stays a
  number in Excel). The header row is bold and frozen, and each column is
  as wide as its longest value, at most 50 characters, as the original's
  export. The library is **write-excel-file 4.1.1** (MIT, one dependency:
  fflate 0.8.3, MIT), pinned exactly (ADR-0003), and loaded only when Excel
  is pressed (its own chunk of the web's bundle). Text is always written as
  text, never as a formula. Building the web image from source needs both
  packages in the npm mirror.
  - **Rejected: proxying segments-manager's `GET
    /api/export/segments/excel` through day1.** It would match the
    original's file byte for byte, but it applies only `status` and
    `site`. It would export rows the page does not show (the search, the
    column filters and the holder are ignored), in other columns (it adds
    Allocated At, writes DHCP as Yes/No and an Available holder as
    "Available") and not the shown order, beside a CSV that is exactly
    what is shown. It would also need a binary read on the `SegmentLedger`
    port, its fake and a route. (The original's page shows only a CSV
    button: its `exportData('excel')` has no button.)
  - **Rejected libraries:** SheetJS's npm package (`xlsx`) is frozen at
    0.18.5 (2022) with known advisories; its fixed versions are published
    only on its own CDN, outside the npm registry and so outside the
    air-gapped mirror. ExcelJS (4.4.0, 2023) brings nine dependencies and
    21 MB for a one-sheet file.
- **The connection dot** beside "Updated … · every 30 s": green while
  segments-manager answered the last refresh, red with the reason in its
  tooltip when it did not. The last refresh is the 30-second re-read or
  the Refresh button, whichever ended last (`lib/segments/connection.ts`).
  The page keeps the last good rows (TanStack Query keeps them beside the
  error) and the failed re-read's problem above them. The original tracks
  this state silently, pauses its re-reads while offline, and asks
  `/api/health` every 10 seconds to find out. Wingman shows it, adds no
  call, and keeps re-reading, so the next good read turns it green.
- **Rejected: TanStack Table's own column filtering** (`getFilteredRowModel`
  and faceted values). Its faceted values come from the rows the other
  columns' filters keep, not the original's base rows. And the page's
  counts and exports would read the table's model instead of the pure
  functions the page already filters with.

Verification: `apps/web/lib/table/column-filters.test.ts`,
`apps/web/lib/table/export.test.ts`,
`apps/web/lib/segments/{view,filter,csv,connection}.test.ts` (Vitest),
`apps/web/e2e/tests/segments-columns.spec.ts` (it reads the downloaded
`.xlsx` back and compares it with the CSV), and the dot's tests in
`apps/web/e2e/tests/segments.spec.ts`.

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
