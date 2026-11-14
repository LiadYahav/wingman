# ADR-0048: The Server Scan area is server-scan's UI rebuilt in Wingman page by page, on the one server-scan client, starting with Sites

Date: 2026-11-13
Status: Accepted

## Context

The single-pane plan (`docs/ideas/single-pane.md`, workstream 4) moves
server-scan's UI into Wingman. Decision 22 (option C, 2026-11-13): server-scan
and segments-manager are fully integrated, every feature of their UIs and
their look, each a platform in the top bar with its own sidebar and brand;
their APIs stay as they are (decision 10). Decision 13 keeps the area for
Wingman's admins until RBAC; decision 18 lets Wingman reuse server-scan's
code, which is public.

server-scan's UI is about 9,700 lines over eight pages (Sites, Servers,
Confs, Events, Jobs, Rules & Policies, Claude, Architecture, plus a server's
own page). The user asked for it **page over page, not all together**.

Wingman already reads server-scan through one port, adapter, cache and fake
(`ServerInventory`, ADR-0038): the fleet rows, cached with their `ETag`, and
one server, for the Nodes tab, MCE placement (ADR-0050) and Inventory
Management (ADR-0057), with a viewer token from a Secret. The Segments area
(ADR-0047 and its amendment) built the groundwork an area needs: the top
bar's switch, each area's brand and data-driven sidebar, the shared table,
Vitest.

server-scan's Sites page reads `GET /api/v1/sites`: per configured site and
for the whole fleet, the servers by vendor, health, maintenance,
installation type and OpenShift state, with the site catalog's display names.

## Decision

- **A platform in the top bar, "Server Scan", at `/server-scan`**, for admins
  with server-scan configured. Its brand is server-scan's own mark (its app
  icon, a rack of three units with status lights) and "Server Scan". Its
  sidebar lists server-scan's pages in server-scan's order, **only the pages
  Wingman has built**, so no entry leads nowhere; a page is one entry in
  `apps/web/lib/server-scan/sidebar.ts`.
- **Page by page, one PR each**, in single-pane §4's order: Sites (this one),
  Servers, Server detail, Confs, Rules & Policies, Events, Jobs, Architecture,
  Claude. Each brings its section of the contract note
  (`docs/notes/2026-11-13-server-scan-area-api.md`), its day1 routes, its
  fake, its reused pure TypeScript with Vitest, and its mocked Playwright
  spec.
- **One server-scan client.** Every page's read extends the `ServerInventory`
  port, `HttpServerInventory`, `CachedServerInventory` and
  `FakeServerInventory` (ADR-0001); there is no second adapter, and what the
  Nodes tab, placement and Inventory read does not change. The port moves to
  `wingman_day1/ports/server_scan.py`: `ports.py` became the package
  `ports/` (re-exporting every port), since it was at ADR-0056's 500 lines.
- **day1 routes under `/api/day1/server-scan/`**, `AdminUser`, `501
  FEATURE_DISABLED` while `SERVER_SCAN_URL` is empty, `502
  DEPENDENCY_UNAVAILABLE` when server-scan fails or refuses the token. They
  answer **in server-scan's own shapes**, typed by day1, so server-scan's
  TypeScript types and pure functions apply as they are.
- **Sites reads server-scan's `GET /api/v1/sites`**, cached 10 seconds per
  replica (operation `list_sites`), not the cached fleet rows: the rows lack
  the site catalog (names, order, the sites with no server). The fake counts
  its rows with server-scan's rules, ported, over a catalog in its fixture.
- **The Sites counts are not links until the Servers page exists.** Each card
  and count carries the filter it will open, in server-scan's parameter
  names, so the Servers PR makes them links in one place.
- **Fresh as the original**: Sites is read on open and again when opened after
  30 seconds; it is not polled (server-scan's Servers page is, and Wingman's
  will be).
