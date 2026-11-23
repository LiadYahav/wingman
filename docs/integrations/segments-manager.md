# segments-manager in Wingman

segments-manager (team-redbull/segments-manager, public) is the platform's
ledger of VLAN segments per site: which segment exists, and which cluster
holds it as what type. Wingman reads one segment for a cluster's network
check and links to segments-manager's UI. This guide says what Wingman
reads, where that code lives, and how to bring Wingman to a newer
segments-manager. The decision is ADR-0039; how segments-manager itself
works is [its study](../ecosystem/notes/segments-manager.md).

Wingman's own Segments area, which rebuilt segments-manager's page, was
removed after 3.52.0
([ADR-0066](../adr/0066-segments-manager-and-server-scan-stay-apart.md), superseding
[ADR-0047](../adr/0047-segments-area-native-read-only.md)): the team keeps segments-manager apart, and people use its own
UI, linked from an admin's top bar (`GET /api/day1/platforms`).

## What Wingman reads, and what it never does

- **One segment**, `GET /api/segments/by-segment?segment=<cidr>`, open (no
  token), cached per replica: the cluster page's EPG, checked against the
  cluster file (ADR-0039). A `404` is "no such segment".
- **Links, not calls**: the cluster page links to segments-manager's UI and
  to its open `GET /api/segments/search?q=<file stem>` (its UI reads no URL
  parameters, so a link can only name what to search for). Both come from
  `SEGMENTS_MANAGER_UI_URL`, else `SEGMENTS_MANAGER_URL`.
- **Never**: a write (allocation and release are the allocate-segment
  workflow's and its release's), the raw application log (`/api/logs`), its
  exports, and the browser calling segments-manager (day1 reads it).

## The commit Wingman matches

[segments-manager.yaml](segments-manager.yaml) holds it: `synced_at: a4edc12`
(2026-10-11, "UPI segments may be shared by several clusters", so a
segment's `cluster_name` may be a list). It has been `main`'s head since that
day and is the build released as image `v0.1.15`: segments-manager's own tags
stopped at v1.0.23 (2026-06-10, an ancestor of `a4edc12`), and its releases
are tagged in team-redbull/redbull-platform (`segments-manager/v0.1.15`). So
the map's `default_target` is `main`, not the newest tag.

## Where its code lives

| What | Where |
|---|---|
| day1's package | `apps/day1-service/src/wingman_day1/integrations/segments_manager/`: `domain/links.py` (the UI and search links), `ports.py` (`SegmentLedger`), `infrastructure/` (`adapter.py`, `parse.py`, `cached.py`, `fake.py`), `compose.py` |
| The check | `apps/day1-service/src/wingman_day1/domain/network.py` (the file against the segment) |
| day1's tests | `apps/day1-service/tests/integrations/segments_manager/` (`api/test_segments_manager_link_api.py`, `unit/domain/test_segments_manager.py`, `unit/infrastructure/test_segments_manager.py`) |
| The fake ledger | `dev/fleet-fixtures/segments.yaml`, in segments-manager's shape, with `DAY1_FAKE_FLEET` |
| The web | `apps/web/components/clusters/segments-link.tsx` |

segments-manager publishes no schema for its reads, so day1's parser is the
contract: it follows its `src/models/schemas.py` and `src/api/routes.py`.
Every file that follows one is a `files` entry of the map and ends its header
with "What it follows upstream, and at which version:
docs/integrations/segments-manager.yaml";
`tests/repo/test_integrations_map.py` fails when the two disagree.

## Syncing with a newer segments-manager

1. **Run the script**: `uv run python scripts/upstream_diff.py segments-manager`
   (to `main`), or name a commit; `--patch` shows the diffs. List 1 is the
   work, list 2 what to decide (map it, or `not_followed` with why), list 3 a
   moved or deleted upstream file, so fix the map.
2. **Parsing**: `infrastructure/parse.py` for a changed record; `domain/network.py`
   for a changed status or type; `domain/links.py` for a changed search route
   or a UI that starts reading URL parameters.
3. **The fake and its fixture**: `fake.py` and `dev/fleet-fixtures/segments.yaml`
   keep segments-manager's shape.
4. **Tests**: day1's tests above.
5. **Bump `synced_at`** in the map, in the same PR, with an ADR-0039 note if
   what Wingman reads changes.
6. **An upgrade-guide row** in `docs/upgrade/` only if operators must act; a
   newer segments-manager alone needs none.

The check of 2026-11-17 (`a4edc12`, nothing newer on `main`) covered the
removed area; git has it.

## Known gaps

- **None found at `a4edc12`** (checked 2026-11-17).
