# server-scan in Wingman

server-scan (team-redbull/server-scan, public) is the platform's inventory of
bare-metal servers. Wingman reads it and rebuilds its UI as the **Server
Scan** area. This guide says what Wingman mirrors, where that code lives, and
how to bring Wingman to a new server-scan release. The decisions are
[ADR-0048](../adr/0048-the-server-scan-area-page-by-page.md); the contract
day1 answers the web is
[the area's API note](../notes/2026-11-13-server-scan-area-api.md); how
server-scan itself works is [its study](../ecosystem/notes/server-scan.md).

## What Wingman mirrors, and what it never does

- **The area**, for admins (ADR-0048): Sites, Servers, a server's page
  (Overview, Hardware, Network, Connectivity, History), Confs, Events, Jobs,
  Rules & Policies, Claude and Architecture, in server-scan's words, order and
  rules, typed in its shapes. Its sidebar lists only the pages Wingman built.
- **Wingman's own features over its data**: the Nodes tab (ADR-0038), MCE
  placement's spare servers (ADR-0050) and Inventory Management's pools
  (ADR-0057). They read the same port and cache as the area.
- **Three writes, all from the area, with the admin token, never retried**
  (ADR-0006): a server's maintenance on and off, Run job on a CronJob, and
  Fetch now on a server (since v6.6.0: a server's page and every Servers
  row; admins only, as server-scan keeps it).
- **Never**: `/servers/available` and reservations (the workflows' and herzi's
  calls: add-server-to-mce takes a server, not Wingman), reclassify and
  health recalculate (no button in server-scan's own UI calls them; Fetch
  now's refresh is one Wingman follows, since server-scan's buttons call it),
  server-scan's login and personal tokens (Wingman signs people in itself; a
  person makes their token on server-scan's own Claude page).
- **Tokens**: the viewer token for the reads, the auditor token for History and
  Events, the admin token for the writes and Jobs; each page that needs one it
  does not have says so (the root README's Environment Variables).

## The version Wingman matches

[server-scan.yaml](server-scan.yaml) holds it: `synced_at: v6.6.0` (`635e08a`).
The area was matched to v5.3.0 (`92146d3`) page by page, brought to v6.1.0
(`876dd16`) in 3.43.0 (ADR-0048's 2026-11-16 amendment) and to v6.6.0 in
3.45.0 (its 2026-11-18 amendment); the checks below confirmed each.

## Where its code lives

| What | Where |
|---|---|
| day1's package | `apps/day1-service/src/wingman_day1/integrations/server_scan/`: `domain/` (its answers in its shapes), `ports.py`, `application/`, `infrastructure/` (the adapter, parsers, cache, `fakes/`), `api/` (the area's routes and schemas), `compose.py` |
| day1's tests | `apps/day1-service/tests/integrations/server_scan/` (`api/`, `unit/`) |
| Also in day1 | `wingman_day1/api/conditional.py` (the rows' weak ETag and 304) |
| The web | `apps/web/features/server-scan/` (`api/`, `types/`, `lib/` with its Vitest cases, `components/`); its routes, thin, in `apps/web/app/(app)/server-scan/`; its mark, `apps/web/public/server-scan-icon.svg` |
| e2e | `apps/web/e2e/fixtures/server-scan*.ts` (day1's answers) and `apps/web/e2e/tests/server-scan*.spec.ts` |
| The fake fleet | `dev/fleet-fixtures/` (`servers.yaml`, `server-records.yaml`, `confs.yaml`, `rules.yaml`, `events.yaml`, `skill/`, `architecture-diagram.html`), with `DAY1_FAKE_FLEET` |
| In-app docs | `apps/web/app/(app)/docs/server-scan.tsx` (`/docs#server-scan`) |

Every file that follows a server-scan file is a `files` entry of the map and
ends its header with "What it follows upstream, and at which version:
docs/integrations/server-scan.yaml";
`tests/repo/test_integrations_map.py` fails when the two disagree. A new
ported file gets both; Wingman's own glue (the routes' hooks, the area's
chrome) gets neither.

## Syncing with a new server-scan release

1. **Run the script**:
   `uv run python scripts/upstream_diff.py server-scan` (to the newest tag) or
   `... server-scan v6.2.0 --patch`. List 1 is the work; list 2 is what to
   decide (map it, or add it to `not_followed` with why); list 3 is a moved or
   deleted upstream file, so fix the map.
2. **Domain and parsing**: `domain/` and `infrastructure/parse.py` (or the
   page's reader) for a new or changed field, route or parameter. A field an
   older server-scan does not send gets a default, so both still read.
3. **day1's schemas and routes**: `api/*_schemas.py`; a new route under
   `/api/day1/server-scan/` goes in the area's note and the root README.
4. **The web's types**: `features/server-scan/types/`, as server-scan's
   `frontend/src/types/` and `api/` files.
5. **lib**: the pure rules, with server-scan's new test cases ported into the
   `*.test.ts` beside them.
6. **components**: the page's parts, in Wingman's design and server-scan's words.
7. **Fixtures and tests**: day1's tests, the fake fleet's fixtures, the e2e
   fixtures and specs.
8. **The in-app docs section** (`apps/web/app/(app)/docs/server-scan.tsx`).
9. **An ADR-0048 amendment**: what changed, what Wingman follows and what it
   does not, and how it behaves against an older server-scan.
10. **Bump `synced_at`** in the map, in the same PR.
11. **An upgrade-guide row** in `docs/upgrade/` only if operators must act (a new
    token, Secret key or setting); a server-scan that is only newer needs none.

A new server-scan write or token is a decision of its own (ADR-0048), not part
of a sync.

## The check of 2026-11-17

`--from 92146d3` to `v6.1.0`: 8 commits; 40 of the map's 126 Wingman files
follow a changed file. Each change is in Wingman:

| server-scan | Wingman |
|---|---|
| `8c0771a` (v5.3.1): `unreachable_detail` on `ServerDetail`, the `collection_error` reason, the Overview's cause under Collection | `domain/record.py` reads it (default `null`); `types/server-scan-record.ts`; `lib/overview.ts` ("Collection error"); `overview-tab.tsx` shows the cause; the fake's stub |
| `29682c4` (v5.4.0): `server_serial` and `server_bmc` on every event, `server_name` also matching them, the details JSON, "Name, serial or BMC" | `domain/events.py` and both event routes (left out when not sent); `types/server-scan-events.ts`, `server-scan-record.ts`; `lib/events.ts`'s `detailsJson`; `event-filter-bar.tsx`; the fake's matches |
| `2bb2fb2` (v6.0.0): Healthy leaves out servers in maintenance; its count follows | `lib/rows.ts`'s `matchesHealth` and `dropdownFacetCounts`, with server-scan's two cases in `rows.test.ts` |
| `85a58b4` (v6.0.0): `/servers/available` takes `max_health`, `POST` locks and live-checks; `claim_token` on a reservation | Not followed: Wingman never calls it; day1 ignores the reservation's new field |
| `a2ba3ee` (v6.1.0): the collectors chart | Nothing to follow |

The only unmapped change under `watch` was `HistoryPanel.test.tsx` (new
fields in its fixture); no server-scan page renders `HistoryPanel`. v6.1.0
was also the newest tag and `main`'s head that day: nothing released since.

## The check of 2026-11-18

`v6.1.0` to `v6.6.0`: 14 commits (six that change what the area shows or
calls); 52 of the map's 126 Wingman files followed a changed file. Each change
is in Wingman (ADR-0048's 2026-11-18 amendment):

| server-scan | Wingman |
|---|---|
| `4d9d171` (v6.2.0): the BMC cell's copy button; a stacked health bar per Sites card | `server-columns.tsx` (and the server header's BMC tooltip); `lib/sites.ts`'s `healthSegments`, `site-card.tsx` |
| `0c141c9` (v6.2.1): `npm audit --omit=dev` | Not followed: server-scan's own CI; Wingman's audit is its own (`docs/ops/ci-maintenance.md`) |
| `a0e29c3` (v6.3.0): `server_type` (physical or vm), the Type filter, Physical, VM and vendor bars on the Sites cards; a ticked severity leaves out servers in maintenance, and `by_health` counts servers in service only | day1 reads `server_type` (its rule over the vendor for an older server-scan), the fake counts maintenance apart; `types/`, `lib/rows.ts`, `lib/servers-view.ts`, `servers-toolbar.tsx`, `lib/sites.ts`'s `countBars` and `cardVerdict`, the server header; the Overview's health bar gains a maintenance part |
| `f80ffb9` (v6.4.0): the Servers table scrolls inside its own box | `lib/fill.ts`, `use-fill-main.ts` (over the shell's `main`), `servers-page.tsx`, `cluster-sidebar.tsx` |
| `827cd97` (v6.5.0): `POST /servers/{id}/refresh`, the server page's Fetch now | the port, `writes.py`, `fakes/refresh.py`, `POST /api/day1/server-scan/servers/{id}/refresh` (`AdminUser`), `409 SERVER_REFRESH_REFUSED`, nginx's 130-second location; `fetch-now.tsx`, `lib/refresh.ts`; `SERVER_REFRESHED` in `lib/events.ts` |
| `55b6391` (v6.6.0): Fetch now on every Servers row; Events scrolls inside its own box | `fetch-now.tsx`'s column; `event-timeline.tsx`'s `fill` |

Not followed, under `watch`: `InventoryPage.test.tsx` and
`MaintenanceToggle.test.tsx` (only their fixtures and a cell index changed;
`not_followed` says why). Outside `watch`, not for Wingman: the footer's
spacing (Wingman has none), `.claude/` rules, the backend's
`available_servers.py` refactor and its dev-only `INVENTORY_FAKE_MANAGERS`.
v6.6.0 was also the newest tag and `main`'s head that day.

## Known gaps

- **None found at v6.6.0** (checked 2026-11-18).
- **Behaviour against an older server-scan**: `server_type` is derived from
  the vendor; before v6.3.0 `by_health` also counted servers in maintenance,
  so a card's bars count those servers twice and "all healthy" needs every
  server healthy and none in maintenance; before v6.5.0 Fetch now answers
  `502` (server-scan has no such route), and the buttons stay.
- **Deliberate differences**, not gaps: the writes above; Claude's "Your
  token" (a link to server-scan's own page); the Servers export written with
  Wingman's shared Excel writer instead of server-scan's zip writer (the same
  rows, columns and headers); Wingman's chrome, login and data layer, listed
  under `not_followed` in the map.