- **Tokens**: the viewer token Wingman holds (`SERVER_SCAN_TOKEN`) is all
  Sites needs. The auditor token (History, Events) and the admin token (Jobs,
  the writes, behind the admin check and Wingman's audit) come, each as its
  own Secret key, with the pages that need them.
- **Reuse** (decision 18): server-scan's types, card model, vendor labels and
  severity glyphs, and its Sites page tests' cases, credited in the code.

## Alternatives rejected

- **Every page in one PR.** The user asked for page over page; a 9,700-line
  UI in one review hides mistakes, and each page can ship and be looked at.
- **Sites computed from the cached fleet rows.** No new call, but the site
  catalog is not in the rows: the cards would lose the display names and
  server-scan's order, and a configured site with no server would vanish.
- **Counts linking to server-scan's own UI meanwhile.** They would send
  admins out of Wingman to a second login (server-scan's LDAP session in
  production), and every link would change in the next PR. Linking to
  Wingman's future Servers URL would lead to a missing page until then.
- **server-scan's header logo.** It is the team's Red Bull logo, a
  third-party trademark taken from an icon site, not server-scan's mark.
- **A second server-scan port or adapter for the area.** Two clients would
  disagree on caching, tokens and errors; ADR-0001 wants one.
- **A route that only says whether the area is on.** The switch reads the
  Sites route itself (cached), as Segments does, so "on" and "the page works"
  are one answer.
- **Polling Sites every 30 seconds.** The original does not, and the counts
  change with server-scan's collectors (every few hours) and membership
  jobs (every 5 minutes).

## Consequences

- A deployment with `serverScan.url` set gets the area for its admins on
  upgrade; no new value, Secret or grant. Without it the area stays hidden.
- With the area on, each admin's browser asks day1 for the sites at most once
  per 5 minutes to know the area is on, and every day1 replica asks
  server-scan at most once per 10 seconds, whoever asks.
- Inventory Management stays a Wingman sidebar page; it links into this area
  for a server's record once the Server detail page exists.
- `ServerRow` carries `installation_type` now (the fake counts it); the
  Servers page will carry the rest of the row.

## Verification

- `apps/day1-service/tests/unit/infrastructure/test_server_scan_sites.py`:
  server-scan's answer read and typed, malformed answers, the token, the
  metric, the cache, and the fake's counts against server-scan's rules.
- `apps/day1-service/tests/api/test_server_scan_api.py`: admins only, 501
  when off, 502 when failing or refused, the shape.
- `apps/web/lib/server-scan/*.test.ts` (Vitest): the cards, counts and filters
  (server-scan's test cases), the sidebar.
- `apps/web/e2e/tests/server-scan.spec.ts`: the switch for admins only, the
  brand and sidebar per area, the cards and counts, loading, error and
  not-configured states.

## Amendments

**2026-11-13, 3.23.0: the Servers page, and the area's first write.** The
second page, server-scan's Servers page at `/server-scan/servers`, every
feature and button (decision 14), in Wingman's design. The contract is §8 of
`docs/notes/2026-11-13-server-scan-area-api.md`.

- **The fleet rows from the one cache, with two `304`s.** The page reads
  `GET /api/day1/server-scan/servers`: the rows the Nodes tab, placement and
  Inventory Management already share (cached for `DAY1_CACHE_TTL_SECONDS`
  and revalidated against server-scan's `ETag`), in server-scan's own shape,
  every one of its 22 fields read. day1 answers with its own weak `ETag` and
  `Cache-Control: no-cache`, so a page polling an unchanged fleet every 30
  seconds, as the original does, gets a bodiless `304`. No open page makes
  day1 read server-scan again.
- **Reuse**: server-scan's row type, its pure filtering, search, sort, facet,
  cluster-list and paging functions and their test cases, its export's
  columns; the filters in the URL under server-scan's parameter names, so
  the Sites counts become links with the filters they already carried.
  Wingman's column filter is added to Model, the one column server-scan
  cannot filter.
- **Paged, not virtualised**: 50 rows a page as server-scan, through the
  shared table, so the DOM holds 50 rows of the ~3,100; the filters run in
  memory over the whole fleet. The rows are not persisted in the browser's
  query cache (2 MB, polled).
- **The cluster sidebar (MCEs, hosted clusters, UPI clusters) sits inside the
  page**, as in server-scan: it is this page's filter, with counts that follow
  the other filters; the area's sidebar stays navigation.
- **The first write: a server's maintenance on and off**, as server-scan's UI
  does it (its dialog's reason and words, Start maintenance; ending in one
  click), plus the optional expected end server-scan's API takes and its
  dialog does not ask. Behind Wingman's admin check, through the same port
  and adapter (`ServerInventory.start_maintenance`, `end_maintenance`), never
  retried (ADR-0006): unanswered is `504 AMBIGUOUS_WRITE`. day1 drops its
  cached rows and sites after a write, so the next read shows it.
- **server-scan's admin token** is a second, optional key of the existing
  Secret (`serverScan.tokenSecret.adminKey`, default `admin-token`, read into
  `SERVER_SCAN_ADMIN_TOKEN` by day1 only) and is sent only on the writes.
  Without it the toggle is greyed out with one line saying so, unless
  Wingman holds no token at all: that is a server-scan with auth off (the
  sandbox), where writes need none.
- **The person is recorded by Wingman.** server-scan records the token
  (`api-token-admin`); day1 logs every write with the person's name
  (`server_maintenance_started`, `_ended`, `_unconfirmed`), as node uninstall
  logs its starts. Wingman has no other audit store than Git.

Rejected: **virtualising the table** (one more library and a scroll unlike
the original's pages, for a page of 50); **the cluster sidebar in the area's
sidebar** (navigation and one page's filter state mixed, its counts tied to
filters the other pages do not have); **writing with the viewer token** (a
production server-scan refuses it, and a viewer token able to write is not a
viewer token); **a second client or port for the writes** (ADR-0001: one
server-scan client); **adding the person to the reason sent to server-scan**
(it would change what the operator typed, which server-scan's donor rule
reads).

Verification: `apps/day1-service/tests/unit/infrastructure/test_server_scan_rows.py`
and `test_server_scan_maintenance.py` (every field, the `304`s, the writes:
allowed, refused, unanswered, no token), `apps/day1-service/tests/api/test_server_scan_servers_api.py`,
`tests/repo/test_chart_env_contract.py` (the optional admin key),
`apps/web/lib/server-scan/*.test.ts` (server-scan's cases) and
`apps/web/e2e/tests/server-scan-servers.spec.ts`.

**2026-11-14, 3.25.0: a server's own page, and the auditor token.** The
third page, server-scan's server page at `/server-scan/servers/<id>`, its
five tabs (Overview, Hardware, Network, Connectivity, History) and every
button (decision 14), in Wingman's design. The contract is §9 of
`docs/notes/2026-11-13-server-scan-area-api.md`.

- **One record per server.** This page is the one view of a server in
  Wingman: the Servers table's names, Inventory Management's candidates and
  add-server runs, and a VM's host link to it instead of repeating it (for a
  person who has the area; for anyone else they stay text). The cluster
  page's Nodes tab does not change.
- **Three reads through the one client** (`ServerInventory.record`,
  `vm_host`, `server_events`): server-scan's `GET /api/v1/servers/{id}`,
  `/vm-host` and `/servers/{id}/events`, behind `AdminUser`. **Not cached by
  day1**: server-scan caches the record per revision itself, never caches
  the VM host (the host's health changes without the VM changing), and
  History's pages are cursors. The uninstall's fresh check (`server`) keeps
  reading only what it needs.
- **The record is typed by day1 in server-scan's shape**, as Pydantic models
  in the domain (`domain/server_scan_record.py`, `server_scan_hardware.py`),
  parsed in the adapter and sent by the route as they are: one definition,
  not a parser, a domain type and a response model for each of about 150
  fields. They hold the fields server-scan's UI reads (its
  `ServerDetail` type), each typed, enumerations kept as strings so a value
  server-scan adds later reaches the page; its internals are left out.
  Two additions: `reservation.held`, computed by day1 with the rule
  server-scan uses for its rows (server-scan's detail answer lacks it, so
  its own page never shows an install lock), and the maintenance's dates,
  since Wingman's dialog sets an expected end.
- **server-scan's auditor token** is a third optional key of the same
  Secret (`serverScan.tokenSecret.auditorKey`, default `auditor-token`, read
  into `SERVER_SCAN_AUDITOR_TOKEN` by day1 only), sent only on History's
  read, as the admin token is only on the writes. Without it beside a viewer
  token History says so in one line and its route answers `501`; with no
  token at all (auth off, the sandbox) it reads without one.
- **No new admin write.** server-scan's page has none: it shows maintenance
  read only (its `0bb7dad`), and the API's reclassify, health recalculate
  and reservation writes have no button in its UI.
- **The maintenance block carries the Servers page's toggle**, which
  server-scan's page does not (it keeps one place to switch maintenance
  from). Here it is the same component and the same write, admin token,
  confirmation, log line and metrics as on the Servers page, so there is
  still one flow to audit, and an admin who opened a server to look at it
  acts on it there.
- **History for every admin**, as the area is admins only (server-scan
  hides the tab from viewers). The tab is in the URL (`?tab=`), which
  server-scan's is not.
- **Reuse** (decision 18): server-scan's types, `datetime.ts`, `actor.ts`,
  `gpuModel.ts`, `drives.ts`, `describeEvent.ts`, the fabric grouping, the
  NIC wording, the health breakdown's rules and labels, and their tests'
  cases as Vitest cases.
- **Inventory's runs gain `server_id`**: a run names its server only by
  name, so day1 looks the name up in the rows it already caches (exactly one
  server, ignoring case) for the link; `null` when none or several match, or
  when server-scan could not be read, and the runs are listed either way.

Rejected: **caching the record in day1** (server-scan already caches it per
revision; a second cache only delays a change); **passing server-scan's
JSON through untyped** (a malformed answer would reach the page as blanks,
and ADR-0048 types every answer); **a dataclass, a parser and a response
model per field** (three copies of about 150 fields to keep in step);
**History with the admin token** (it would put a write-capable token on a
read; the admin token stays on the writes); **History from `GET
/api/v1/events?server_id=`** (the server's own route exists; the global one
is the Events page's); **reclassify, recalculate and reservation buttons**
(not in server-scan's UI; the reservation is herzi's and the workflows');
**resolving a run's server in the browser** (it would download the fleet's
2 MB rows on the Inventory page for a link).

Verification: `apps/day1-service/tests/unit/infrastructure/test_server_scan_record.py`
(the record, the VM host and History read and typed, malformed answers, the
tokens, the metrics, the fake), `apps/day1-service/tests/api/test_server_scan_record_api.py`,
`tests/repo/test_chart_env_contract.py` (the optional auditor key),
`apps/web/lib/server-scan/*.test.ts` (server-scan's cases) and
`apps/web/e2e/tests/server-scan-server.spec.ts`.
