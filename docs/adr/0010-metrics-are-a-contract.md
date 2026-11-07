# ADR-0010: Metrics follow one catalogue with bounded labels, served off the public Route

Date: 2026-11-07
Status: Accepted

## Context

Wingman exported no metrics. Nobody could see whether GitLab calls were
failing, whether Wingman's token had expired (every user affected), or whether
a write's outcome was unknown. herzi and server-scan both ship an exporter,
alert rules and a dashboard, and both learned the same lessons: unbounded
label values grow without end, and a dashboard drifts unless a test ties it
to the code.

## Decision

- One catalogue in `wingman_core.observability.metrics`, documented in
  `docs/ops/metrics.md`. Names start with `wingman_`; renaming one is a
  breaking change.
- Label values come from fixed sets (`StrEnum`s); unknown values become
  `other`. Cluster, team, user, MR number and paths are never labels. Request
  metrics use the route template, and `<unmatched>` for unrouted requests.
- The registry is injected (built per app), never the global default, so tests
  and multiple apps do not share state.
- Every GitLab call is counted and timed by `InstrumentedGitLab`, a wrapper
  around any `GitLabPort`, so the fake reports the same metrics as production.
- Series an alert reads are pre-created at zero.
- `/metrics` lives on each service's own port, outside `/api`. nginx proxies
  only `/api/*`, so Prometheus reaches it in-cluster and the public Route
  never exposes it.

## Alternatives rejected

- **Metrics inside the adapter.** The fake would export nothing, and local
  dashboards would be empty.
- **Exposing `/metrics` through the Route** (server-scan does, for its UI).
  Wingman's UI does not need it.

## Consequences

- Alert rules, a ServiceMonitor and a Grafana dashboard ship with the chart
  next (alerts unit-tested with promtool, as in herzi; the dashboard checked
  against this catalogue, which would have caught server-scan's drifted
  threshold).

## Verification

`packages/wingman-core/tests/unit/observability/test_metrics_catalogue.py`:
the exact families, types and labels; the docs table matches the code; alerted
outcomes exist at zero; `other` fallbacks; a scrape through ASGI.
