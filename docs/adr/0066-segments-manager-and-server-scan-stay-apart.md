# ADR-0066: segments-manager and server-scan stay apart from Wingman: the top bar links to their own UIs, and Wingman rebuilds neither

Date: 2026-11-23
Status: Accepted (supersedes ADR-0047 and ADR-0048)

## Context

Wingman rebuilt two of the team's systems inside itself: the Segments area,
segments-manager's page (ADR-0047), and the Server Scan area, server-scan's
UI page by page, with three writes of its own (maintenance, Run job, Fetch
now; ADR-0048). The team decided that both systems stay apart from Wingman.
3.52.0 put each area behind a setting, off by default
(`DAY1_SEGMENTS_AREA`, `DAY1_SERVER_SCAN_AREA`), and linked the top bar to
each system's own UI instead (both ADRs' first 2026-11-23 amendments).

Code that no deployment runs still has to be read, built, tested and kept in
step with two upstreams: the areas were about 20,000 lines of the web and
14,000 of day1, its tests and fixtures, for pages nobody opens. The user
asked for no leftovers.

## Decision

The two areas are removed. Wingman links to segments-manager and server-scan
and reads only what its own features need.

- **The top bar** keeps its platform switch for admins: Wingman, then
  Segments and Server Scan, each a link to the system's own UI in a new tab
  (`GET /api/day1/platforms`: `{"platforms": [{"id", "name", "url"}]}`, the
  `area` flag gone with the areas). A viewer has no switch and never asks.
- **What day1 still reads**, each through its port, adapter, cache and fake:
  server-scan's fleet rows and one server, with the viewer token (the Nodes
  tab, the uninstall's check, placement, Inventory Management; ADR-0038,
  ADR-0050, ADR-0057), and segments-manager's one segment (a cluster's EPG,
  ADR-0039). The ports have only those methods.
- **Links instead of pages**: a node's server opens its page in server-scan
  (`server.url`, built by day1); the cluster card opens segments-manager's UI
  and names the cluster to search for. Inventory Management names a server as
  text.
- **Gone**: every route under `/api/day1/segments` and `/api/day1/server-scan`
  (a 404 now), their use cases, schemas, adapter methods, fakes and fixtures;
  the settings `DAY1_SEGMENTS_AREA`, `DAY1_SERVER_SCAN_AREA` and
  `DAY1_SERVER_SCAN_REFRESH`; server-scan's admin and auditor tokens
  (`SERVER_SCAN_ADMIN_TOKEN`, `SERVER_SCAN_AUDITOR_TOKEN`), which only the
  area used; the error codes `JOB_ALREADY_RUNNING` and
  `SERVER_REFRESH_REFUSED`; nginx's long location for Fetch now; the
  dependency operations only the areas called (`docs/ops/metrics.md`); the
  web's `features/` folder, the area sidebars, brands and server-scan's mark,
  the Overview's Free Segments and Server Fleet Health cards, and the in-app
  docs sections. Wingman's chrome is its own again; its credits stay on its
  brand, and the areas' own credits went with them.
- **The chart** renders none of the removed settings. Its keys
  (`day1.serverScanRefresh`, `day1.segmentsArea`, `day1.serverScanArea`,
  `serverScan.tokenSecret.adminKey` and `auditorKey`) stay in
  `values.schema.json`, marked deprecated, so a values file that still sets
  them is accepted and ignored (ADR-0059).

## Alternatives rejected

- **Keep the areas behind their settings** (3.52.0): nothing turns them on,
  and every change to the shared code (ServerRow, the caches, the data table)
  still had to carry them.
- **Redirect `/segments` and `/server-scan` to the systems' UIs**: an old
  bookmark is rare, and Wingman would choose for the person where they land;
  the top bar is one click away.
- **Keep server-scan's admin token for a later write**: a write Wingman makes
  to server-scan is a decision of its own (ADR-0048 said so); none is planned.

## Consequences

- An admin and a viewer see what they saw in 3.52.0, where the areas were
  off. Nothing an operator set changes behaviour; the guide is
  `docs/upgrade/3.52-to-3.53.md`.
- To bring an area back, start from git history: the last release that
  shipped both is v3.52.0 (off by default), and ADR-0047 and ADR-0048 say what
  they did. It would be a new decision, with its own ADR.
- `docs/integrations/` keeps the guides and maps for what Wingman still reads
  from each system; the page-by-page parity is gone with the pages.

## Verification

- `apps/day1-service/tests/api/test_platforms_api.py`: the links, admins only,
  no route under `/api/day1/segments` or `/api/day1/server-scan`, the network
  and inventory reads still served.
- `tests/repo/test_chart_env_contract.py` and `tests/repo/test_chart_schema.py`:
  the removed keys render nothing and are accepted as deprecated.
- `apps/web/lib/platforms.test.ts` and `apps/web/e2e/tests/platforms-apart.spec.ts`:
  the top bar's links out, nothing in Wingman leading to an area, a viewer's
  top bar; `cluster-nodes.spec.ts` and `cluster-network.spec.ts` the links to
  each system's own page.
