# Flavors v2, stage 1: day1 API changes the web app builds on (2026-11-08)

Stage 1 of `docs/ideas/flavors-v2.md`: the machine-config catalogue, the
nodepool defaults, config checks, enforced locks and numeric owners, all in
day1 (`apps/day1-service`). This note is the contract the web stage builds
against; every new or changed endpoint and field is here. Decisions:
ADR-0026 (locks), ADR-0027 (machine configs and defaults), ADR-0028
(owners). "Flavor" is the UI's word for a spec (`/api/day1/specs`).

Paths are relative to the day1 service. Errors are RFC 9457 problems as
before (`docs/notes/2026-11-07-day1-api-changes.md` §1): every rule a
request breaks is one string in `details.problems` of a 422
`VALIDATION_ERROR`, so the form can show them all at once. Each problem
starts with the template-input path it is about (`nodepools[1].configs[0]:
...`, `owner_anaf: ...`, `locked_paths: ...`), in the path syntax below, so
the form can attach it to its field. A body that fails its own JSON schema
(a wrong type, an unknown field) is still FastAPI's 422 with
`details.errors[{loc, msg, type}]`.

## 1. New: `GET /api/day1/machine-configs` (any session)

What a nodepool's `configs` may name, read from `mc-files/` in the day1
repo, plus the nodepool defaults from the specs project. Cached for
`DAY1_CACHE_TTL_SECONDS` (or until the GitLab webhook says the repo moved).

```json
{
  "network_config": "nm-conf",
  "static_configs": [
    {"name": "nic-ring-buffer", "folder": "", "path": "mc-files/nic-ring-buffer.bu"},
    {"name": "worker-kubeletconfig-reserved", "folder": "", "path": "mc-files/worker-kubeletconfig-reserved"},
    {"name": "workers-chrony-configuration", "folder": "", "path": "mc-files/workers-chrony-configuration.bu"},
    {"name": "kubevirt-worker-tuning", "folder": "kubevirt", "path": "mc-files/kubevirt/kubevirt-worker-tuning.bu"}
  ],
  "hardware_types": [
    {"name": "cisco", "template": "mc-files/templates/nm-conf-template-hw-cisco.bu"},
    {"name": "dell", "template": "mc-files/templates/nm-conf-template-hw-dell.bu"},
    {"name": "dell-data", "template": "mc-files/templates/nm-conf-template-hw-dell-data.bu"}
  ],
  "nodepool_defaults": {
    "path": "nodepool-defaults.yaml",
    "found": true,
    "configs": [
      {"name": "nm-conf"},
      {"name": "workers-chrony-configuration"},
      {"name": "nic-ring-buffer"}
    ],
    "error": null,
    "problems": []
  },
  "problems": []
}
```

(That is the response on the fixtures.)

- `network_config` is always `"nm-conf"`: the entry name that stands for
  the cluster's own network config (§3).
- `static_configs`: root first, then by folder, then by name. `folder` is
  `""` for the `mc-files/` root; group the picker by it. `name` is what
  goes in an entry. Nothing from `mc-files/legacy/` is ever listed.
- `hardware_types`: sorted by name; the choices for an `nm-conf` entry.
- `nodepool_defaults`: the entries a new nodepool starts with, in the
  entry shape of §3 (`hardware` is absent when the nodepool picks it).
  - `found: false`: the specs project has no `nodepool-defaults.yaml`;
    `configs` is `[]`. No defaults, not an error.
  - `error` set (a string): the file exists but cannot be used (not YAML,
    not a mapping, unknown keys, more than 50 entries); `configs` is `[]`
    and `problems` says why. Show it; do not treat it as "no defaults".
  - `error: null` and non-empty `problems`: these default entries would not
    resolve (for example a config removed from `mc-files/`); prefilling
    them leads to the same 422 at save.
- `problems` (top level): files in `mc-files/` that are not offered, and
  why (a static file a template's suffix would capture, a name found twice,
  a template not named `nm-conf-template-hw-<hw>.bu`, or no `mc-files/`
  folder at all). For an admin view; the picker can ignore it.
