# Tuning profiles: the day1 API the web builds on (2026-11-15)

ADR-0061. Tuning profiles (`Tuned`, `PerformanceProfile`) come from
`tuning/` in the day1 repo; a nodepool names them in `tuning_config`; a
flavor can lock them for every nodepool. Paths are relative to the day1
service. Errors are RFC 9457 problems as before: each broken rule is one
string in `details.problems` of a 422 `VALIDATION_ERROR`, starting with the
path it is about (`docs/notes/2026-11-08-flavors-v2-api-changes.md` §2).

## 1. New: `GET /api/day1/tuning-profiles` (any session)

```json
{
  "folder": "tuning",
  "found": true,
  "profiles": [
    {
      "name": "performance-pinned",
      "kind": "PerformanceProfile",
      "summary": null,
      "path": "tuning/performance-pinned.yaml",
      "clusters": [],
      "requires_performance_profile": null
    },
    {
      "name": "tuned-network-latency",
      "kind": "Tuned",
      "summary": "Lower network latency on worker nodes",
      "path": "tuning/tuned-network-latency.yaml",
      "clusters": ["prod-lark-site1"],
      "requires_performance_profile": null
    },
    {
      "name": "tuned-pinned-irq",
      "kind": "Tuned",
      "summary": "Keep interrupts off the pinned CPUs",
      "path": "tuning/tuned-pinned-irq.yaml",
      "clusters": [],
      "requires_performance_profile": "performance-pinned"
    },
    {
      "name": "tuned-sysctl-baseline",
      "kind": "Tuned",
      "summary": "Raise the kernel's file and connection limits",
      "path": "tuning/tuned-sysctl-baseline.yaml",
      "clusters": [],
      "requires_performance_profile": null
    }
  ],
  "problems": [
    {
      "path": "tuning/tuned-misnamed.yaml",
      "detail": "metadata.name is tuned-renamed; it must be the file's name, tuned-misnamed"
    }
  ]
}
```

(That is the response on the fixtures.)

