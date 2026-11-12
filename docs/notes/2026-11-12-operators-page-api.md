# Operators page: the API the web uses (3.9, ADR-0053)

What the web needs from day2 for the Operators pages, and what changed for
the add-on authoring endpoints of 3.8 (ADR-0043,
`docs/notes/2026-11-12-day2-addon-authoring-api.md`). Everything is under
`/api/day2`. Reads take a viewer, writes an admin; every write is refused
first with `403 TEAM_READ_ONLY` for a team that has not given Wingman write
access.

Words: an **operator** is a chart in a team's catalog, `operators/<op>/`,
and the fleet defaults built from it (`defaults/<scope>/<op>/`). An
**add-on** is that chart on one cluster, managed from the cluster's page
(unchanged). The API keeps `addon` in its paths.

## 1. Reads

### `GET /teams/{team}/operators`

The team's operators, one per `operators/<op>/` folder plus one per fleet
default whose chart is not in the catalog (`in_catalog: false`), by name.

```jsonc
[
  {
    "team": "redbull",
    "name": "kyverno",
    "in_catalog": true,
    "repourl": "https://gitlab.example/helm-charts/kyverno.git",   // "" when unknown
    "target_revision": "HEAD",
    "sync": { "auto_sync": false, "prune": false, "self_heal": false, "sync_options": ["CreateNamespace=true"] },
    "ocp_versions": ["4.16.27"],                 // ocp-versions/<v>/ folders
    "defaults": [                                // only the scopes it is a default on
      { "scope": "mces", "label": "every MCE", "reach": 2, "excluded": 1 }
    ],
    "installed_on": 3,                           // apps from clusters' own folders
    "warnings": 0,
    "writable": true,
    "read_only_reason": null
  }
]
```

### `GET /teams/{team}/operators/{operator}`

One operator: its files, its OCP-version pins, and one panel per scope.
404 when the team has neither `operators/<op>/` nor any `defaults/*/<op>/`.

```jsonc
{
  "team": "redbull",
  "name": "kyverno",
  "in_catalog": true,
  "writable": true,
  "read_only_reason": null,
  "catalog": { /* CatalogEntryOut, as GET /addons/{team}/{addon}; null when !in_catalog */ },
  "deploy_config": File,                         // operators/<op>/<op>.yaml
  "values_file": File,                           // operators/<op>/values.yaml
  "ocp_versions": [
    { "version": "4.16.27", "target_revision": "release-4.16",
      "deploy_config": File, "values_file": File }
  ],
  "scopes": [ScopePanel, ScopePanel, ScopePanel, ScopePanel],  // hosted-clusters, mces, hub, upi
  "warnings": [Finding]
}
```

`File` (a file of the team repo; `last_commit_id` is the commit it was read
at, send it back on an edit of that file):

```jsonc
{ "path": "operators/kyverno/kyverno.yaml", "exists": true,
  "text": "# why kyverno prunes\nrepourl: ...\n",       // null when absent
  "values": { "repourl": "..." },                         // parsed; {} when absent or invalid
  "last_commit_id": "abc123...", "problem": null }        // problem: the YAML error, if any
```

`ScopePanel`:

```jsonc
{
  "scope": "mces", "label": "every MCE", "noun": "MCE(s)",
  "is_default": true,
  "folder": "defaults/mces/kyverno",
  "values_file": File,                 // defaults/<scope>/<op>/values.yaml
  "deploy_config": File,               // defaults/<scope>/<op>/<op>.yaml (sync override)
  "sync": SyncOut,                     // effective over the team default
  "sync_overridden": false,
  "env_files": [ { "env": "prep", "file": File } ],     // values-<env>.yaml that exist (read-only)
  "exclusions": {                      // null for the hub (there are none)
    "path": "defaults/mces/exclusions.yaml",
    "exists": true,
    "names": ["ocp4-prep-mce-site1-a"],       // this operator's entry, as written
    "unknown_names": [],                     // names in it that are no destination of the team
    "editable": true,                        // false: Wingman cannot edit it in place
    "problem": null,                         // why not editable (or the YAML error)
    "last_commit_id": "abc123..."
  },
  "destinations": [ScopeDestination],  // every destination of that kind the team's repo registers
  "unregistered": [                    // known to day1 (MCEs, hosted clusters) or other teams, not to this team
    { "id": "mce:site2:prod:ocp4-prod-mce-site2-a", "name": "ocp4-prod-mce-site2-a",
      "site": "site2", "env": "prod", "mce": "ocp4-prod-mce-site2-a" }
  ],
  "last_commit_id": "abc123..."        // the commit the team repo was read at
}
```

`ScopeDestination`:

