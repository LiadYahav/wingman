# Add-on authoring and per-team write access: the day2 API the web reads (2026-11-12)

What day2 adds so a team can, from Wingman, add a new add-on to its repo,
edit an add-on's team default (its deploy config, sync options included,
and its values), make an add-on a default across a fleet (every hosted
cluster, every MCE, the hub, every UPI cluster), and edit a fleet default.
Each change is one merge request on the team's repo (`sigs/<team>`), as
every day2 change is (ADR-0022). Writes are per-team opt-in: a team that has
not given Wingman's GitLab account write access to its project is read-only
in Wingman. Decisions and reasons: ADR-0043. Everything here is under
`/api/day2`; request bodies refuse unknown fields (422).

**Changed in 3.12 (ADR-0053):** every write here also answers `impact`,
`excluded` and `digest`, and what it deletes or changes on any destination
is confirmed in `confirm_changes` together with the preview's digest as
`expected_digest` (409 `plan-changed` when the repo moved since the
preview). See `docs/notes/2026-11-12-operators-page-api.md` §2 and §4.

## 1. Per-team write access

Wingman uses one GitLab account (the chart's `gitlab.accessToken`). A team
opts in by making that account a **Developer (or higher) member of its own
project** `sigs/<team>`; then Wingman can push a branch and open an MR there.
Wingman reads the account's access per team project (GitLab
`GET /projects/:id` → `permissions`, the higher of `project_access` and
`group_access`), keeps it for the read cache's TTL, and:

- **writable** (access ≥ 30, Developer): every day2 write works as before;
- **read-only** (anything less, or no membership): every day2 write for that
  team is refused with `403 TEAM_READ_ONLY` (create add-on, edit a default,
  make default, install, update, remove, bulk install, and approve, reject and
  edit of its MRs). Reads work wherever Wingman can read the project.

Membership in the sigs group (or a group above it) is inherited by every team
project, so it turns writes on for every team at once. Per-team opt-in needs
the account to be a member of each opting-in project, not of the group.

### `GET /teams`, `GET /teams/{team}`

Each team gains four fields:

```json
{
  "name": "orca",
  "project_id": 3,
  "path_with_namespace": "sigs/orca",
  "web_url": "https://gitlab.example/sigs/orca",
  "writable": false,
  "access_level": 20,
  "access_role": "reporter",
  "read_only_reason": "orca hasn't given Wingman write access to sigs/orca: Wingman's GitLab account is a Reporter there, and opening a merge request needs Developer or higher. A maintainer of sigs/orca turns writes on by adding the account to the project as a Developer."
}
```

- `access_level`: GitLab's number (0 none, 5 minimal, 10 guest, 15 planner,
  20 reporter, 30 developer, 40 maintainer, 50 owner).
- `access_role`: its name (`none`, `minimal`, `guest`, `planner`, `reporter`,
  `developer`, `maintainer`, `owner`).
- `read_only_reason`: `null` when `writable`; otherwise one sentence to show
  as is (it names the team and the project).

`GET /teams/{team}` is one of these (404 for an unknown team).

### `403 TEAM_READ_ONLY`

```json
{
  "type": "/problems/team-read-only",
  "title": "Team Read Only",
  "status": 403,
  "code": "TEAM_READ_ONLY",
  "detail": "<the same sentence as read_only_reason>",
  "details": {"team": "orca", "project": "sigs/orca", "access_level": 20, "access_role": "reporter", "required_level": 30}
}
```

It comes before any other check of the request, so a read-only team's write
never gets as far as a validation error.

## 2. Sync options

The leaf Application's ArgoCD `syncPolicy`, as four settings. Every request
and response below uses this shape:

```json
{"auto_sync": false, "prune": false, "self_heal": false, "sync_options": ["CreateNamespace=true"]}
```

- `auto_sync`: `syncPolicy.automated` is present (ArgoCD syncs by itself
  after the merge). Off means manual sync: nothing deploys until someone
  syncs the app in ArgoCD (Wingman has no ArgoCD access).
