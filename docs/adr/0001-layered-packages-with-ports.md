# ADR-0001: Code is layered, and import-linter enforces the layers

Date: 2026-11-07
Status: Accepted; amended 2026-11-17 (an external system's day1 code is a package under
`wingman_day1/integrations/`, with these layers inside it), and 2026-11-23 (the two
integrations keep the layers they still have, without their areas)

## Context

The legacy services mix concerns in one place. A router calls a service that
builds GitLab paths, parses YAML, calls python-gitlab and raises FastAPI's
`HTTPException`, all in the same function. The consequences are measurable:
there were no Python tests at all, because nothing could be tested without a
GitLab. The approval flow was copied into day1 and day2 and drifted (day2
looks merge requests up by number alone, ADR-0007). And the infrastructure
model (folder names, CR kinds, naming patterns) is spread across services
instead of living in one place that can change when the ecosystem does.

server-scan and herzi, the team's reference repos, both separate a pure
domain from adapters and wire them in one composition root.

## Decision

Every Python package has the same layers:

| Layer | Holds | May import |
|---|---|---|
| `domain` | value objects, enums, pure rules (no I/O) | stdlib only |
| `ports` | `Protocol`s the application needs (`GitLabPort`, `Clock`) | `domain` |
| `application` | use cases: one function per thing a user does | `domain`, `ports` |
| `infrastructure` | adapters implementing ports (GitLab over httpx, the fake) | `domain`, `ports` |
| `observability` | metrics, and wrappers that record them | `domain`, `ports` |
| `web` / `api` | FastAPI routers, schemas, error rendering | everything above |

Each service has one composition root (`main.py`) that builds the adapters and
hands them to the application. The rules are import-linter contracts in the
root `pyproject.toml` and run in CI (`uv run lint-imports`). The domain may not
import any I/O library (`httpx`, `fastapi`, `pydantic_settings`,
`prometheus_client`).

## Alternatives rejected

- **Convention only, no enforcement.** server-scan documents a fifth contract
  it could not hold (application importing concrete repositories), because the
  rule was added after the code. Wingman's services are being rewritten anyway,
  so every contract is gated from the first commit.
- **A single shared "utils" package.** That is what `wingman_shared` became: a
  GitLab client, YAML helpers, auth and models with no direction between them.

## Consequences

- Application code is tested against the in-memory GitLab (ADR-0005), without
  a network.
- Adding an external system (server-scan, segments-manager, the workflow
  orchestrator) means a port plus an adapter plus a fake, never a client call
  from a router.
- `wingman_shared` is legacy. It is removed when day1 and day2 stop importing it.

## Verification

`uv run lint-imports` is a CI step and part of `scripts/gate.sh`. The
contracts are listed in `pyproject.toml` under `[tool.importlinter]`.

## Amendment (2026-11-17): an external system is one package, with the layers inside it

### Context

day1's layers were folders, so an external system's code was spread over
`domain/`, `ports/`, `application/`, `infrastructure/`, `api/v1/` and a
`compose_*.py`, held together only by a file prefix (`server_scan_*`,
`segments_manager*`). An upstream release then touched every layer:
Wingman's parity with server-scan v6.1.0 (PR #90) changed 34 files in 19
folders, 9 of them in day1's source and tests (`api/v1/`, `domain/`,
`infrastructure/`, `tests/api/`, `tests/unit/infrastructure/`), the rest in
the web, its E2E fixtures and the docs. Nothing told a reader which files
were one system's, or that the Nodes tab's code was not.

### Decision

- **One package per external system** with an area of its own:
  `apps/day1-service/src/wingman_day1/integrations/<system>/`, holding the
  same layers: `domain/`, `ports.py`, `application/`, `infrastructure/`
  (`adapter.py`, `parse.py`, `cached.py`, and the fake, `fake.py` or
  `fakes/`), `api/` (its routers and their `*_schemas.py`) and `compose.py`
  (its part of the composition root). Module names drop the prefix:
  `domain/server_scan_events.py` is `integrations/server_scan/domain/events.py`.
  Its tests are `apps/day1-service/tests/integrations/<system>/`. Today:
  `server_scan` (49 modules) and `segments_manager` (11).