```jsonc
{
  "id": "mce:site1:prep:ocp4-prep-mce-site1-a", "name": "ocp4-prep-mce-site1-a",
  "kind": "mce", "site": "site1", "env": "prep", "mce": "ocp4-prep-mce-site1-a",
  "ocp_version": "4.16.27",
  "renders": true,                     // false: day1 has no version for it, the platform renders nothing
  "state": "default",                  // see below
  "deployed": true,                    // an app of this operator exists there
  "app_name": "redbull-in-cluster-kyverno-deploy",       // null when not deployed
  "override": File,                    // defaults/<scope>/<op>/values-<name>.yaml; null for the hub
  "override_shared_with": [],          // other destinations whose name is the same, so the same file
  "own_folder": null,                  // its own <op>/ folder, when it has one
  "own_deploy": null                   // File of <own_folder>/<op>.yaml, when it has an own folder
}
```

`state`:

| state | meaning |
|---|---|
| `default` | the default deploys it here |
| `excluded` | `exclusions.yaml` keeps the default off it: no app |
| `own-deploy` | excluded, and it has its own folder: deployed from there, with its own deploy config (the platform's full-override carve-out) |
| `own-folder` | not a default on this scope; the cluster has the chart in its own folder (an add-on of the cluster) |
| `duplicate` | a default **and** its own folder, not excluded: the platform generates the app twice (an error) |
| `none` | not a default, no own folder |
| `not-rendered` | the platform renders nothing for it (`renders: false`) |

On the hub: one destination (`hub`), `default` or `none`, no `override`,
no `exclusions`.

## 2. The plan every authoring write answers with

Every write takes `?dry_run=true` (200, the plan; nothing is opened) and
otherwise answers 201 (create, make default) or 200 (edits) with the opened
MR. Both carry the 3.8 fields (`action`, `chart`, `scope`, `reach`,
`adopted`, `needs_confirmation`, `warnings`, `notes`; the plan `title` and
`files`, the MR its `MRDetail` and `files`) and, new in 3.9:

```jsonc
{
  "impact": [                    // every destination whose app of this operator changes, goes, or comes
    { "cluster": "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1",
      "name": "ocp4-prod-herzi-site1", "kind": "hosted",
      "effect": "changed",       // "changed" | "removed" | "added"
      "app_name": "redbull-ocp4-prod-herzi-site1-podinfo-deploy",
      "changes": [ { "stack": "deploy", "key": "projectNamespace", "before": null, "after": "other-ns" },
                   { "stack": "values", "key": "resources.limits.cpu", "before": null, "after": "1" } ],
      "orphaned": false }        // true for "removed": the Application goes, the workload keeps running
  ],
  "excluded": ["mce:site1:prep:ocp4-prep-mce-site1-a"],  // the scope's destinations the default skips, after
  "digest": "9f2c…"              // sha256 of what the MR writes and does (files, impact, title)
}
```

- `changes` compare the effective deploy config and workload values
  **before and after, chart defaults aside**, key by key. Each change is
  `{stack, key, before, after, after_null}`: `after_null: true` is a Helm
  `null`, which deletes the chart's own default for that key (the web says
  so); a key no layer sets any more has `after: null` and
  `after_null: false`. The same shape is in `adopted[].changes`, and an
  adopted item has `exclusion_removed`.
- `needs_confirmation` lists every `removed` destination and every `changed`
  one, plus (as in 3.8) adopted clusters whose move changes something.
- **Confirming**: the request repeats `needs_confirmation` in
  `confirm_changes` (exactly; 422 `confirm-changes` otherwise) **and** the
  preview's `digest` in `expected_digest`. With anything to confirm,
  `expected_digest` is required (422 `confirm-against-preview`). When it is
  sent and the repo moved so the plan is no longer the previewed one, the
  answer is `409 REVISION_CONFLICT` with `details.rule = "plan-changed"` and
  `details.digest`, the new one: re-run the preview and show it. Nothing was
  opened. The web always sends the preview's digest.

## 3. New writes

### `PUT /addons/{team}/{addon}/defaults/{scope}/exclusions`

Which destinations of the scope the fleet default skips. Edits
`defaults/<scope>/exclusions.yaml` in place (comments kept byte for byte;
created when absent).

```jsonc
{ "excluded": ["mce:site1:prep:ocp4-prep-mce-site1-a"],   // the full set, by id; the others are included
  "last_commit_id": "abc123…",                           // ScopePanel.exclusions.last_commit_id
  "confirm_changes": [], "expected_digest": null, "message": null }
```

- Excluding a destination deletes its Application; `prune: false` leaves the
  workload running, unmanaged (`impact[].effect = "removed"`,
  `orphaned: true`; it must be confirmed). Including one generates it again
  (`added`); the new Application adopts what is still running.
