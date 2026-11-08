# Day1 API changes the web app must follow (2026-11-07)

The rewritten day1 service (`apps/day1-service/src/wingman_day1`) keeps every
path the web app calls, with compatible JSON wherever the meaning did not
change. This note lists **every** change a client can see, for the stage that
updates `apps/web`. Each item says what changed, why, and what the web should
do. Paths are relative to the day1 service (`/api/day1`, `/api/auth`,
`/api/webhooks`).

## Everywhere

1. **Errors are RFC 9457 problems** (`application/problem+json`, ADR-0004):
   `{type, title, status, detail, instance, code, request_id, details}`.
   `detail` is still a human string, so `api-client.ts` (which reads
   `json.detail`) keeps working. Match on `code`, not text. Validation
   failures list every broken rule in `details.problems` (show them all on
   the form); FastAPI's own 422s list `details.errors[{loc,msg,type}]`.
2. **Request bodies reject unknown fields** (422). The web sends none today.
3. **MR responses** (`MRDetail`: create/modify/delete cluster, spec writes,
   approvals, audit) gain `project_id`, `sha` (the source branch head) and
   `merged_at`; `state` may be `locked`. `author.username`/`author.name` are
   the requester from the MR footer everywhere (audit used the raw GitLab
   author, i.e. the service account). `author.avatar_url` is always `""`.
4. **Commit authors** are now the requesting user (name, `<user>@openshift.local`)
   instead of the service account; history and audit show people.

## Auth (`/api/auth`)

5. **`POST /dev-login` requires `secret`** (the configured `DEV_AUTH_SECRET`,
   at least 32 characters, or the service refuses to start). The login page
   sends only `{username, role}` today → it now gets 401. Add a secret field
   (or a dev-only env-injected value). 404 when dev login is off. Usernames:
   lowercase letters, digits, `.`, `_`, `-`. Dev users' groups are
   `wingman-dev-admins` / `wingman-dev-viewers`.
6. `POST /callback`: 401 `UNAUTHORIZED` when OpenShift refuses the code, 403
   `FORBIDDEN` when the user is in no Wingman group, 502
   `DEPENDENCY_UNAVAILABLE` when OpenShift is unreachable. Body unchanged.
   The authorize URL is now URL-encoded.

## Sites and MCEs (ADR-0018)

7. **Removed: `POST /sites` and `POST /sites/{site}/mces`** (405). Wingman no
   longer creates sites or MCEs; drop the "Create new…" options on
   `/clusters/new`.
