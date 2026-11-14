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
  page's Nodes tab does not change (superseded by the 3.26.0 amendment: it
  links there too).
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
- **Maintenance is read only on the server's page**, as in server-scan
  (its `0bb7dad`: one place to switch it, the Servers list). The block
  shows the state and reason, and a "Switch on Servers" link opens the
  list at this server (decision 14: exactly server-scan's buttons).
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

**2026-11-14, 3.26.0: the Nodes tab links admins to a server's page.** A
server's name on the cluster page's Nodes tab, and a node in the Overview's
opened nodepool, opens the server's page here (`/server-scan/servers/<id>`)
for a person who has the Server Scan area (an admin, with server-scan
configured), in the same tab as any link inside Wingman and without the
external-link mark: one view per server. Anyone else keeps the link to
server-scan's own page (`url`, built by day1), in a new tab, until RBAC
opens the area to them. Nothing else on the cluster page changes.

- **No API change.** The nodes read already carries server-scan's id
  (`server.id`, the uninstall's key), the id the server page reads by, so
  the web builds the link; `url` stays as it is.
- **One decision**: `nodeServerLink` (`apps/web/lib/server-scan/server-page.ts`)
  returns the address, whether it stays in Wingman and the accessible name
  ("<name>, its server page", or "<name>, its server-scan page (opens in a
  new tab)"), and both views link through it. The Overview's rows used to
  say "<name>: open in server-scan (new tab)"; they now say what the Nodes
  tab says.

Rejected: **the Nodes tab's own server details** (a second view of a server
to keep in step with the page); **server-scan's page for everyone** (an
admin would leave Wingman for a record Wingman already shows); **Wingman's
page for viewers** (the area is admins only: the page would answer `403`).

Verification: `apps/web/lib/server-scan/server-page.test.ts` and
`apps/web/e2e/tests/cluster-nodes.spec.ts` (an admin with the area, a viewer).

**2026-11-14, 3.27.0: the Claude page.** server-scan's Claude page at
`/server-scan/claude`: its guide to the `server-scan-api` Claude Code skill,
the download, the four setup steps, the MCP command and the skill's files,
in Wingman's design and server-scan's words. The contract is §12 of
`docs/notes/2026-11-13-server-scan-area-api.md`.

- **The skill is read from server-scan, never copied.** server-scan serves
  it from its API, read from its disk on every call (its ADR-0052, so the
  page follows every edit): day1 reads `GET /api/v1/skill` through the one
  client (`ServerInventory.skill`, typed in server-scan's shape, cached 60
  seconds per replica, the original page's refresh) and passes on the zip
  server-scan builds (`ServerInventory.skill_zip`, `GET
  /api/v1/skill/download`, never cached). Both with the viewer token: no new
  Secret, key or value.
- **The zip and the commands name server-scan, not Wingman.** Claude Code
  calls server-scan's API with the person's own token, so the address
  written into the zip, the MCP command's and the token link's is
  server-scan's for people (`SERVER_SCAN_UI_URL`, else `SERVER_SCAN_URL`,
  the node links' rule), sent by day1 as `server_scan_url`. server-scan's
  page uses its own origin.
- **The token placeholder is server-scan's rule**: server-scan writes
  `VIEWER_TOKEN` into a viewer caller's copy, `AUDITOR_TOKEN` into anyone
  else's. The caller is Wingman, so day1 says which (`token_line`):
  `VIEWER_TOKEN` with its viewer token, `AUDITOR_TOKEN` with none (auth off).
- **The personal token is a link out**, the one place parity is impossible
  (single-pane §4): server-scan makes, replaces and revokes it only for a
  person signed in to server-scan, never for a service token. Step 3 and the
  MCP section link to server-scan's own Claude page in a new tab and say so
  in one line; Wingman has no token section and never sees a token.
- **No write.** The page reads the skill and downloads the zip; nothing
  changes on server-scan.
- **Reuse** (decision 18): server-scan's `skillText.ts` (`extractPrompts`,
  `outline`), the tools' split, its types and its tests' cases; the fake
  reads and zips a stand-in skill (`dev/fleet-fixtures/skill/`) with
  server-scan's `skill_bundle.py` rules, ported.

