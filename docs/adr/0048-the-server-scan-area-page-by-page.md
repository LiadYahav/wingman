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