8. `GET /sites/{site}/mces` for an unknown site → 404 (was `[]`).
9. **New: `GET /mces[?site=]`** → `[{name, site, env, letter,
   follows_convention, naming_problems[], default_mastertag, hub_version,
   cluster_count, stray_files[], problems[]}]`. `default_mastertag` (the
   MCE's `values.yaml`) is a good default for the create form's OCP version;
   `stray_files` are files in `hostedClusters/` that break the MCE's
   ApplicationSet.

## Clusters (`/clusters`)

10. **List items** (`ClusterStatus`): `spec_name`/`spec_version` are `null`
    for clusters not linked to a spec (was the sentinel
    `"(not linked to a cluster spec)"`; `hasSpec()` already treats null as
    unlinked). New: `mastertag`, `path`, `hosted_cluster{cluster_name, name,
    namespace}`, `naming{follows_convention, env, short_name, sequence,
    problems[]}`, `problems[]` (a file that does not parse is listed with its
    problems instead of disappearing). `created_by`/`created_at` are the
    file's last change, as before. `phase` is always `Unknown`, as before.
11. **Detail `GET /clusters/{name}`**: `site`/`mce` are optional (names are
    unique; an ambiguous name answers 422). New: `path`, `last_commit_id`
    (send it back with an edit or delete), `values{owner, mastertag,
    platform, nodepools[{name, infra_env_name, replicas, allow_deletion,
    configs[], node_labels, tuning_config}], network{vlan_id,
    dhcp_network}, cluster_name, automation_keys[]}` (`null` if the file
    does not parse), `hosted_cluster`, `naming`, `mce_default_mastertag`,
    `problems[]`. `metadata.spec_name` is `null` when unlinked;
    `metadata.variables` is always `{}` (inputs are not stored);
    `metadata.requested_addons[{team, name, version, override_values}]` is
    new. Show VLAN/network from `values.network` (filled by the
    allocate-segment workflow after the MR is pushed).
12. **Create/preview** (`POST /clusters`, `POST /clusters/preview`):
    - `addon_overrides` is now honoured: keyed `"<team>/<name>"` of a spec
      addon (unknown key → 422), stored in the file header and shown in
      detail and drift. Send the override values the form collects (today
      it sends none).
    - `variables.openshift_release_version` is required. Identity variables
      (`cluster_name`, `site`, `mce`, `site_name`, `mce_name`) may be sent
      but must equal the top-level fields.
    - Every string variable must be single-line, ≤ 253 chars, without `"` or
      `\`.
    - New names are checked (ADR-0014): 422 with `details.problems` for a
      name off `ocp4-<env>-<name>-<site>[-<seq>]`, an env different from
      the MCE's, an off-convention MCE, a too-long derived namespace; 409
      `ALREADY_EXISTS` for a name used anywhere or by an open create MR;
      404 for an unknown site/MCE/spec.
    - A stale spec version is 409 `REVISION_CONFLICT` (was 400).
    - The preview body gains `path`.
13. **Modify `PATCH /clusters/{name}`**: `site`/`mce` optional; new optional
    `last_commit_id` (send the detail's: an edit of a file that changed
    since is 409 `REVISION_CONFLICT` instead of overwriting the workflow's
    or CI's commits). 422 when the edit changes or removes `vlanId`,
    `dhcp_values`, `mcFiles`, `mcConfigMap` or `clusterName`, lacks a valid
    `mastertag`, or changes nothing.
14. **Delete `DELETE /clusters/{name}`**: optional `last_commit_id` query.
15. **Removed: `POST /clusters/{name}/sync-yaml`** (405). Nothing is stored
    to re-render from (ADR-0016); drop the "Sync" button. Drift's
    `unified_diff` is always `""`.
16. **Drift `GET /clusters/{name}/drift`**: new `site`, `mce`, `state`
    (`in_sync | drifted | unknown | not_linked`), `current_spec_version`,
    `error`; `is_drifted` is `null` when unknown (day2 did not answer, the
    spec is gone); `addon_drift[]` items gain `override_values` (pass them
    to day2's install as `override_values` instead of `{}`). The legacy
    `reason: "No spec associated"` field is gone (`state: not_linked`).
    Only a missing spec addon is drift (ADR-0025): an `addon_drift[]`
    item's `reason` is only `"missing"` (`"version_mismatch"` is gone), and
    its fix installs it at the team default version: send day2's install
    no `version` (any other is refused as an unconfirmed emergency pin,
    ADR-0022). A spec addon installed at another version is listed in
    the new `version_differences[{addon_name, team, spec_version,
    installed_version}]`, does not make the cluster `drifted`, and has no
    fix: show it as information.
17. **`GET /clusters/drift-summary`** items gain `site`, `mce`, `state`,
    `error`; `is_drifted` may be `null`. Count unknowns separately.
18. **Status** (`/clusters/{name}/status`, `/status/stream`, `/bulk-status`):
    bodies gain `hosted_cluster` and `namespace` (the HostedCluster is now
    `openshift-<clusterName>` in `hcp-<clusterName>`, ADR-0015).
    `bulk-status` answers for every requested cluster, with `error` set on
    failures (it used to omit them). Off → 501 `FEATURE_DISABLED` problem
    (was a plain 501).
19. `GET /mces/{mce}/infraenvs`: 422 `VALIDATION_ERROR` for an MCE without a
    token, 404 for a namespace that does not exist, 502
    `DEPENDENCY_UNAVAILABLE` for hub errors, 501 when status is off.

## Specs (`/specs`)

20. List items may carry `load_error` and `load_problems[]`: a spec file
    that does not parse is listed (name only) instead of disappearing.
21. The spec document gains `spec.day1.values` (preset template inputs,
    merged under the form's values). Stored spec files no longer contain
    `day1.template` (it is still filled on read). Unknown keys → 422.
    `metadata.name` must be a DNS-1123 label, `metadata.version` one word.
22. `PUT /specs/{name}` and `DELETE /specs/{name}` accept `?last_commit_id=`;
    renaming in a PUT → 422; creating an existing spec → 409. `GET
    /specs/{name}` and the list items carry `last_commit_id` (the commit that
    last changed the file, a broken spec's too): send it back.
23. `GET /specs/{name}/clusters` items gain `state`, `error`;
    `GET /specs/{name}/drift` now returns real results (it always returned
    `[]`), items `{cluster, site, mce, state, is_drifted, spec_version,
    unified_diff: "", error}`.

## Approvals (`/approvals`)

24. **`POST /approvals/{iid}/approve` requires `{"sha": "<mr.sha>"}`**, the
    head the reviewer saw in `GET /approvals/{iid}` (422 without it). If the
    branch moved since (CI or the allocate-segment workflow pushed), it is
    409 `REVISION_CONFLICT` and nothing is merged: reload and review again.
    Self-approval is 403 `SELF_APPROVAL`.
25. `repo` defaults to `day1` on every approvals route, so the audit page's
    `GET /api/day1/approvals/{iid}` works (was 422). A specs MR still needs
    `?repo=specs`.
26. `PUT /approvals/{iid}`: only files the MR changes may be sent (422
    otherwise); optional `sha` (409 if the branch moved); a cluster file
    must keep the automation-owned keys. The commit goes on top of the
    branch (never a force-push), authored by the editor.
27. The approvals list includes open Wingman MRs whatever branch they target
    (the legacy list required `main`).

## Audit (`/audit`)

28. `GET /audit/commits` items gain `repo` (`day1 | specs`);
    `GET /audit/merge-requests` items carry the right `repo` (legacy tagged
    all `day1`). **Web fix needed**: stop overwriting `repo` with `"day1"`
    for day1-service items, and expand an MR with
    `/api/day1/approvals/{iid}?repo={repo}` (the page calls
    `/api/${repo}/approvals/...`, which for a specs MR is not even a route).
29. `GET /audit/commits/{repo}/{sha}/diff`: unknown SHA → 404 problem;
    a wrong `repo` hint is still tolerated.

## Removed or new elsewhere

30. Removed: `GET /api/day1/cache/stats`.
31. `POST /api/webhooks/gitlab` answers 404 when `GITLAB_WEBHOOK_SECRET` is
    empty (it accepted anyone) and 401 on a wrong token.
32. New: `GET /health/live`, `GET /health/ready` (GitLab reachable),
    `GET /metrics` (service port only); `/healthz` is kept.
33. New: `GET` and `POST /clusters/{name}/delete-workflow` (ADR-0033). Both
    answer 501 `FEATURE_DISABLED` ("not available yet") until the
    delete-cluster workflow exists. Then `GET` returns `{"run": null | {workflow_id,
    status, phase, error}}`, and `POST {"confirm": true}` (admin) returns 202 with the run.

## Deployment (chart) changes

Not web-visible, but the chart must change before this service deploys:

- `GITLAB_ACCESS_TOKEN` → `GITLAB_TOKEN`; `GITLAB_SSL_VERIFY` →
  `GITLAB_VERIFY_TLS` (core settings).
- Dropped: `GITLAB_DEFAULT_BRANCH` (each project's default branch is used),
  `DAY1_CLUSTERS_PATH_TEMPLATE`, `DAY1_CLUSTER_FILE_SUFFIX` (the layout is
  the ApplicationSet's contract), `CACHE_*` (one `DAY1_CACHE_TTL_SECONDS`,
  at most 60), `DAY1_SERVICE_URL`, `SERVICE_PORT`, `LOG_LEVEL`.
- New: `DAY1_CLUSTER_NAME_STRIP_PREFIX` (default `ocp4-`; `""` for the
  sandbox; `MCE_CLUSTER_NAME_PREFIX` still accepted), `WINGMAN_ENVIRONMENT`,
  `WINGMAN_GIT_BACKEND`, `DAY1_STATUS_POLL_SECONDS`,
  `DAY2_TIMEOUT_SECONDS`, `OPENSHIFT_TIMEOUT_SECONDS`, `MCE_TIMEOUT_SECONDS`,
  `WINGMAN_VERSION`, `WINGMAN_COMMIT`.
- `OPENSHIFT_SSL_VERIFY` and `MCE_SSL_VERIFY` now default to `true` (may name
  a CA bundle). `JWT_SECRET_KEY` must be ≥ 32 characters. The service
  refuses to start without a way to log in (complete OpenShift OAuth
  settings, or dev login with a strong secret).
- The image runs `uvicorn wingman_day1.main:app` as UID 1001, installed from
  `uv.lock`.
- Day1 calls day2's `GET /api/day2/clusters/{name}/addons?mce=&site=` with a
  5-minute viewer session for `system:wingman-day1` (same `JWT_SECRET_KEY`)
  and expects `{"installed": [{"team", "name", "version"}]}`; the day2
  rewrite must keep this or the coordinator adapts `HttpDay2Addons`.