- **What moves is what changes when the system does**: its API, its shapes
  and the Wingman area that mirrors it (the Server Scan area, the Segments
  area). Wingman's own features that use its data stay where they are and
  import the integration's `domain` and `ports`, never its adapters: the
  Nodes tab, placement, Inventory Management, a cluster's network check
  (ADR-0039), the Overview. Kept out on purpose: `domain/servers.py` (the
  Nodes tab's rules, and `ServerRow`, the row every one of those features
  reads), `domain/network.py` (ADR-0039's check and `SegmentRecord`, its
  input), `domain/errors.py` and `api/errors.py` (one error vocabulary
  mapped to RFC 9457 codes in one table, ADR-0004), `infrastructure/cache_keys.py`
  (one registry of keys, ADR-0011), `infrastructure/http.py` and
  `observed.py` (every adapter's), `api/conditional.py` (HTTP's conditional
  GET), `api/deps.py` (the routes' one context, ADR-0056), `settings.py`, and
  `infrastructure/fake_fleet.py` (the fake orchestrator's uninstall and the
  fleet fixture's loader, which seed server-scan's fake). The workflows
  orchestrator's adapters and the MCE hubs are not moved here; a move of
  theirs follows the same rule.
- **The contracts** (`[tool.importlinter]`): an integration's layers keep
  this ADR's rules inside it (five forbidden contracts over
  `wingman_day1.integrations.*`); day1's own domain may import an
  integration's domain, its ports and use cases also its ports, and none of
  them its adapters, routers or `compose`; nothing outside the composition
  root (`main.py`, `platform_adapters.py`, `compose_*.py`, an integration's
  `compose.py`) builds an integration's adapters, except that day1's
  infrastructure may use an integration's (the fake fleet reuses
  server-scan's fake and parser). An independence contract keeps the
  integrations from importing each other, directly or indirectly; it
  ignores only the two places that use every integration by design: day1's
  use cases reading a port (`wingman_day1.application.*` to an integration's
  `ports`) and the routes' context naming each area's use case (`api.deps`).
- **The web, decided at the same time**: an external system's area is
  `apps/web/features/<area>/` with `api/`, `types/`, `lib/` and
  `components/` (`features/server-scan/`, `features/segments/`); its page
  routes stay in `app/` (ADR-0056's 2026-11-17 amendment).

### Alternatives rejected

- **Layer folders and a file prefix** (as before): a release lands in five
  folders, and a file's prefix is the only sign of whose it is.
- **A distribution per system** (`wingman_server_scan` beside
  `wingman_day1`): the areas' use cases need day1's `ClusterService` and the
  routes' context; another `pyproject.toml`, lock entry and image install
  buys no isolation the contracts do not already give.
- **Moving the features that use the data too** (the Nodes tab, Inventory
  Management): the integration would then change for Wingman's reasons, and
  a feature that reads two systems would have no home.
- **Two direct-only forbidden contracts instead of independence**:
  import-linter 2.15's independence contract always follows indirect chains
  (it has no `allow_indirect_imports`), which is why it needs the two
  ignores above; direct-only contracts would also miss a chain through a
  shared adapter such as `infrastructure/http.py`, which it catches.

### Consequences

- A server-scan or segments-manager release lands in its integration, its
  tests' folder and its web feature folder (and the docs).
- day1's `ports` no longer re-exports `ServerInventory`; it, and
  `SegmentLedger`, are imported from their integration's `ports`.
- server-scan's adapter, its fake fleet's seeding and segments-manager's
  cached ledger for the network check are built in their `compose.py` or
  fake module, not in `platform_adapters.py` or `main.py`.
- Nothing a caller sees changed: the routes, payloads, metric names and
  labels, settings, and the audit logger's name
  (`wingman_day1.application.server_scan`, kept so its lines read the same).
- The ADRs and dated notes written before this (0038, 0039, 0047, 0048, the
  2026-11-13 API notes) name the old paths; they are left as history.

### Verification

- `uv run lint-imports` (23 contracts) in `scripts/gate.sh python`.
- 2026-11-17: 18 probe imports, each reverted, broke the contract meant to
  catch it: `httpx` or `settings` in an integration's domain, an adapter in
  its ports, use cases or routers, a use case in its adapter, `compose` in
  its router, an adapter or router in day1's domain, ports, use cases,
  infrastructure or API, and segments-manager's domain in server-scan's, both
  directly and through `infrastructure/http.py`.
- The moved tests pass unchanged in `tests/integrations/server_scan/` and
  `tests/integrations/segments_manager/`.

## Amendment (2026-11-23): the integrations without their areas

The Segments and Server Scan areas were removed (ADR-0066). `server_scan/`
and `segments_manager/` stay packages under `wingman_day1/integrations/`,
with the layers they still have: segments-manager's `domain/` (its links),
both `ports.py`, `infrastructure/` and `compose.py`; neither has an
`application/` or an `api/` any more. The routes' context names no
integration's use case, so the independence contract ignores one chain
only, Wingman's use cases reading an integration's port. The contracts for
an integration's use cases and routes stay, for the next one that has them.
The web's `features/` folder went with the areas (ADR-0056's amendment of
the same day).