- A GitLab read failure is a 503 problem, as for every read.

**Use:** when a nodepool is added (flavor editor and create form), fill its
`configs` with `nodepool_defaults.configs` (copy the objects as they are)
unless the flavor locks that nodepool's configs. Day1 never applies the
defaults itself, and changing them never changes an existing flavor or
cluster.

## 2. Path syntax (locks and problems)

```
path  := name ( "." name | "[" index "]" )*
name  := [A-Za-z_][A-Za-z0-9_]*
index := "0" | [1-9][0-9]{0,2}        (no leading zero, below 1000)
```

At most 253 characters, no spaces: `owner_merkaz`, `nodepools[0].configs`,
`nodepools[1].node_labels`. This is the syntax
`components/clusters/dynamic-variable-form.tsx` already builds
(`${basePath}[${i}]`, `${basePath}.${name}`). `nodepools.0.configs` is not
a path.

## 3. Changed: nodepool config entries (create and flavor values)

A `nodepools[i].configs` entry is one of:

```json
{"name": "workers-chrony-configuration"}
{"name": "nm-conf", "hardware": "dell"}
```

- The first names a static config from `static_configs[].name`.
- The second is the cluster's own network config for hardware type
  `dell` (from `hardware_types[].name`). Day1 writes it to the cluster file
  as `{name: nm-conf-<clusterName>-<hw>}`, where clusterName is the chart's
  (the file stem minus `DAY1_CLUSTER_NAME_STRIP_PREFIX`, default `ocp4-`):
  `ocp4-prod-falcon-site1` with `dell` → `nm-conf-prod-falcon-site1-dell`.
  The preview shows the expanded name. A flavor stores the entry as
  written, never expanded.
- `hardware` belongs only to `nm-conf`; omit it (or send `null`) on static
  entries. No other keys.

Checked on `POST /clusters`, `POST /clusters/preview` (the merged inputs:
flavor presets, then the request, then locks) and on `POST /specs`,
`PUT /specs/{name}` (`spec.day1.values`). One problem per bad entry:

| Entry | Problem (after `nodepools[i].configs[j]: `) |
|---|---|
| `{"name": "nm-conf"}` | `nm-conf needs a hardware type, one of cisco, dell, dell-data` |
| `{"name": "nm-conf", "hardware": "hp"}` | `no hardware type 'hp', one of cisco, dell, dell-data` |
| `{"name": "nic-ring-buffer", "hardware": "dell"}` | `hardware applies only to nm-conf, not to 'nic-ring-buffer'` |
| `{"name": "worker-chrony-configuration"}` | `no machine config 'worker-chrony-configuration' in mc-files/ (did you mean 'workers-chrony-configuration'?)` |
| `{"name": "nic-ring-buffer.bu"}` | `write 'nic-ring-buffer' without .bu: the CI names a butane config so` |
| `{"name": "restored-example-config"}` | `'restored-example-config' is only in mc-files/legacy/ (restored originals of clusters not yet onboarded), which Wingman does not offer` |
| `{"name": "nm-conf-prod-x-site1-dell"}` in a flavor | `'nm-conf-prod-x-site1-dell' is one cluster's network config name; write {name: nm-conf, hardware: dell} instead` |
| the same at create of another cluster | `... is another cluster's network config name; write {name: nm-conf, hardware: dell} instead` |
| `{"name": "nm-conf", "hardware": "l4"}` where an `l4` and a `cisco-l4` type exist and the cluster is `prod-cisco` | `the l4 network config would be named 'nm-conf-prod-cisco-l4', which the CI reads as hardware 'cisco-l4'` |
| an entry equal to an earlier one in the same nodepool | `the same entry as nodepools[i].configs[k]` |
| `"x"`, `{}`, `{"name": "x", "ref": 1}`, `{"hardware": 3}` | `must be {name: <config>} or {name: nm-conf, hardware: <type>}`, `name is required`, `unknown keys ref (an entry has name and hardware)`, `hardware must be a string` |