- `profiles` are the **shared** profiles (`tuning/<name>.yaml`), sorted by
  name: the only names a flavor or a create may use. `kind` is `Tuned` or
  `PerformanceProfile`. `summary` is a Tuned's `[main]` `summary=` (first
  profile entry), else `null`. `clusters` are the cluster names (the
  chart's, ADR-0015) that have a variant `tuning/<cluster>/<name>.yaml`.
  `requires_performance_profile` is, for a Tuned whose `[main]` has
  `include=openshift-node-performance-<pp>` (in any profile entry's
  `data`), that `<pp>`; else `null`. The web warns about a nodepool that
  names the Tuned without `<pp>` and offers "Add `<pp>`"; day1 never
  refuses it.
- `problems` are files that are not offered: not `.yaml`, nested deeper
  than one folder, a name that is not a DNS-1123 label of at most 63
  characters, not exactly one YAML mapping, another `apiVersion`/`kind`,
  `metadata.name` not the file's name. `*.md` and dot files are skipped
  silently.
- `found: false`: the day1 repo has no `tuning/`; `profiles` and `problems`
  are empty. The picker is then empty and says why.
- A failed GitLab read fails the request (ADR-0004).

## 2. Changed: a nodepool's `tuning_config` input

In a flavor's `spec.day1.values.nodepools[i]` and in a create's
`variables.nodepools[i]`: **a list of profile names**, in the order
chosen (`["tuned-network-latency", "performance-pinned"]`). A single name
as a string is still accepted; `[]`, `""` or no key means none. At most 16
per nodepool.

The template field the schema reports for it is now
`{"name": "tuning_config", "type": "list", "required": false, "default": []}`
(the fixture template; the web treats `tuning_config` by name, whatever type
a team's template reports).

The rendered cluster file gets `tuningConfig: <name>` for one,
`tuningConfig: ["a", "b"]` for several, nothing for none. `tuningConfigmap`
is never written (ADR-0061; neither provisioner sends it).

## 3. Validation (422 problems)

- **Flavor save** (`POST /specs`, `PUT /specs/{name}`): each name must be a
  shared profile.
  - `nodepools[1].tuning_config: must be a list of tuning profile names`
  - `nodepools[0].tuning_config[0]: tuned-network-latncy is not a tuning profile in tuning/ (did you mean tuned-network-latency?)`
  - `nodepools[0].tuning_config[1]: tuned-x is a variant for cluster prod-lark-site1 only; a flavor names shared profiles from tuning/`
  - `nodepools[0].tuning_config[2]: tuned-network-latency is listed twice`
  - `nodepools[0].tuning_config: 17 profiles; the limit is 16`
  - `nodepools[0].tuning_config: at most one PerformanceProfile per nodepool (HyperShift); it names performance-a, performance-b`
    (any number of Tuned is fine; the web replaces a pool's PerformanceProfile when another is picked)
- **Preview and create** (`POST /clusters/preview`, `POST /clusters`, both
  provisioners): the same checks on the merged inputs (flavor presets,
  locks, the request), same messages.
- **Edit** (`PATCH /clusters/{name}`, and the sync below): only names the
  edit adds to the file are checked; each must be a shared profile, a
  variant for this cluster or an entry of the file's `tuningConfigmap`:
  - `nodepool[0].tuningConfig: tuned-x is not in tuning/, in tuning/prod-lark-site1/ or in this file's tuningConfigmap`
  - `nodepool[0].tuningConfig: must be a tuning profile name or a list of names`
  - `nodepool[0].tuningConfig: at most one PerformanceProfile per nodepool (HyperShift); it names ...`
    (only for a nodepool whose `tuningConfig` the edit changes; a name's kind
    is its variant's, else the shared file's, else the file's `tuningConfigmap` entry's)
  - `tuningConfigmap is owned by automation; an edit must leave it as it is`

## 4. New: the tuning rule `nodepools[*].tuning_config`

Listed in `spec.day1.locked_paths` like `nodepools[*].configs`. Every
nodepool of a cluster has exactly these profiles, **compared as a set**.

- Save: every flavor nodepool must set `tuning_config`, with at least one
  name, and all must name the same profiles:
  - `locked_paths: nodepools[*].tuning_config locks every nodepool's tuning profiles, but spec.day1.values.nodepools[1] sets none`
  - `locked_paths: nodepools[*].tuning_config locks every nodepool to the same tuning profiles, but nodepools[1].tuning_config names other profiles than nodepools[0].tuning_config`
  - `nodepools[0].tuning_config` is not lockable (no positional tuning lock).
- Create: a nodepool that sends `tuning_config` with other profiles is
  refused: `nodepools[1].tuning_config: locked by flavor F: every nodepool has ["a"], in any order; the request sends ["b"]`.
  A nodepool that sends none gets the rule's names. The web shows the
  rule's names read-only on every nodepool and sends them.

## 5. Changed: drift (`GET /clusters/{name}/drift`, import, rollout)

A nodepool whose `tuningConfig` names other profiles than the rule is a
`value_drift` item:

```json
{
  "path": "nodepools[*].tuning_config",
  "file_key": "nodepool[1].tuningConfig",
  "nodepool": {"index": 1, "name": "prod-lark-site1-dell-r760-site1-64c-512gb-20tb"},
  "flavor_value": "tuned-network-latency",
  "cluster_value": null,
  "in_file": false,
  "added": ["tuned-network-latency"],
  "removed": [],
  "needs_decision": null,
  "needs_hardware": false,
  "reboots": true
}
```

`flavor_value` is in the file's form (a string for one name, a list for
several); `added`/`removed` are names. `reboots` is true for tuning too.

## 6. Changed: sync (`POST /clusters/{name}/sync/preview`, `POST /clusters/{name}/sync`)

- The sync writes only `tuningConfig` names (the flavor's order), never
  `tuningConfigmap`; the CI injects the manifests on the MR branch.
- `rebooting[]` now includes nodepools whose tuning changes. Each item has
  two new booleans: `configs` (its machine configs change) and `tuning`
  (its tuning profiles change). A pool with both appears once.
- A name the sync would add that does not resolve for this cluster (shared,
  variant or the file's `tuningConfigmap`) is a `problems` entry, so
  `can_sync` is false.
- `confirm_removals` stays about configs only; removing a profile needs no
  confirmation field. The web's confirm dialog names the pools whose tuning
  changes: "their nodes may reboot".
- The MR description lists the tuning changes per nodepool and says the
  nodes may reboot.

## 7. Unchanged

`GET /machine-configs`, the configs rule, hardware choices, and the
approve page's shape: its `rolls_nodes` also lists clusters whose
nodepools' tuning changes, with no new field.