- `prune`, `self_heal`: `automated.prune` and `automated.selfHeal`. They
  exist only with auto-sync: a request with either `true` and `auto_sync`
  `false` is `422` (`details.rule`: `sync-without-auto`).
- `sync_options`: `syncPolicy.syncOptions`, in order, each `Name=value`
  (`^[A-Za-z][A-Za-z0-9]*=[A-Za-z0-9._-]+$`, else `422`, rule
  `sync-option-invalid`; duplicates are `422` too). The template offers a
  list of common ones (§3); any option of that shape is accepted.

Other `syncPolicy` keys a file already has (`retry`,
`managedNamespaceMetadata`, `automated.allowEmpty`) are kept as they are and
not shown.

## 3. A new add-on

### `GET /teams/{team}/addon-template`

What the New add-on form starts from, read from the team's own files:

```json
{
  "team": "redbull",
  "writable": true,
  "read_only_reason": null,
  "sync": {"auto_sync": false, "prune": false, "self_heal": false, "sync_options": ["CreateNamespace=true"]},
  "sync_source": "the sync options most of sigs/redbull's add-ons use (3 of 3)",
  "repourl_prefix": "https://gitlab.example/helm-charts/",
  "known_sync_options": ["CreateNamespace=true", "ServerSideApply=true", "PruneLast=true", "ApplyOutOfSyncOnly=true", "RespectIgnoreDifferences=true", "Replace=true", "Validate=false", "SkipDryRunOnMissingResource=true", "FailOnSharedResource=true", "PrunePropagationPolicy=foreground", "PrunePropagationPolicy=background", "PrunePropagationPolicy=orphan"],
  "scopes": [
    {"scope": "hosted-clusters", "label": "every hosted cluster", "destinations": ["hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1", "..."]},
    {"scope": "mces", "label": "every MCE", "destinations": ["mce:site1:prod:ocp4-prod-mce-site1-a", "..."]},
    {"scope": "hub", "label": "the hub", "destinations": ["hub"]},
    {"scope": "upi", "label": "every UPI cluster", "destinations": ["upi:site1:prod:ocp4-dok-site1"]}
  ]
}
```

- `sync`: the sync options most of the team's add-ons
  (`operators/*/<chart>.yaml`) use; with no add-on yet, the platform's
  default: manual sync with `CreateNamespace=true`. `sync_source` says
  which, for a hint under the control.
- `repourl_prefix`: the folder most of the team's add-ons' chart repos sit in
  (`<prefix><chart>.git` is a good pre-fill), or `null`.
- `scopes`: the four fleet scopes, each with the destinations a default there
  reaches today: the folders this team's repo has for that kind, minus none
  (exclusions name charts, and a new default has none). A fleet default
  reaches only clusters the team's repo has a folder for.

### `POST /addons/{team}` (admin)

```json
{
  "name": "podinfo",
  "repourl": "https://gitlab.example/helm-charts/podinfo.git",
  "target_revision": null,
  "path": null,
  "project_namespace": "podinfo",
  "sync": {"auto_sync": false, "prune": false, "self_heal": false, "sync_options": ["CreateNamespace=true"]},
  "ignore_differences": null,
  "values": {},
  "default_scope": null,
  "default_values": {},
  "confirm_changes": [],
  "message": null
}
```

- `name` (required): the chart folder, a DNS label (lowercase letters,
  digits, `-`; 422 `chart-name`). It becomes part of Application names.
- `repourl` (required): `http(s)://...`; written under the lowercase key
  `repourl`, the only spelling the platform reads. A URL on this GitLab must
  name a project Wingman can read (422 `chart-repo-missing`); one elsewhere is
  accepted with a warning (versions and chart defaults will not be shown).