- Names in the entry that are no destination of the team are kept as written
  (and stay a lint error, `exclusions-unknown-target`).
- 422 `rule`: `hub-override` (the hub has none), `destination-unknown` (an id
  that is not a registered destination of that scope), `exclusion-shared`
  (two destinations of the scope share the name: they are excluded together
  or not at all, `details.clusters`), `own-deploy`
  (including a destination that has its own deploy config: remove that
  instead), `exclusions-layout` (the file cannot be edited exactly; the
  detail says why), `no-change`. 404 when the operator is not a default
  there.
- Title: `[Wingman/Day2] Exclude addon <team>/<op> from <names> (fleet default on every MCE)`,
  `Include addon <team>/<op> on <names> (...)`, or with both,
  `Update addon <team>/<op> exclusions (...)`. Action `set-exclusions`.

### `PUT /addons/{team}/{addon}/defaults/{scope}/destinations/{cluster}/values`

A per-destination value override of a fleet default:
`defaults/<scope>/<op>/values-<name>.yaml`.

```jsonc
{ "values": { "replicas": 3 },          // null or {}: delete the file (back to the default's values)
  "last_commit_id": "abc123…",          // ScopeDestination.override.last_commit_id (null when absent)
  "confirm_changes": [], "expected_digest": null, "message": null }
```

- The effective values before and after, with provenance, come from
  `POST /merge-preview` (`override_values` previews exactly this file for a
  destination the default deploys to); the plan's `impact` has the key
  changes for every destination the file reaches (`override_shared_with`).
- 422 `rule`: `hub-override` (the hub's values are the default's own
  `values.yaml`), `override-name-is-env` (a name equal to `prod`, `prep` or
  `test` is the env layer), `destination-unknown`, `no-change`. 409 when the
  file changed since `last_commit_id`, or was deleted since.
- Title: `[Wingman/Day2] Override addon <team>/<op> values on <name> (fleet default on every MCE)`;
  deleting: `... values on <name>: back to the fleet default (...)`. Action
  `override-values`.

### `PUT /addons/{team}/{addon}/defaults/{scope}/destinations/{cluster}/deploy`

A per-destination deploy-config override, the platform's carve-out: the
destination is excluded from the default and gets its own
`<own folder>/<op>/<op>.yaml`, in one commit. The Application keeps its name
(both folders generate the same one), so ArgoCD keeps it.

```jsonc
{ "deploy": { "target_revision": "v2.1", "repourl": null, "path": null, "project_namespace": null },
  // null: remove the own deploy config: the own folder goes (a non-empty values.yaml there moves to
  // values-<name>.yaml) and the exclusion entry with it, so the default deploys it again
  "last_commit_id": "abc123…",
  "confirm_changes": [], "expected_digest": null, "message": null }
```

- Only the keys that are set are written; `target_revision` must be a branch
  of the chart repo (a warning: it detaches this destination from the team
  default and OCP-version pins, an emergency pin).
- Its values still come from the default's layers (`values.yaml`,
  `values-<env>.yaml`, `values-<name>.yaml`) below the own folder's.
- 422 `rule`: `hub-override`, `destination-unknown`, `exclusions-layout`,
  `adoption-blocked` (the own folder holds other files), `no-change`.
- Title: `[Wingman/Day2] Override addon <team>/<op> deploy config on <name> (...)`;
  removing: `... deploy config on <name>: back to the fleet default (...)`.
  Action `override-deploy`.

## 4. Changed in 3.9 (review of 3.8)

- `POST /addons/{team}` (create), `PUT /addons/{team}/{addon}` (team
  default), `POST|PUT /addons/{team}/{addon}/defaults/{scope}` (make and
  edit a fleet default): all take `confirm_changes` and `expected_digest`
  and answer `impact`, `excluded`, `digest`. A create now lists every
  cluster that already had the chart in its own folder and changes (the new
  team layer sits under it); a team-default or fleet-default edit lists every
  destination it changes; all of them must be confirmed.
- Make default: a cluster whose own folder moves into the default **and**
  that an old entry of `exclusions.yaml` names for that chart would lose its
  app. The entry is removed in the same commit; the cluster is in
  `needs_confirmation` and its `adopted[]` item has `exclusion_removed: true`.
- Fleet-default values with `null` show as changes (`after: null`).
- A values file deleted after the read is a 409, not silently created again.
- `ignore_differences: []` removes the key.
- Teams: a team whose access could not be read is read-only with
  `access_role: "unknown"` and a reason; the others are unaffected (one
  failing project no longer fails `/teams`, `/addons`, `/fleet-defaults`).
  Access through a group share of the project counts.