At create, writing this cluster's own expanded name by hand
(`{"name": "nm-conf-prod-falcon-site1-dell"}`) is accepted; prefer the
structured form. Example 422 from `POST /clusters` (`instance` and
`request_id` left out):

```json
{
  "type": "/problems/validation-error",
  "title": "Validation Error",
  "status": 422,
  "detail": "the cluster's inputs are not acceptable",
  "code": "VALIDATION_ERROR",
  "details": {
    "problems": [
      "nodepools[0].configs[0]: nm-conf needs a hardware type, one of cisco, dell, dell-data",
      "nodepools[1].configs[0]: no machine config 'nope' in mc-files/"
    ]
  }
}
```

## 4. Changed: owners are numbers

`owner_merkaz`, `owner_anaf`, `owner_mador` must each be a **string** of 1
to 10 ASCII digits (`"1234"`, `"0042"`). A JSON number, an empty string,
spaces or other characters are refused, on create and preview (whatever the
merged inputs end up with) and in a flavor's values (preset or locked):

```
owner_anaf: must be a number of 1 to 10 digits, sent as a string like "1234" (got '5x')
```

Use a text input with `inputMode="numeric"` and send the text. An owner the
request does not set at all is reported by the template as missing, as
before (`the cluster template reads an undefined input`).

## 5. Changed: the spec document (`GET /specs`, `GET /specs/{name}`, `POST`, `PUT`)

```json
{
  "apiVersion": "wingman.io/v1",
  "kind": "ClusterSpec",
  "metadata": {"name": "agent-dell", "description": "...", "version": "1.0.0", "labels": {"platform": "agent"}},
  "spec": {
    "day1": {
      "variables": [],
      "structure": {"nodepools": [{"configs": [{}, {}, {}]}]},
      "locked_paths": ["nodepools[0].configs"],
      "template": "{#- ... the shared template ... -#}",
      "values": {
        "nodepools": [
          {
            "replicas": 2,
            "configs": [
              {"name": "nm-conf", "hardware": "dell"},
              {"name": "workers-chrony-configuration"},
              {"name": "nic-ring-buffer"}
            ]
          }
        ]
      }
    },
    "day2": {"addons": []}
  },
  "load_error": null,
  "load_problems": [],
  "last_commit_id": "…",
  "warnings": []
}
```

(`agent-dell` is a new fixture flavor; the spec list is now
`agent-dell, agent-single, agent-standard`.)

- **`spec.day1.locked_paths`** replaces `immutable_paths` in responses.
  Requests may still send `immutable_paths` (it is read as `locked_paths`);
  sending both is a 422 (`details.errors[0].msg` contains `immutable_paths
  is the old name of locked_paths`). The stored file gets `locked_paths`.
  Switch the editor to `locked_paths`.
- **`spec.day1.values`** holds both presets and locked values. A path in
  `locked_paths` is locked; every other value is a preset.
- **`warnings`** (new, list items and detail): the flavor rules a stored
  spec breaks; it still loads, but saving it unchanged would be refused.
  They cover values that could break the file, owners, and locks. (Config
  names are checked at save and create, not listed here.) For a broken
  spec (`load_error` set) it is `[]`.

## 6. New: locks are enforced

**What can be locked**, and nothing else:

| Template input | Cluster-file key (for drift, stage 2) |
|---|---|
| `owner_merkaz`, `owner_anaf`, `owner_mador` | `owner.merkaz`, `owner.anaf`, `owner.mador` |
| `platform` | `platform` |
| `nodepools[<i>].replicas` | `nodepool[<i>].replicas` |
| `nodepools[<i>].configs` (the whole list) | `nodepool[<i>].configs` |
| `nodepools[<i>].node_labels` (the whole map) | `nodepool[<i>].nodeLabels` |

