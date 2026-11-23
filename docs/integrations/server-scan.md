# server-scan in Wingman

server-scan (team-redbull/server-scan, public) is the platform's inventory of
bare-metal servers. Wingman reads two of its routes for its own pages. This
guide says what Wingman reads, where that code lives, and how to bring
Wingman to a new server-scan release. How server-scan itself works is
[its study](../ecosystem/notes/server-scan.md).

Wingman's own Server Scan area, which rebuilt server-scan's UI page by page,
was removed in 3.52.1
([ADR-0066](../adr/0066-segments-manager-and-server-scan-stay-apart.md), superseding
[ADR-0048](../adr/0048-the-server-scan-area-page-by-page.md)): the team keeps server-scan apart, and people use its own UI,
linked from an admin's top bar (`GET /api/day1/platforms`).

## What Wingman reads, and what it never does

- **The fleet rows**, `GET /api/v1/servers/rows`, with the viewer token. day1
  caches them for a few seconds and sends their weak `ETag` back as
  `If-None-Match`, so an unchanged fleet costs a `304`. They feed the
  cluster's Nodes tab (ADR-0038), MCE placement's spare servers (ADR-0050)
  and Inventory Management's pools (ADR-0057).
- **One server**, `GET /api/v1/servers/{id}`, read fresh, never cached: the
  node uninstall's check (ADR-0038).
- **Links, not calls**: a node's server link opens server-scan's own server
  page, built by day1 from `SERVER_SCAN_UI_URL`.
- **Never**: a write of any kind, `/servers/available` and reservations (the
  workflows' and herzi's calls), server-scan's login and personal tokens, and
  the browser calling server-scan (day1 reads it).
- **Token**: the viewer token only (`SERVER_SCAN_TOKEN`), or none for an
  instance that runs with auth off (the root README's Environment Variables).

## The version Wingman matches

[server-scan.yaml](server-scan.yaml) holds it: `synced_at: v6.6.0`
(`635e08a`), set in 3.48.0 (ADR-0048's 2026-11-18 amendment). day1 reads
only the row fields Wingman's features use (its identity, state, health,
site, cluster and MCE, maintenance, reservation, claims and MACs); a field
server-scan adds is ignored until a feature needs it.

## Where its code lives

| What | Where |
|---|---|
| day1's package | `apps/day1-service/src/wingman_day1/integrations/server_scan/`: `ports.py` (`ServerInventory`), `infrastructure/` (`adapter.py`, `parse.py`, `cached.py`, `fakes/inventory.py`), `compose.py` |
| The domain types | `apps/day1-service/src/wingman_day1/domain/servers.py` (`ServerRow`, `ServerDetail`) |
| day1's tests | `apps/day1-service/tests/integrations/server_scan/unit/infrastructure/` (`test_server_scan.py`, `test_server_scan_rows.py`) |
| The fake fleet | `dev/fleet-fixtures/servers.yaml`, in server-scan's row shape, with `DAY1_FAKE_FLEET` |
| The web | `apps/web/components/clusters/node-server-link.tsx` (the link to server-scan's server page) |

Every file that follows a server-scan file is a `files` entry of the map and
ends its header with "What it follows upstream, and at which version:
docs/integrations/server-scan.yaml";
`tests/repo/test_integrations_map.py` fails when the two disagree.

## Syncing with a new server-scan release

1. **Run the script**:
   `uv run python scripts/upstream_diff.py server-scan` (to the newest tag) or
   `... server-scan v6.7.0 --patch`. List 1 is the work; list 2 is what to
   decide (map it, or add it to `not_followed` with why); list 3 is a moved or
   deleted upstream file, so fix the map.
2. **Domain and parsing**: `domain/servers.py` and `infrastructure/parse.py`
   for a new or changed field or value. A field an older server-scan does not
   send gets a default, so both still read.
3. **The fake and its fixture**: `fakes/inventory.py` and
   `dev/fleet-fixtures/servers.yaml` keep server-scan's shape.
4. **Tests**: day1's two test files above.
5. **Bump `synced_at`** in the map, in the same PR, with an ADR-0038 note if
   what Wingman reads changes.
6. **An upgrade-guide row** in `docs/upgrade/` only if operators must act; a
   server-scan that is only newer needs none.

A new server-scan read or token is a decision of its own, not part of a sync.

The checks of 2026-11-17 and 2026-11-18 (v5.3.0 to v6.6.0) covered the
removed area; git has them.

## Known gaps

- **None found at v6.6.0** (checked 2026-11-18).
