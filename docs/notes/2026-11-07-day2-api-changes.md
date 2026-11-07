# day2 API changes for the web app (2026-11-07)

The day2 service was rewritten on `wingman-core` against the gitops-day2
layout (ADR-0020 to ADR-0024). Paths and field names are kept where the
meaning is unchanged; this note lists everything the web app can see that
changed. Request bodies now refuse unknown fields (422).

## Addressing clusters

- `{name}` in every `/api/day2/clusters/{name}/...` path is now a **cluster
  id** or a bare name that names exactly one destination:
  `hub`, `mce:<site>:<env>:<mce>`, `hosted:<site>:<env>:<mce>:<cluster>`,
  `upi:<site>:<env>:<cluster>`. URL-encode it (`:` is safe, but encode anyway).
- `?mce=` is **optional** (was required); with a bare name it narrows the match.
- A bare name that matches several destinations is 422 with
  `details.candidates` (their ids); an unknown one is 404.
- The web app should switch to ids from `GET /api/day2/clusters`; bare names
  keep today's hosted-cluster pages working meanwhile.

## New endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/day2/teams` | `[{name, project_id, path_with_namespace, web_url}]` |
| `GET /api/day2/clusters[?kind=&site=&env=]` | every destination: `{id, kind, name, site, env, mce, ocp_version, argo, teams, in_day1, warnings}` |
| `GET /api/day2/clusters/{id}` | one of those |
| `GET /api/day2/clusters/{id}/upgrade-check?to=<version>` | `{cluster, from_version, to_version, warnings}`: pinned charts lacking `ocp-versions/<to>/` |
| `GET /api/day2/lints[?team=]` | every finding `{rule, severity, message, team, path, cluster, chart}` |
| `GET /health/live`, `/health/ready`, `/metrics` | probes and Prometheus (not under `/api`) |

Removed: `GET /api/day2/cache/stats`.

## Catalog (`GET /addons`, `/addons/{team}/{addon}`)

- `current_version` is the team default `targetRevision`, else **`HEAD`**
  (was: `targetRevision`, else the first branch, else `main`).
- `argocd_metadata` is always present; its `targetRevision` defaults to
  `HEAD` (was `main`); it gains `path`. `repourl` is `""` when the team
  default only has the miscased `repoUrl`.
- `available_versions`: every branch, default branch first, then newest
  release first (was: minus `master/HEAD/develop/dev`, `main` first).
- `dependencies` is always `[]`, and `default_values` is `values.yaml`
  verbatim (a `dependencies:` key is no longer popped out of it).
- New: `ocp_version_pins [{version, target_revision}]`, `fleet_defaults`
  (scopes), `chart_project`, `warnings`.
- `GET /addons/{team}/{addon}/values`: `version` is optional (default `HEAD`).

## Installed charts (`GET /clusters/{id}/addons`)

- Keeps `{cluster, mce, installed}`; adds `id, kind, site, env, ocp_version,
  excluded [{team, name, scope}], warnings, argocd_note`.
- `installed` now includes **fleet defaults** and works for all four kinds.
- Per chart: `version` is now the **effective** `targetRevision` (was the
  cluster override or `""`). New: `source` (`cluster` | `fleet-default`),
  `path`, `override_path` (the file an edit writes: the chart folder's
  `values.yaml`, or `defaults/<scope>/<chart>/values-<cluster>.yaml` for a
  fleet default), `last_commit_id` (send it back on update), `pinned`,
  `deploy` (the leaf app: `app_name, argo, namespace, repo_url,
  target_revision, path, release_name, destination, destination_namespace,
  sync_policy, auto_sync`), `warnings`. `parse_errors` items are findings now.
- Nothing about sync or health: Wingman has no ArgoCD access yet.

## Values preview (`GET /clusters/{id}/addons/{team}/{addon}`, `POST /merge-preview`)

- Same top-level keys (`merged, provenance, chart_values, team_values,
  cluster_values, addon_name, team, version`).
