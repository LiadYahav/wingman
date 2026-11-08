# ADR-0001: Code is layered, and import-linter enforces the layers

Date: 2026-11-07
Status: Accepted

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