Not lockable: `cluster_name`, `site`, `mce`, `openshift_release_version`
(and `site_name`, `mce_name`), any other nodepool field
(`infra_env`, `nodepool_name`, `tuning_config`), part of a list
(`nodepools[0].configs[1]`) or a whole nodepool. A flavor that sets
`openshift_release_version` in `values` keeps it as the create form's
default (a preset), as today.

**At flavor save** (`POST /specs`, `PUT /specs/{name}`), 422
`spec '<name>' cannot be saved` with one problem per broken lock:

```
locked_paths: 'nodepools.0.configs' is not a template-input path like owner_merkaz or nodepools[0].configs (unexpected '.' at character 10)
locked_paths: openshift_release_version is set for each cluster at create (its name, site, MCE and OpenShift version) and cannot be locked
locked_paths: nodepools[0].infra_env cannot be locked; lockable inputs are owner_merkaz, owner_anaf, owner_mador, platform, nodepools[<i>].replicas, nodepools[<i>].configs, nodepools[<i>].node_labels
locked_paths: platform is listed twice
locked_paths: owner_mador is locked but spec.day1.values sets no value for it
locked_paths: 101 paths; the limit is 100
```

So the editor must send the locked field's value in `values` (today's
"new spec" page sends locks with empty leaves; that is now refused). The
same save also checks `values` with the template's input rules, owners
(§4) and configs (§3); all problems come in one response.

**At create and preview:**

- Show a locked field read-only with the flavor's value. Sending it is
  fine, leaving it out is fine (day1 puts the flavor's value in place, also
  when the request's `nodepools` list replaces the flavor's).
- Sending a different value is a 422:

  ```
  nodepools[0].configs: locked by flavor agent-dell to [{"name": "nm-conf", "hardware": "dell"}, {"name": "workers-chrony-configuration"}, {"name": "nic-ring-buffer"}]; the request sends [{"name": "nic-ring-buffer"}]
  owner_anaf: locked by flavor agent-two to "56"; the request sends "99"
  ```

  Values compare as JSON (order matters in lists; `{"hardware": null}` is
  not the same as no `hardware` key), except that a whole number and its
  digits as a string are equal (`3` and `"3"`); `true` is not `1`.
- A lock on a nodepool the request does not have is a 422; send at least
  as many nodepools as the flavor locks:

  ```
  nodepools[1].replicas: the flavor locks it to 3, but the cluster has no nodepools[1]
  ```

- Presets stay overridable: send any value.
- A stored lock that breaks the save rules (listed in `warnings`) is not
  enforced.

Locks are by position in this stage: `nodepools[0]` is the first nodepool
of the request. Use `structure` (unchanged) for the number of nodepools the
form starts with.

## 7. Unchanged, for the record

- `GET /specs/template/schema`: a `configs` item still lists only `name`
  (the template reads `config.name`); `hardware` is Wingman's, not the
  template's. Build the config picker from §1, not from the schema.
- `GET /clusters/{name}` `metadata.immutable_paths` is still always `[]`
  (the cluster detail's legacy field; it does not come from the flavor).
- Cluster edit (`PATCH /clusters/{name}`, the raw YAML editor) does not
  check config names yet; it writes the file's own `nm-conf-<...>` names.
- Drift is still add-on drift only (ADR-0016, ADR-0025). Drift on locked
  values, importing existing clusters and the sync MR are stage 2.

## 8. Fixtures the live suite can use

- `mc-files/` in `gitops-day1/platform-config` (§1's response).
- `wingman/cluster-specs/nodepool-defaults.yaml` (the team's three).
- `wingman/cluster-specs/specs/agent-dell.yaml`: locks
  `nodepools[0].configs`, presets `nodepools[0].replicas: 2`.
- `agent-single` and `agent-standard` still use `immutable_paths: []`, so
  they also prove the alias.
- The live create in `e2e/tests/live-day1-flows.spec.ts` now types
  `workers-chrony-configuration` (it typed a name that does not exist).