Rejected: **copying the skill into Wingman** (stale on server-scan's first
edit: its ADR-0052's reason); **a link out for the whole page** (the
download, the commands and the files need no server-scan login, and
leaving Wingman for them is the second login ADR-0048 avoids); **minting a
token through Wingman** (server-scan makes personal tokens only for its own
sessions, and a token made with Wingman's service token would be
Wingman's, recorded as Wingman, not the person); **building the zip in
day1** from the skill's files (a second copy of server-scan's packing rules,
the `BASE_URL` line and the viewer rename, to keep in step);
**`window.location.origin` as the address** (Wingman's, which Claude Code
must not call).

Verification: `apps/day1-service/tests/unit/infrastructure/test_server_scan_skill.py`
(the skill and the zip read and typed, malformed answers, no skill, the
token, the refused address, the metrics, the cache, the fake, the token
line), `apps/day1-service/tests/api/test_server_scan_skill_api.py`,
`apps/web/lib/server-scan/skill-text.test.ts` (server-scan's cases, the
commands), `apps/web/lib/server-scan/sidebar.test.ts` and
`apps/web/e2e/tests/server-scan-claude.spec.ts`.

**2026-11-14, 3.28.0: the Architecture page, server-scan's diagrams through
day1 in a sandboxed frame.** server-scan's Architecture page at
`/server-scan/architecture`, its tabs, words and descriptions, the diagram
in the URL (`?diagram=`), in Wingman's design. The contract is §11 of
`docs/notes/2026-11-13-server-scan-area-api.md`.

server-scan's diagrams are archify's self-contained pages (about 0.7 MB
each: inline SVG and the viewer's scripts for pan, zoom, search and its
toolbar), served by its UI's nginx as static files
(`<ui>/architecture/<slug>.html`), without login or framing headers. Its API
does not have them; their JSON sources are not served; the list of
diagrams is compiled into its frontend. The single-pane plan said to frame
them, so they never go stale.

- **day1 reads each diagram from server-scan's UI**, through the one client
  (`ServerInventory.architecture_diagram`, operation
  `get_architecture_diagram`), at `SERVER_SCAN_UI_URL` (else
  `SERVER_SCAN_URL`, as node links), **with no token**: the files need none.
  It takes the page only if archify made it, since server-scan's nginx answers
  a missing file with its app and a `200`. Cached five minutes per diagram:
  they change only with server-scan's releases.
- **The web shows the page in a sandboxed frame**: `srcdoc`,
  `sandbox="allow-scripts allow-downloads"`, no `allow-same-origin`, so the
  diagram's scripts run in an origin of their own and reach nothing of
  Wingman's. The page is server-scan's, unchanged but for one script first
  in its head that answers `prefers-color-scheme` with Wingman's theme
  (server-scan passes `?theme=`; a `srcdoc` has no address).
- **The list of diagrams is server-scan's, reused** (decision 18): seven
  slugs, labels and descriptions in `apps/web/lib/server-scan/diagrams.ts`.
  The diagrams are never copied; only their names are. A diagram server-scan
  adds is one entry; one it drops answers `404` and its tab says so.
- **No new setting, Secret, token or write.** A deployment whose
  `SERVER_SCAN_URL` is server-scan's in-cluster API needs `serverScan.uiUrl`
  to be its UI (node links already need it), reachable and trusted from
  day1.
- **The sidebar** gains Architecture in the "Reference" section, after
  Claude and last, as in server-scan's navigation.

