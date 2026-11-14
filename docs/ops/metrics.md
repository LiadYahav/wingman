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
| `wingman_dependency_requests_total` | counter | `dependency`, `operation`, `outcome` | Calls to an external system. `dependency` is `gitlab`, `kubernetes` (an MCE hub's API), `openshift_oauth`, `day2`, `server_scan`, `workflows` (the workflows orchestrator) or `segments_manager`; `operation` is a GitLabPort method, or one of the fixed operations below; `outcome` is `ok`, `not_found`, `already_exists`, `conflict`, `not_mergeable`, `denied`, `rejected`, `unavailable`, `ambiguous` or `error`. |
| `wingman_dependency_request_duration_seconds` | histogram | `dependency`, `operation` | Time spent in a call, retries included. |
| `wingman_placement_decisions_total` | counter | `decision` | day1 only: creates checked against MCE placement (ADR-0050). `decision` is `picked` (Wingman's pick), `override` (an admin chose another MCE that passes every check, with a reason) or `refused` (the MCE failed a check, an override had no reason, or the form's pick was stale). Previews are not counted. |
| `wingman_rollout_runs_total` | counter | `trigger` | Flavor rollout runs (day1, ADR-0044), by what started them: `merge` (Wingman merged the flavor's MR), `webhook` (the specs project's webhook), `reconcile` (an admin pressed Reconcile) or `read` (the rollout status was read with work pending). Every value exists at zero from start-up; day2 exports them at zero. |
| `wingman_rollout_merge_requests_total` | counter | `outcome` | What flavor rollouts (day1) did with each cluster's merge request: `opened`, `recovered` (an MR opened for a branch an earlier run left without one), `superseded` (an open MR to an older version was closed for the new one), `failed` (GitLab refused the write), `unconfirmed` (GitLab did not confirm the write, ADR-0006; the next run checks the branch and MR) or `not_sent` (not started because GitLab stopped answering in that run). Every value exists at zero from start-up; day2 exports them at zero. Never a cluster, flavor or version label. |

Operations of the other dependencies (day1):

| `dependency` | `operation` |
|---|---|
| `kubernetes` | `get_hosted_cluster`, `list_node_pools`, `list_infra_envs`, `list_machines`, `list_machine_sets`, `list_agent_machines`, `list_agents`, `list_nodes`, `list_pods` |
| `openshift_oauth` | `discover`, `exchange_code`, `get_user` |
| `day2` | `list_installed_addons`, `list_open_installs`, `install_addons` |
| `server_scan` | `list_server_rows`, `get_server`, `list_sites`, `enable_maintenance`, `disable_maintenance`, `get_server_record`, `get_vm_host`, `list_server_events`, `get_skill`, `download_skill`, `get_architecture_diagram`, `list_confs` |
| `workflows` | `list_runs`, `get_run`, `start_uninstall`, `start_provision`, `upgrade_targets`, `start_upgrade`, `decide_upgrade`, `start_add_server` |
| `segments_manager` | `get_segment`, `list_sites`, `get_stats`, `list_segments`, `refresh_segments` |

## Reading the GitLab outcomes

- `denied` means GitLab refused **Wingman's own token**: an expired or revoked
  token, or a missing project membership. Every user is affected; fix the
  deployment's `GITLAB_TOKEN`.
- `unavailable` means GitLab was unreachable or answered 5xx on a read, after
  retries. Nothing was written.
- `ambiguous` means a write was sent but its result is unknown (a timeout or a
  5xx after sending). Writes are never retried (ADR-0006). Someone must check
  whether the commit or merge happened before trying again.
- The readiness probe adds GitLab calls only until a pod's first pass
  (`get_project`, and day2's `list_group_projects`; ADR-0054). After that,
  every GitLab call is a request's, a rollout's, a warm-up's or a cache
  refresh's: an idle Wingman makes none, so no GitLab traffic is not an outage.

## Reading placement

- `kubernetes` `list_nodes` and `list_pods` are MCE placement's reads of a
  hub's own nodes and pods (ADR-0050), one per page of 500. `denied` means
  the MCE token may not list them: that MCE is never picked until the grant
  in the chart README is applied (the upgrade guide has the steps).
  `list_agents` also counts the servers check's reads of the needed
  InfraEnvs' Agents, one per page.
- `wingman_placement_decisions_total`: a rising `override` is admins
  disagreeing with the rule; a rising `refused` is people choosing MCEs that
  fail a check, or forms left open while the counts moved.

## Reading the server-scan, workflows and segments-manager outcomes

- `server_scan` `denied` means server-scan refused **Wingman's viewer token**
  (`SERVER_SCAN_TOKEN`); `unavailable` means it could not be reached or
  answered with an error. The nodes are still listed, without their servers,
  and the answer's `server_scan_error` says why; an uninstall answers 502.
- `server_scan` `list_server_rows` is the fleet's rows: the Nodes tab,
  placement, Inventory Management and the Server Scan area's Servers page
  read them from one cache entry, at most once per replica per
  `DAY1_CACHE_TTL_SECONDS` however many pages poll, each a `304` from
  server-scan while nothing changed (ADR-0048's 3.23.0 amendment).
- `server_scan` `list_sites` is the Server Scan area's Sites page
  (server-scan's per-site counts, ADR-0048), also read by an admin's top bar to know
  the area is on: at most one call per replica per 10 seconds (its cache),
  whoever asks, and none while no admin is signed in. `denied` (the viewer
  token refused) and `unavailable` on it are the area's `502`; the Nodes
  tab, placement and Inventory Management are not affected.
- `server_scan` `enable_maintenance` and `disable_maintenance` are the Server
  Scan area's one write, a server's maintenance on and off by an admin
  (ADR-0048's 3.23.0 amendment), each logged with the person
  (`server_maintenance_started`, `_ended`). `denied` means server-scan
  refused **its admin token** (`SERVER_SCAN_ADMIN_TOKEN`); `not_found` a
  server it does not have; `rejected` a body it refused (its `422`);
  `ambiguous` a write sent whose answer was lost (logged as
  `server_maintenance_unconfirmed`): never retried, look at the server's row
  before trying again.
- `server_scan` `get_server_record`, `get_vm_host` and `list_server_events`
  are the Server Scan area's server page (ADR-0048's 3.25.0 amendment): the
  server whole, a VM's host and the server's History, one call each per page
  open or History page, never cached by day1 (server-scan caches the record
  itself). `not_found` is an id server-scan does not have, or a VM host asked
  of a server that is not a VM. `denied` on `get_server_record` and
  `get_vm_host` is the viewer token refused (`SERVER_SCAN_TOKEN`); on
  `list_server_events` it is **the auditor token** (`SERVER_SCAN_AUDITOR_TOKEN`).
  `get_server` stays the uninstall's fresh check of a server's cluster.
- `server_scan` `get_skill` and `download_skill` are the Server Scan area's
  Claude page (ADR-0048's 3.29.0 amendment): server-scan's Claude Code skill,
  at most one call per replica per minute (its cache), and its zip, one call
  per download, never cached. Both use the viewer token: `denied` is
  `SERVER_SCAN_TOKEN` refused. `not_found` is a server-scan that carries no
  skill (the page says so); `unavailable` on `download_skill` includes
  server-scan refusing the address written into the zip (check
  `SERVER_SCAN_UI_URL`).
- `server_scan` `get_architecture_diagram` is the Server Scan area's
  Architecture page (ADR-0048's 3.28.0 amendment): one of server-scan's
  diagrams, read from **its UI** (`SERVER_SCAN_UI_URL`, else
  `SERVER_SCAN_URL`) with no token, at most once per diagram per replica per
  5 minutes (its cache). `not_found` is a diagram server-scan's UI does not
  serve, or an address that is not its UI (its API has no diagrams);
  `unavailable` its UI unreachable or answering anything but the page.
- `server_scan` `list_confs` is the Server Scan area's Confs page, the
  hardware catalog (ADR-0048's 3.29.0 amendment): one call per page open, and
  again when it is opened after 30 seconds, never cached by day1 (a small
  collection server-scan reads per call). `denied` is the viewer token
  refused (`SERVER_SCAN_TOKEN`); `unavailable` includes an answer day1 could
  not read.
- `workflows` `start_uninstall` `ambiguous` means an uninstall start was sent
  and its answer was lost (ADR-0006, ADR-0038). It is never retried: look at
  the node's uninstall run before starting it again. `conflict` is the
  orchestrator's "already uninstalling"; `rejected` is a body it refused.
- `workflows` `start_provision` is a create that starts the provision-cluster
  workflow (`DAY1_PROVISIONER=workflow`, ADR-0042). `ambiguous`: sent, answer
  lost; look at the cluster's provision run before creating it again.
  `conflict`: a run for the cluster is already going. `rejected`: the
  orchestrator refused the name or the file (its 422).
- `workflows` `upgrade_targets`, `start_upgrade` and `decide_upgrade` are a
  cluster's upgrade through the upgrade-cluster workflow (`DAY1_UPGRADES`,
  ADR-0055). The targets read waits for a short run, up to
  `WORKFLOWS_TARGETS_TIMEOUT_SECONDS`: a slow one is the orchestrator's
  wait, and `unavailable` includes its 504 (no limb answered). `not_found`:
  the workflow's day1 has no such file, or no running run takes the
  decision; `rejected`: the file or the rules cannot be used, or a body the
  orchestrator refused. `decide_upgrade` counts every decision and agent
  proposal, with no decision label: `conflict` is the run's validator
  refusing one (the person sees its words), `ambiguous` a decision sent
  whose answer was lost (it may have landed; never retried). `start_upgrade`
  `conflict`: the cluster already has an open run.
- `workflows` `start_add_server` is an admin adding servers to an MCE's
  InfraEnv pool from Inventory Management (`DAY1_ADD_SERVERS`, ADR-0057).
  `ambiguous`: sent, answer lost; some runs may have started, so look at the
  pool's runs before asking again (never retried: a pool draw sent twice
  installs twice). `conflict`: a named server already installing, or every
  slot of the pool busy. `rejected`: a body the orchestrator refused (its
  422). Inventory's run list is `list_runs` and `get_run` (the 20 newest
  runs, each kept 10 seconds).
- `segments_manager` `get_segment` is one cluster's segment, read for its
  EPG (ADR-0039). A segment segments-manager does not have is `ok`: that is
  an answer, shown as a warning. `unavailable` means it could not be reached
  or answered with an error; the cluster's VLAN and segment are still shown
  (they are the file's), and the answer's `ledger_error` says why.
- `segments_manager` `list_sites`, `get_stats` and `list_segments` are the
  Segments area's reads (ADR-0047). An open page re-reads every 30 seconds,
  and the pages a replica serves share one read of each per 10 seconds (its
  cache); none while nobody has the page open.
  `refresh_segments` is its Refresh button (`fresh=true`: segments-manager
  reads its database, not its cache), at most one per replica per 5 seconds.
  `unavailable` on them is the area's `502`; the cluster pages are not
  affected.
