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

- The chart ships a ServiceMonitor, a PrometheusRule built from the plain
  `chart/files/alerts.rules.yaml` (7 alerts, each unit-tested with promtool and
  each with a runbook section in `docs/ops/runbook.md`) and a Grafana
  dashboard (`chart/dashboards/wingman.json`, also as a sidecar ConfigMap).
  All three are off by default (`monitoring.*`): they need the Prometheus
  Operator CRDs.
- The build label is `component`, not `service`: Prometheus adds `service` as a
  target label, and the clash would rename ours to `exported_service`.

## Verification

`packages/wingman-core/tests/unit/observability/test_metrics_catalogue.py`:
the exact families, types and labels; the docs table matches the code; alerted
outcomes exist at zero; `other` fallbacks; a scrape through ASGI.

`tests/repo/test_observability_contract.py`: every metric and label used by an
alert or a dashboard query is exported, every alert has a runbook section and
every section an alert, dashboard panels use the datasource variable and the
`job` filter, and a panel quoting an alert's threshold quotes the real one.
Verified on 2026-11-07 by breaking each: a misspelled metric in a rule and a
wrong threshold in a panel each fail the suite. `promtool test rules
chart/tests/alerts.test.yaml` fires and clears each alert.
