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
  yet" reads as `0`, not as a missing series. So is every value of the
  rollout counters' one label.

## Catalogue

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `wingman_build_info` | gauge | `component`, `version`, `commit` | Always 1; which build is running. `component` is `day1` or `day2` (not `service`: Prometheus adds that as a target label). Version skew shows here. |
| `wingman_http_requests_total` | counter | `method`, `route`, `status_class` | HTTP requests served. `status_class` is `2xx`..`5xx`. |
| `wingman_http_request_duration_seconds` | histogram | `method`, `route` | Time to serve a request. |
| `wingman_dependency_requests_total` | counter | `dependency`, `operation`, `outcome` | Calls to an external system. `dependency` is `gitlab`, `kubernetes` (an MCE hub's API), `openshift_oauth`, `day2`, `server_scan`, `workflows` (the workflows orchestrator), `segments_manager`, `link_check` (Quick Links' status checks) or `argocd` (Quick Links' ArgoCD counts); `operation` is a GitLabPort method, or one of the fixed operations below; `outcome` is `ok`, `not_found`, `already_exists`, `conflict`, `not_mergeable`, `denied`, `rejected`, `unavailable`, `ambiguous` or `error`. |
| `wingman_dependency_request_duration_seconds` | histogram | `dependency`, `operation` | Time spent in a call, retries included. |
| `wingman_rollout_runs_total` | counter | `trigger` | Flavor rollout runs (day1, ADR-0044), by what started them: `merge` (Wingman merged the flavor's MR), `webhook` (the specs project's webhook), `reconcile` (an admin pressed Reconcile) or `read` (the rollout status was read with work pending). Every value exists at zero from start-up; day2 exports them at zero. |
| `wingman_rollout_merge_requests_total` | counter | `outcome` | What flavor rollouts (day1) did with each cluster's merge request: `opened`, `recovered` (an MR opened for a branch an earlier run left without one), `superseded` (an open MR to an older version was closed for the new one), `failed` (GitLab refused the write), `unconfirmed` (GitLab did not confirm the write, ADR-0006; the next run checks the branch and MR) or `not_sent` (not started because GitLab stopped answering in that run). Every value exists at zero from start-up; day2 exports them at zero. Never a cluster, flavor or version label. |

Operations of the other dependencies (day1):

| `dependency` | `operation` |
|---|---|
| `kubernetes` | `get_hosted_cluster`, `list_node_pools`, `list_infra_envs`, `list_machines`, `list_machine_sets`, `list_agent_machines`, `list_agents` |
| `openshift_oauth` | `discover`, `exchange_code`, `get_user` |
| `day2` | `list_installed_addons`, `list_open_installs`, `install_addons` |
| `server_scan` | `list_server_rows`, `get_server` |
| `workflows` | `list_runs`, `get_run`, `start_uninstall`, `start_provision` |
| `segments_manager` | `get_segment` |
| `link_check` | `check_link` |
| `argocd` | `list_applications` |

## Reading the GitLab outcomes

- `denied` means GitLab refused **Wingman's own token**: an expired or revoked
  token, or a missing project membership. Every user is affected; fix the
  deployment's `GITLAB_TOKEN`.
- `unavailable` means GitLab was unreachable or answered 5xx on a read, after
  retries. Nothing was written.
- `ambiguous` means a write was sent but its result is unknown (a timeout or a
  5xx after sending). Writes are never retried (ADR-0006). Someone must check
  whether the commit or merge happened before trying again.

## Reading the server-scan, workflows, segments-manager and Quick Links outcomes

- `server_scan` `denied` means server-scan refused **Wingman's viewer token**
  (`SERVER_SCAN_TOKEN`); `unavailable` means it could not be reached or
  answered with an error. The nodes are still listed, without their servers,
  and the answer's `server_scan_error` says why; an uninstall answers 502.
- `workflows` `start_uninstall` `ambiguous` means an uninstall start was sent
  and its answer was lost (ADR-0006, ADR-0038). It is never retried: look at
  the node's uninstall run before starting it again. `conflict` is the
  orchestrator's "already uninstalling"; `rejected` is a body it refused.
- `workflows` `start_provision` is a create that starts the provision-cluster
  workflow (`DAY1_PROVISIONER=workflow`, ADR-0042). `ambiguous`: sent, answer
  lost; look at the cluster's provision run before creating it again.
  `conflict`: a run for the cluster is already going. `rejected`: the
  orchestrator refused the name or the file (its 422).
- `segments_manager` `get_segment` is one cluster's segment, read for its
  EPG (ADR-0039). A segment segments-manager does not have is `ok`: that is
  an answer, shown as a warning. `unavailable` means it could not be reached
  or answered with an error; the cluster's VLAN and segment are still shown
  (they are the file's), and the answer's `ledger_error` says why.
- `link_check` `check_link` is one of Quick Links' status checks (ADR-0052):
  `ok` the link answered 2xx, 3xx, 401 or 403 (a dot that is up);
  `not_found` it answered 404, `rejected` another 4xx, `unavailable` 5xx,
  no answer within `QUICK_LINKS_TIMEOUT_SECONDS` or no connection (a dot
  that is down); `error` TLS could not be verified (a dot that is unknown:
  set `QUICK_LINKS_SSL_VERIFY` or the CA bundle). The URL is never a label.
  Checks run only while someone reads the page, at most once per link per
  `QUICK_LINKS_STATUS_TTL_SECONDS`.
- `argocd` `list_applications` is one ArgoCD's application list, read with
  its read-only token for a Quick Links card's counts. `denied` means the
  ArgoCD refused **that token** (expired, revoked, or the account may not
  list applications): replace it in the ArgoCD tokens Secret and restart
  day1. `unavailable` means no answer or an error answer; the card shows
  its link and dot without the counts. The instance is never a label.