Rejected: **the browser framing server-scan's UI directly** (the plan's
first idea): the single pane's rule is that the browser never calls
server-scan; a cross-origin frame cannot report a failure, so a missing
diagram would show server-scan's own app in the frame (its fallback) and an
outage the browser's error page; a framing header server-scan adds later
would blank the page silently; and there would be no fake, metric or
problem. **Rendering the diagrams in Wingman**, as the plan prefers for
text diagrams such as Mermaid: their sources are archify's JSON, which
server-scan does not serve, and archify is not a library to load. **Copying
the pages into Wingman**: they would go stale with server-scan's next
release (the plan's reason to frame them). **A link out to server-scan's
page**: it leaves Wingman for a second login (why this ADR kept the Sites
counts from linking out). **The frame with `allow-same-origin`**: server-scan's
scripts would run as Wingman, with its session and storage. **Reading the
list of diagrams from server-scan's bundle**: a build artefact's internals,
not an interface.

Verification: `apps/day1-service/tests/unit/infrastructure/test_server_scan_architecture.py`
(read from the UI without a token, a missing diagram and the SPA's
fallback, failures, the size cap, the metric, the cache, the fake),
`apps/day1-service/tests/api/test_server_scan_architecture_api.py`,
`apps/web/lib/server-scan/diagrams.test.ts` (server-scan's cases, the theme
script) and `apps/web/e2e/tests/server-scan-architecture.spec.ts` (the
sandbox, the picker and the URL, the theme, the states).

**2026-11-14, 3.29.0: the Confs page, server-scan's hardware catalog.**
server-scan's Confs page at `/server-scan/confs`, every feature of it
(decision 14), in Wingman's design, in the sidebar's Fleet section after
Servers. The contract is §10 of
`docs/notes/2026-11-13-server-scan-area-api.md`.

- **One read through the one client** (`ServerInventory.confs`): server-scan's
  `GET /api/v1/confs` with the viewer token, behind `AdminUser`, operation
  `list_confs`. No new Secret, value or key.
- **Typed by day1 in server-scan's shape** (`domain/server_scan_confs.py`):
  every field of its `Conf`, which is the collection writer's shape, with
  its defaults; its `unreadable` ids passed on, so the page names the stored
  confs server-scan skipped.
- **Not cached by day1**: server-scan reads its small collection on every
  call and caches nothing itself, and only this page asks, at most once per
  30 seconds per open page. A cache would only delay a change the
  collection's writer makes.
- **Read only**, as server-scan's page is: its only controls are the search
  and a row's ▸, and server-scan has no write for confs (another system
  writes the collection).
- **Fresh as the original**: read on open, again when opened after 30
  seconds; not polled.
- **The fake** serves server-scan's own fake catalog
  (`providers/fake/confs.py`), transcribed into
  `dev/fleet-fixtures/confs.yaml` in the answer's shape, plus one unreadable
  id to show the notice.
- **Reuse** (decision 18): server-scan's `Conf` type, `format.ts` with its
  search, the page's words, and its tests' cases as Vitest cases.