- `target_revision`: a branch of the chart repo; `null` or absent means
  `HEAD` (the repo's default branch) and writes no key. A branch the repo does
  not have is 422 `revision-unknown`.
- `path`: the chart's folder in its repo; `null`/absent/`"."` writes no key.
- `project_namespace`: the destination namespace (a DNS label, else 422
  `namespace-invalid`); `null` writes no key.
- `sync` (required): §2.
- `ignore_differences`: ArgoCD's list of objects, written as given (anything
  else is 422 `ignore-differences-invalid`); `null` writes no key.
- `values`: `operators/<name>/values.yaml` (`{}` when empty).
- `default_scope`: also make it a fleet default in the same MR (`hub`,
  `mces`, `hosted-clusters`, `upi`); `default_values` is then
  `defaults/<scope>/<name>/values.yaml`. As §5, including clusters that
  already have a folder of that name, which `confirm_changes` confirms as
  there.

Writes `operators/<name>/<name>.yaml` and `operators/<name>/values.yaml`
(plus §5's files with `default_scope`). `409 ALREADY_EXISTS` (rule
`addon-exists`) when `operators/<name>/` exists. Title:
`[Wingman/Day2] Create addon <team>/<name> in the team catalog` (with a
scope: `... and as a fleet default on every hosted cluster`). Labels
`wingman`, `day2`, `create-addon`.

## 4. An add-on's team default

### `GET /addons`, `GET /addons/{team}/{addon}`

Each catalog entry gains:

```json
{
  "writable": true,
  "read_only_reason": null,
  "sync": {"auto_sync": false, "prune": false, "self_heal": false, "sync_options": ["CreateNamespace=true"]},
  "ignore_differences": null,
  "deploy_config_exists": true,
  "last_commit_id": "9f1c…"
}
```

