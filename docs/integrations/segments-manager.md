# segments-manager in Wingman

segments-manager (team-redbull/segments-manager, public) is the platform's
ledger of VLAN segments per site: which segment exists, and which cluster
holds it as what type. Wingman reads it and rebuilds its one page as the
**Segments** area. This guide says what Wingman mirrors, where that code
lives, and how to bring Wingman to a newer segments-manager. The decisions are
[ADR-0047](../adr/0047-segments-area-native-read-only.md) and, for a
cluster's network check, ADR-0039; the contract day1 answers the web is
[the area's API note](../notes/2026-11-13-segments-area-api.md); how
segments-manager itself works is [its study](../ecosystem/notes/segments-manager.md).

## What Wingman mirrors, and what it never does

- **The area**, for admins (ADR-0047): the per-site cards, then every segment
  in one table with the original's columns and words, its status tabs, search,
  a filter on every column, sort, the CSV and Excel exports of the rows shown,
  Refresh and the connection dot. Each row also says where segments-manager
  disagrees with a cluster file (ADR-0039's checks, from the segment's side).
- **A cluster's EPG** on the cluster page, checked against its file
  (ADR-0039), and links to segments-manager's UI and search for everyone else.
- **Read only, its open GETs**: `/api/sites`, `/api/stats`, `/api/segments`
  (with `fresh=true` for Refresh, at most once per cool-down) and
  `/api/segments/by-segment`. None needs a token.
- **Never**: a write (allocation and release are the allocate-segment workflow's
  and its release's), the raw application log (`/api/logs`), its server-side
  exports (Wingman writes the files in the browser, from the rows shown), and
  the browser calling segments-manager (day1 reads it).

## The commit Wingman matches

[segments-manager.yaml](segments-manager.yaml) holds it: `synced_at: a4edc12`
(2026-10-11, "UPI segments may be shared by several clusters"). Nothing
recorded it before 2026-11-17; it was found this way:

- `a4edc12` has been `main`'s head since 2026-10-11, and the ecosystem study
  read that commit on 2026-11-07; the Segments area was built after it
  (3.15.0 to 3.21.0, 2026-11-13), so it can only have followed this commit.
- Wingman follows `a4edc12`'s own change (a UPI segment's `cluster_name` is a
  list, shown comma-joined) and `32cc7b9`'s (the UPI and HUB types; a site
  card lists only types with an allocation, else "No allocated segments").
- It is the build released as image `v0.1.15`: segments-manager's own tags
  stopped at v1.0.23 (2026-06-10, an ancestor of `a4edc12`), and its releases
  are tagged in team-redbull/redbull-platform (`segments-manager/v0.1.15`,
  three minutes after the commit). So the map's `default_target` is `main`,
  not the newest tag.

## Where its code lives

| What | Where |
|---|---|
| day1's package | `apps/day1-service/src/wingman_day1/integrations/segments_manager/`: `domain/` (the segments typed, the holders, the links), `ports.py`, `application/`, `infrastructure/` (`adapter.py`, `parse.py`, `cached.py`, `fake.py`), `api/`, `compose.py` |
| day1's tests | `apps/day1-service/tests/integrations/segments_manager/` (`api/`, `unit/`) |
| The web | `apps/web/features/segments/` (`api/`, `types/`, `lib/` with its Vitest cases, `components/`); its route, thin, `apps/web/app/(app)/segments/page.tsx` |
| e2e | `apps/web/e2e/fixtures/segments.ts`, `apps/web/e2e/tests/segments.spec.ts` and `segments-columns.spec.ts` |
| The fake ledger | `dev/fleet-fixtures/segments.yaml`, with `DAY1_FAKE_FLEET` |
| In-app docs | `apps/web/app/(app)/docs/segments.tsx` (`/docs#segments`) |

segments-manager publishes no schema for its reads, so day1's parsers are the
contract: they follow its `src/models/schemas.py` and `src/api/routes.py`. The
web follows its page: `static/js/app.js`, `static/html/index.html` and
`static/css/styles.css`. Every file that follows one is a `files` entry of the
map and ends its header with "What it follows upstream, and at which version:
docs/integrations/segments-manager.yaml"; `tests/repo/test_integrations_map.py`
fails when the two disagree.

## Syncing with a newer segments-manager

1. **Run the script**: `uv run python scripts/upstream_diff.py segments-manager`
   (to `main`), or name a commit; `--patch` shows the diffs. List 1 is the
   work, list 2 what to decide (map it, or `not_followed` with why), list 3 a
   moved or deleted upstream file, so fix the map.
2. **Domain and parsing**: `domain/segments.py` and `infrastructure/parse.py`
   for a changed record, a new type or a new filter; the fake for its counts.
   A legacy record that cannot be read stays set aside, never fatal.
3. **day1's schemas and routes**: `api/segments_schemas.py`, the area's note,
   the root README for a new route.
4. **The web's types**: `features/segments/types/segments.ts`.
5. **lib**: the columns, filters, view, site cards, exports and the connection
   state, with their Vitest cases.
6. **components**: the page's parts, in Wingman's design and the original's words.
7. **Fixtures and tests**: day1's tests, `segments.yaml`, the e2e fixtures and specs.
8. **The in-app docs section** (`apps/web/app/(app)/docs/segments.tsx`).
9. **An ADR-0047 amendment** for what changes on the page or in what Wingman reads.
10. **Bump `synced_at`** in the map, in the same PR.
11. **An upgrade-guide row** in `docs/upgrade/` only if operators must act; a
    newer segments-manager alone needs none.

## The check of 2026-11-17

`a4edc12` to `main`: no commit, so nothing is new. `--from f10e0f5` (before
`32cc7b9`) to `main`: 2 commits, 21 of the map's 22 files flagged, and each
change is in Wingman: day1 knows the UPI and HUB types and reads a list of
clusters; the web joins a shared segment's holders with ", " in the table,
the search and the exports, and a site card lists only types with an
allocation. The types' new accent colours (`styles.css`) are not followed:
Wingman shows every type in one outlined style. No watched change is
unmapped. `static/js/app.js` is one file behind most of the web's, so a change
to it flags them all: read its `--patch` to see which part moved.

## Known gaps

- **None found at `a4edc12`** (checked 2026-11-17).
- **Deliberate differences**, not gaps: the filters, view and exports live in
  the URL and the browser (the original keeps them in the page); the Excel file
  holds the rows shown, not the server's export; no segment detail panel and
  no `/api/logs` (ADR-0047); a cluster file whose segment segments-manager
  does not list shows on the cluster page, not in the table.