Rejected: **caching the confs in day1** (nothing to save, a change shows
later); **`GET /api/v1/confs/{conf_id}` for an opened row** (the list already
carries every field, and server-scan's page does not call it); **linking a
conf to the servers built to it** (server-scan does not, and nothing in a
server's record names its conf).

Verification: `apps/day1-service/tests/unit/infrastructure/test_server_scan_confs.py`
(the read, the shape field for field, the defaults, malformed answers, the
token, the metric, the fake), `test_server_scan.py` (read through the cache),
`apps/day1-service/tests/api/test_server_scan_confs_api.py`,
`apps/web/lib/server-scan/confs.test.ts` (server-scan's cases) and
`apps/web/e2e/tests/server-scan-confs.spec.ts`.

**2026-11-14, 3.30.0: the Rules & Policies page, what server-scan runs.**
server-scan's Rules & Policies page at `/server-scan/rules`, every feature of
it (decision 14), in Wingman's design: the classification rules that give a
server its installation type, and the health policies that judge its health,
grouped and ordered as server-scan does, in a Configuration section of the
sidebar between Fleet and Reference. The contract is §13 of
`docs/notes/2026-11-13-server-scan-area-api.md`.

- **Two reads through the one client** (`ServerInventory.classification_rules`,
  `health_policies`): server-scan's `GET /api/v1/classification-rules` and
  `/health-policies`, the enabled ones only (`?enabled=true`, as its page
  asks), with the viewer token, behind `AdminUser`, operations
  `list_classification_rules` and `list_health_policies`. Two routes, not
  one, so each section loads and fails on its own, as in server-scan. No new
  Secret, value or key.
- **Typed by day1 in server-scan's shapes** (`domain/server_scan_rules.py`):
  every field, with its domain models' defaults; a policy's condition tree
  typed node by node (`not` keeps its name), its values any JSON; server-scan's
  words stay strings.
- **Not cached by day1**: two small reads server-scan answers from its
  database, asked for by this page only, at most once per 30 seconds per
  open page; after a server-scan upgrade re-seeds them, the page shows the
  new set at once.
- **Read only, and nothing left out**: server-scan's page has no control at
  all, and its API has no write for rules or policies (its `27b20a8`,
  `f9ab059`: they ship in code and are seeded at start-up).
- **Fresh as the original**: read on open, again when opened after 30
  seconds; not polled.
- **The fake** serves the three classification rules the fake servers'
  records name (one source for "Matched rule" on a server's page and this
  page, held together by a test) and server-scan's own 20 seeded health
  policies, transcribed into `dev/fleet-fixtures/rules.yaml`.
- **Reuse** (decision 18): server-scan's rule and policy types, the
  condition guards, `MANAGER_TYPE_LABELS`, `RulesPage.tsx`'s scope, section,
  severity and condition functions, its words, and its tests' cases as
  Vitest cases.

Rejected: **one route for both** (one failing would blank the other, which
server-scan's page keeps apart); **an `enabled` parameter** (the page lists
what the deployment does; a disabled rule is not that, and server-scan's
page never asks for one); **checking a condition's grammar in day1**
(server-scan validates it against its metric registry when it seeds it; day1
types it and shows it); **the metric registry** (`/api/v1/health-metrics`:
the page does not read it); **caching** (nothing to save, an upgrade shows
later).

Verification: `apps/day1-service/tests/unit/infrastructure/test_server_scan_rules.py`
(both reads, enabled only, the shapes field for field, the defaults,
malformed answers, the token, the metrics, the fake and its agreement with
the records fixture), `test_server_scan.py` (read through the cache),
`apps/day1-service/tests/api/test_server_scan_rules_api.py`,
`apps/web/lib/server-scan/rules.test.ts` (server-scan's cases) and
`apps/web/e2e/tests/server-scan-rules.spec.ts`.

**2026-11-14, 3.31.0: the Events page, the fleet's audit trail.**
server-scan's Events page at `/server-scan/events`, every feature of it
(decision 14), in Wingman's design, in an Activity section of the sidebar
between Fleet and Configuration. The contract is §14 of
`docs/notes/2026-11-13-server-scan-area-api.md`.

- **Two reads through the one client** (`ServerInventory.events`,
  `event_actors`): server-scan's `GET /api/v1/events` with its filters and
  keyset cursor (`server_id`, `event_type`, `actor_id`, `since`, `until`,
  `server_name`, `cursor`, `page_size`) and `GET /api/v1/events/actors`,
  behind `AdminUser`, operations `list_events` and `list_event_actors`. day1
  checks each parameter (lengths, server-scan's event-type form, a date with
  its zone, the page size) and passes on those given; a cursor server-scan
  refuses is a `422`. The answer is History's page, the same model.
- **History's auditor token and guard, extended, not copied.** The same
  `SERVER_SCAN_AUDITOR_TOKEN`, sent on History and these two reads only; the
  same rule for when the audit trail works (the auditor token, or no token at
  all: auth off); the same use-case guard and `501 FEATURE_DISABLED`, now
  `ServerScanAuditOffError` for both pages, each with its own line. The
  `501` carries `details.setting: "SERVER_SCAN_AUDITOR_TOKEN"`, so a page
  tells a missing auditor token from server-scan not being configured. No
  new Secret, value or key.
- **Not cached by day1**: cursors and filters, read when a page is shown;
  the actors at most once a minute per open page, as the original's list.
- **Read only**, as server-scan's audit trail is: append-only, with no write
  in its API but its retention job's.
- **One audit trail in the fake.** The fleet's trail is every fake server's
  History plus `dev/fleet-fixtures/events.yaml` (people's and the platform's
  events, herzi's install lock, a pruned server), filtered and paged as
  server-scan does; a server's History is the same trail by its id, so both
  pages agree.
- **The web shares History's timeline, details and pager**, moved to
  `components/server-scan/events/` with a Server column whose name links to
  the server's page here. The User filter is Wingman's searchable dropdown
  over server-scan's actor list (label and count, narrowed by label or id).
- **Fresh as the original**: read on open, again when opened after 30
  seconds; the User list once a minute; not polled.
- **Reuse** (decision 18): server-scan's `filters.ts`, `parseIsraelInput`,
  `ActorCombobox.tsx`'s choices, `EventTimeline.tsx`'s Server cell, its
  words, and its tests' cases as Vitest cases; `describeEvent.ts`,
  `actor.ts` and `datetime.ts` were ported with History.

Rejected: **the list with the viewer token** (server-scan keeps its audit
trail from viewers: `require_audit_access`); **the admin token** (a
write-capable token on a read); **a separate "off" signal for Events**, such
as a status route or a field on the sites (the `501`'s `details.setting` is
the answer itself, as `history_available` is the record's); **caching the
list** (cursors over a trail that grows; a page would show old events);
**History from the fleet route with `server_id`** (kept from 3.25.0: the
server's own route exists); **server-scan's `AuditGate`** (the area is for
Wingman's admins, who may all read the trail; RBAC decides the rest);
**a text box that narrows a list as you type, as server-scan's User
filter** (Wingman's searchable dropdown does the same in Wingman's look).

Verification: `apps/day1-service/tests/unit/infrastructure/test_server_scan_events.py`
(both reads, the parameters sent, the auditor token only, a refused cursor
and token, malformed answers, the metrics, the cache, the fake's filters,
cursors and actors, the guard), `apps/day1-service/tests/api/test_server_scan_events_api.py`,
`apps/web/lib/server-scan/event-filters.test.ts` and `datetime.test.ts`
(server-scan's cases), `sidebar.test.ts` and
`apps/web/e2e/tests/server-scan-events.spec.ts`.

**2026-11-14, 3.32.0: the Jobs page, and the area's second write.**
server-scan's Jobs page at `/server-scan/jobs`, every feature and button
(decision 14), in Wingman's design, in the sidebar's Activity section
after Events. The contract is §15 of
`docs/notes/2026-11-13-server-scan-area-api.md`.

- **Three calls through the one client** (`ServerInventory.jobs`,
  `job_logs`, `run_job`): server-scan's `GET /api/v1/jobs` (the triggerable
  CronJobs, their recent Jobs and pods), a pod's log, and `POST
  /api/v1/jobs/{cronjob}/run`, behind `AdminUser`, operations `list_jobs`,
  `get_job_logs` and `run_job`. Typed by day1 in server-scan's shape
  (`domain/server_scan_jobs.py`); `enabled: false` passes through, so the
  page says the deployment has the feature off.
- **The admin token on the reads too.** server-scan serves the whole
  `/api/v1/jobs` router to its admin role only (logs and Job names are
  operational detail, its ADR-0055), so day1 reads it with the same optional
  admin key the maintenance toggle uses, decided by the same helper: the
  admin token when set, none when Wingman holds no token (auth off, the
  sandbox), and off with a viewer token alone: every Jobs route answers
  `501` with the line naming the key, and the page shows "Jobs is not set
  up" with it. No new Secret, value or key.
- **Not cached by day1**: the page polls every 5 seconds while a Job runs,
  as server-scan's does, and a cached list would hide the run it started.
- **Run now, as server-scan's UI does it**: its confirmation's words and the
  CronJob's warning (the chart's annotation), a real Job from the CronJob's
  template. server-scan refuses a start while a run is unfinished (`409`,
  `JOB_ALREADY_RUNNING`, its words) and has no idempotency key, so a second
  send after the first finished is a second run: never retried (ADR-0006),
  the submit disabled while sending, `504 AMBIGUOUS_WRITE` when unanswered,
  after which the page says to look at the runs before starting it again.
- **The person is recorded by Wingman**: the Job and server-scan's audit
  trail name Wingman's admin token; day1 logs each start with the person
  (`server_scan_job_started`, `_unconfirmed`), through the same recording
  maintenance uses.
- **Reuse** (decision 18): server-scan's types, the page's pure decisions
  and words, and its tests' cases as Vitest cases; its fake runner, ported,
  with three CronJobs.

Rejected: **the viewer token for the reads** (server-scan answers it `403`:
its router is admin only); **the Jobs routes on without the admin token
behind a viewer token** (every read would be a `502` naming a token that is
not wrong, only missing); **caching the list** (the run just started would
show a poll later, and server-scan reads Kubernetes per call anyway);
**retrying an unanswered start** (a second collector or prune run, which
server-scan only refuses while the first is unfinished); **a person's name
on the Job** (server-scan's run takes no body and writes the caller's actor;
Wingman's log is the record); **the shared table** (a card per CronJob with
a few runs as lines, as server-scan's: nothing to sort, filter or page).

Verification: `apps/day1-service/tests/unit/infrastructure/test_server_scan_jobs.py`
(the reads and the start typed, the admin token, auth off, refused, not
found, conflict, unanswered, sent once, the metrics, the fake),
`apps/day1-service/tests/api/test_server_scan_jobs_api.py` (admins only, the
tokens' table, 501, 502, 409, 404, 504, logged with the person),
`apps/web/lib/server-scan/jobs.test.ts` (server-scan's cases),
`apps/web/lib/server-scan/sidebar.test.ts` and
`apps/web/e2e/tests/server-scan-jobs.spec.ts`.