`sync` is what `operators/<chart>/<chart>.yaml` sets (an OCP-version pin, a
fleet default or a cluster folder may override it per destination; the
values preview's `deploy` shows the effective leaf). `last_commit_id` is the
commit the entry was read at: send it back on edit.

### `PUT /addons/{team}/{addon}` (admin)

Every field is optional; an absent field is left as it is.

```json
{
  "repourl": "https://gitlab.example/helm-charts/kyverno.git",
  "target_revision": "3.3.0",
  "path": null,
  "project_namespace": "kyverno",
  "sync": {"auto_sync": true, "prune": false, "self_heal": true, "sync_options": ["CreateNamespace=true", "ServerSideApply=true"]},
  "ignore_differences": null,
  "values": {"replicas": 2},
  "last_commit_id": "9f1c…",
  "message": null
}
```

- `null` for `target_revision`, `path`, `project_namespace` or
  `ignore_differences` removes that key (`HEAD`, `.`, no namespace).
  `repourl` cannot be removed (422 `repourl-missing`). `sync` and `values`
  absent or `null` are unchanged.
- A miscased `repoUrl` the file has is replaced by `repourl` when the request
  sets `repourl`.
- The deploy config is **edited in place**: only the keys that change are
  rewritten, and every other line, comments included, stays as it is. A file
  whose layout the editor cannot edit exactly (a comment inside a value it
  must rewrite, flow style across lines, anchors) is 422
  `deploy-config-layout`, with the reason; edit that file by hand.
- `values` replaces `operators/<addon>/values.yaml` (rewritten, as a
  cluster's values file is today).
- `last_commit_id`: the entry's; a file changed since is `409 REVISION_CONFLICT`.
- Nothing to change is 422 `no-change`.

The notes say which destinations the change reaches (every destination that
gets the add-on and does not override the changed keys). Title:
`[Wingman/Day2] Update addon <team>/<addon> team default`. Label
`update-default`.

## 5. Making an add-on a fleet default

A chart folder in `defaults/<scope>/` is deployed to every destination of that
kind the team's repo registers (ADR-0020). The app it generates on a cluster
has the **same name** as the one a cluster folder generates
(`<team>-<cluster>-<chart>` and its leaf `<team>-<cluster>-<chart>-deploy`),
and the same value files. So a cluster that already has the chart in its own
folder must lose that folder in the same commit (a chart in both is the same
app twice: the XOR rule), and when it does, ArgoCD keeps the same
Applications: nothing is deleted, re-created or orphaned. Wingman moves those
folders into the default in the same MR:

- `<cluster folder>/<chart>/values.yaml` (when not empty) becomes
  `defaults/<scope>/<chart>/values-<cluster>.yaml`, copied byte for byte;
  the cluster's own `<chart>.yaml` is deleted;
- a `.gitkeep` keeps the cluster registered if that was its last folder;
- a chart folder holding any other file is 422 `adoption-blocked` (move it by
  hand).

The values file moves below the MCE-wide and cluster-wide value files in the
stack, and the cluster's own deploy config goes, so Wingman compares each such
cluster's effective deploy config and values before and after. A cluster
where nothing changes moves without asking. A cluster where something
changes (an emergency pin, a namespace, sync options, a value) is listed with
each changed key, and the request must confirm exactly those clusters in
`confirm_changes`, else 422 `confirm-changes` (its `details.adopted` lists
them, as in a dry run).

### `GET /fleet-defaults[?team=]`

Every `defaults/<scope>/<chart>/` folder, with or without a catalog entry:

```json
{
  "team": "redbull",
  "chart": "example-chart",
  "scope": "mces",
  "scope_label": "every MCE",
  "path": "defaults/mces/example-chart",
  "in_catalog": false,
  "values": {},
  "values_exists": true,
  "sync": {"auto_sync": false, "prune": false, "self_heal": false, "sync_options": ["CreateNamespace=true"]},
  "sync_overridden": true,
  "reach": ["mce:site1:prep:ocp4-prep-mce-site1-a", "mce:site1:prod:ocp4-prod-mce-site1-a"],
  "excluded": [],
  "tweaks": ["defaults/mces/example-chart/values-ocp4-prep-mce-site1-a.yaml"],
  "last_commit_id": "9f1c…",
  "writable": true,
  "read_only_reason": null,
  "warnings": []
}
```

- `sync`: the effective settings, the team default with the fleet layer
  (`defaults/<scope>/<chart>/<chart>.yaml`) on top; `sync_overridden`: the
  fleet layer sets `syncPolicy`.
- `reach`: the destinations it deploys to; `excluded`: those
  `exclusions.yaml` keeps it off; `tweaks`: the per-env and per-cluster
  value files (edited per cluster, through the cluster's add-on page).

### `POST /addons/{team}/{addon}/defaults/{scope}` (admin)

```json
{
  "values": {},
  "sync": null,
  "confirm_changes": [],
  "message": null
}
```

- `{scope}`: `hub`, `mces`, `hosted-clusters` or `upi`. The add-on must be in
  the catalog (`operators/<addon>/`, else 404); `defaults/<scope>/<addon>/`
  must not exist (409 `default-exists`).
- `values`: `defaults/<scope>/<addon>/values.yaml` (always written, `{}` when
  empty: the file is what makes the folder exist).
- `sync`: `null` inherits the team default's; otherwise the fleet layer gets
  the `syncPolicy` keys that make the effective settings these, and only when
  they differ.
- `confirm_changes`: cluster ids, from a dry run's `needs_confirmation`.

Title: `[Wingman/Day2] Promote addon <team>/<addon> to a fleet default on every hosted cluster`
(`every MCE`, `the hub`, `every UPI cluster`). Label `make-default`.

### `PUT /addons/{team}/{addon}/defaults/{scope}` (admin)

```json
{"values": {"fleet": true}, "sync": {"auto_sync": true, "prune": false, "self_heal": true, "sync_options": []}, "last_commit_id": "9f1c…", "message": null}
```

The default must exist (404 otherwise). Absent fields are unchanged; `sync:
null` removes the fleet layer's `syncPolicy` (back to the team default's).
`values` replaces `defaults/<scope>/<addon>/values.yaml`; the per-cluster
`values-<x>.yaml` files are not touched. The fleet `<addon>.yaml` is edited in
place as in §4. Title: `[Wingman/Day2] Update addon <team>/<addon> fleet default on every MCE`.
Label `update-default`. Works for a fleet default without a catalog entry too
(`in_catalog: false`).

Stopping being a default is not here yet (ADR-0043, left for later): it
deletes the default's Applications and, with `prune: false`, orphans the
workloads on every destination. Until then: exclusions per cluster
(runbook R10) or by hand.

## 6. Dry runs and results

Every write above takes `?dry_run=true`: it runs every check, opens nothing,
and answers `200` with the plan. The web shows the plan (and its diffs)
before the real request; Make default needs it to fill `confirm_changes`.

```json
{
  "team": "redbull",
  "action": "make-default",
  "chart": "cluster-roles",
  "scope": "hosted-clusters",
  "title": "[Wingman/Day2] Promote addon redbull/cluster-roles to a fleet default on every hosted cluster",
  "files": [
    {"action": "create", "path": "defaults/hosted-clusters/cluster-roles/values.yaml", "content": "{}\n", "previous": null},
    {"action": "delete", "path": "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/cluster-roles/cluster-roles.yaml", "content": null, "previous": ""}
  ],
  "reach": ["hosted:site1:prep:ocp4-prep-mce-site1-a:ocp4-prep-eyal-site1", "..."],
  "adopted": [
    {
      "cluster": "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1",
      "name": "ocp4-prod-herzi-site1",
      "moved": [],
      "deleted": ["sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/cluster-roles/cluster-roles.yaml", "sites/.../cluster-roles/values.yaml"],
      "gitkeep": "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/.gitkeep",
      "changes": []
    }
  ],
  "needs_confirmation": [],
  "warnings": [],
  "notes": ["..."]
}
```

- `files[].action`: `create`, `update` or `delete`; `content` is the new
  text (`null` for a delete), `previous` the current one (`null` for a create).
- `adopted[]` (make default, and create with `default_scope`): each cluster
  whose own folder moves into the default. `moved`: `[{from, to}]`;
  `changes`: `[{stack: "deploy" | "values", key: "syncPolicy.automated.prune", before, after}]`
  (dotted leaf paths; `before`/`after` `null` when absent). Empty `changes`
  means the move changes nothing on that cluster.
- `needs_confirmation`: the ids of `adopted` with `changes`.

The real request answers `201` (`POST`) or `200` (`PUT`) with the opened MR
(the `MRDetail` fields, as an install's answer has them) plus `action`,
`chart`, `scope`, `files [{action, path}]`, `reach`, `adopted`, `warnings`
and `notes`.

## 7. Errors

| Status, code | `details.rule` | When |
|---|---|---|
| 403 `TEAM_READ_ONLY` | | the team has not given Wingman write access (§1) |
| 404 `NOT_FOUND` | | unknown team, add-on, or fleet default |
| 409 `ALREADY_EXISTS` | `addon-exists`, `default-exists` | the folder exists already |
| 409 `REVISION_CONFLICT` | | a file changed since `last_commit_id` |
| 422 `VALIDATION_ERROR` | `chart-name`, `repourl-invalid`, `repourl-missing`, `chart-repo-missing`, `revision-unknown`, `namespace-invalid`, `ignore-differences-invalid`, `sync-without-auto`, `sync-option-invalid`, `sync-layering`, `adoption-blocked`, `confirm-changes`, `deploy-config-layout`, `yaml-invalid` (a file the change needs does not parse), `no-change`, or a lint rule the change would break (ADR-0023) | the request cannot be written as asked |

Warnings a plan may carry (`warnings[].rule`): `chart-repo-elsewhere` (the
chart repo is not on this GitLab), `chart-values-missing` (no `values.yaml` at
the chart's path and revision), `repourl-moved`, and `sync-differs` (an
OCP-version pin or a cluster's own deploy config gives some destinations other
sync options than the default's).

Body validation (a wrong type, an unknown field) is 422 as everywhere.
