# Metrics

Every Wingman service exports Prometheus metrics at `GET /metrics` on its own
port (day1 `8001`, day2 `8002`). The path is outside `/api`, and the web app's
nginx proxies only `/api/*`, so `/metrics` is reachable from inside the
cluster (ServiceMonitor) and never through the public Route.

**Names and labels are a contract.** Dashboards and alerts are written against
them; renaming one breaks them silently. `tests/unit/observability/test_metrics_catalogue.py`
fails when this table and the code disagree.

## Label rules

- Every label value comes from a fixed set (a `StrEnum` in
  `wingman_core.observability.metrics`). Anything else is recorded as `other`.
- Never a label: cluster, team, user, MR number, file path, raw URL path. Each
  would create one series per value, without bound. Request metrics use the
  **route template** (`/api/day1/clusters/{name}`), and `<unmatched>` for
  requests no route matched.
- Series an alert depends on are created at zero on start-up, so "no failures
  yet" reads as `0`, not as a missing series.

## Catalogue

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `wingman_build_info` | gauge | `component`, `version`, `commit` | Always 1; which build is running. `component` is `day1` or `day2` (not `service`: Prometheus adds that as a target label). Version skew shows here. |
| `wingman_http_requests_total` | counter | `method`, `route`, `status_class` | HTTP requests served. `status_class` is `2xx`..`5xx`. |
| `wingman_http_request_duration_seconds` | histogram | `method`, `route` | Time to serve a request. |
| `wingman_dependency_requests_total` | counter | `dependency`, `operation`, `outcome` | Calls to an external system. `dependency` is `gitlab`, `kubernetes` (an MCE hub's API), `openshift_oauth` or `day2`; `operation` is a GitLabPort method, or one of the fixed operations below; `outcome` is `ok`, `not_found`, `already_exists`, `conflict`, `not_mergeable`, `denied`, `rejected`, `unavailable`, `ambiguous` or `error`. |
| `wingman_dependency_request_duration_seconds` | histogram | `dependency`, `operation` | Time spent in a call, retries included. |

Operations of the other dependencies (day1):

| `dependency` | `operation` |
|---|---|
| `kubernetes` | `get_hosted_cluster`, `list_node_pools`, `list_infra_envs` |
| `openshift_oauth` | `discover`, `exchange_code`, `get_user` |
| `day2` | `list_installed_addons` |

## Reading the GitLab outcomes

- `denied` means GitLab refused **Wingman's own token**: an expired or revoked
  token, or a missing project membership. Every user is affected; fix the
  deployment's `GITLAB_TOKEN`.
- `unavailable` means GitLab was unreachable or answered 5xx on a read, after
  retries. Nothing was written.
- `ambiguous` means a write was sent but its result is unknown (a timeout or a
  5xx after sending). Writes are never retried (ADR-0006). Someone must check
  whether the commit or merge happened before trying again.