- `provenance` leaves are now layer **roles**: `chart, hub, team,
  team-ocp-version, site, site-env, fleet, fleet-env, fleet-target, mce,
  upi-wide, cluster-wide, cluster` (was only `chart|team|cluster`).
- `version` is the chart revision used (`HEAD` when unpinned); `?version=`
  previews another one.
- New: `cluster` (id), `installed`, `source`, `ocp_version`, `chart {project,
  revision, path, problem}` (why chart defaults are missing, if they are),
  `layers [{role, path, exists, values, last_commit_id, problem}]`,
  `deploy` (the leaf plus its own `layers` and per-key `provenance`), `warnings`.
- `merge-preview` body: `mce` optional, `cluster` may be an id, new
  `override_values` (previews an edit of the cluster's values file).
- Merging follows Helm exactly: `null` deletes a key, even a chart default.

## Writes

All writes return the opened MR as an `MRDetail` plus `cluster, files
[{action, path}], app_names, warnings, notes`. Read `notes`: they say what
else the change registers, that nothing deploys until someone syncs, and
that a removal leaves the workload running. Refusals are RFC 9457 problems
with `details.rule`.

- **Install** `POST /clusters/{id}/addons/{team}/{addon}`: `version` is
  optional and is honoured only if it equals the inherited revision, or with
  `emergency_pin: true` (else 422 `emergency-pin-required`). New fields:
  `emergency_pin`, `repourl` (needed when no layer has a lowercase one: 422
  `repourl-missing`), `project_namespace`, `message`. A chart that is a fleet
  default there is 409 `ALREADY_EXISTS` with `rule: xor` and the
  `values-<cluster>.yaml` to edit instead. Title:
  `[Wingman/Day2] Install addon <team>/<chart> on <cluster>` (the `v<version>`
  suffix is gone).
- **Update** `PUT ...`: send `last_commit_id` from the installed listing; a
  stale one is 409 `REVISION_CONFLICT`. `version` no longer writes a pin
  unless `emergency_pin`; setting the inherited version removes a pin. A
  no-op is 422 `no-change`. Title `[Wingman/Day2] Update addon <team>/<chart> on <cluster>`.
- **Remove** `DELETE ...[?last_commit_id=]`: a fleet default is 422
  `fleet-default-remove` (exclude it instead).
- **Bulk** `POST /clusters/{id}/addons/bulk`: items may come from several
  teams; the response is now `{merge_requests: [...], failed: [{team, error,
  detail}]}` (was one `MRDetail`); one refused item refuses all (422 `bulk`,
  `details.problems`), nothing opened. Labels are `install` (was
  `bulk-install`), titles follow the convention (were `[Day2] ...`).

## Approvals and audit

- MRs are addressed by **team and number**: `/approvals/{team}/{iid}` for
  GET, PUT, `/approve`, `/reject` (was `/approvals/{iid}`, which could act on
  another team's `!iid`). The web id `day2-<iid>` must become
  `day2-<team>-<iid>` or similar.
- `POST .../approve` requires a body `{sha}`: the MR head the approver
  reviewed (`MRDetail.sha`); a branch that moved since is 409. Approving your
  own change is 403 `SELF_APPROVAL`.
- `PUT /approvals/{team}/{iid}` edits only files the MR already changes
  (422 `path-not-in-mr`); each file may carry `last_commit_id`.
- `MRDetail` gains `team, project_id, sha, gitlab_author`. `author.username`
  is the requester from the description footer everywhere, audit included
  (audit used to show GitLab's author, the service account).
- `GET /audit/merge-requests` lists only Wingman MRs (label `wingman`).
  `CommitRecord` gains `team`. `GET /audit/commits/{sha}/diff` takes an
  optional `?team=`.
- `GET /clusters/{id}/history` entries keep `{sha, short_sha, message,
  author, date, web_url, team}`.

## Errors

Every error is `application/problem+json` with `type, title, status, detail,
instance, code, request_id, details` (ADR-0004). `detail` is still a string,
so the current `api-client.ts` message extraction keeps working.
