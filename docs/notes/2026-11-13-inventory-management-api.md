# Inventory Management: the API the web reads (2026-11-13)

The sidebar page **Inventory Management** (`/inventory`, ADR-0057):
everyone signed in reads it, only admins add servers. It answers three questions without opening server-scan, Temporal
or the orchestrator:

1. How many Agents does each MCE have available, by InfraEnv pool and
   hardware, as server-scan reports them?
2. Install servers into a pool myself: let the pool pick N, or name them.
3. What are the add-server runs doing, herzi's included?

Every route is under `/api/day1/inventory`. The reads (§1, §2, §4) take
`CurrentUser`; installing (§5) takes `AdminUser`, and the page shows no
Install servers to a viewer. Errors are RFC 9457 problems (ADR-0004). The browser never calls server-scan,
herzi or the orchestrator. `<mce>` is a day1 MCE folder
(`ocp4-<env>-mce-<site>-<x>`), `<infra_env>` an InfraEnv name (a DNS
label). Since 3.19.0 day1 does not check the InfraEnv against the MCE's
list: the workflow's first phase (`validating-infraenv`) does, as on the
orchestrator's own "Install servers" form, so nothing here needs live
status (ADR-0057's amendment). Since 3.38.0 a pool's free servers are
split into **Ready** and **Needs fix**, with a **Total**, and a named
install may waive the workflow's health checks (`allow_unhealthy`, §5)
after the dialog's confirmation (ADR-0057's 3.38.0 amendment).

## 0. Where the numbers come from

| Number | Source | Rule |
|---|---|---|
| An MCE's servers | server-scan `GET /api/v1/servers/rows`, through day1's one cached `ServerInventory` (the Nodes tab and placement read the same cache entry) | rows whose `mce_name` is the MCE folder |
| In clusters | the same rows | `openshift_state` `INSTALLED` |
| **Available** (Agents in the MCE's inventory, in no cluster) | the same rows | `openshift_state` `INSTALLED_TO_INVENTORY` |
| Usable | the same rows | available, out of maintenance, reachable, not stale, neither `CRITICAL` nor `UNKNOWN`, not contested: placement's rule (`mce_capacity.usable`), shared |
| The pools (InfraEnvs) | the MCE's InfraEnv list with each one's `spec.agentLabels` (hub, cached as for the create form); without it (live status off, or the hub unreadable), the InfraEnvs the MCE's day1 cluster files name (`nodepool[].infraEnvName`), with no labels | `infra_envs_from` says which: `mce` or `day1` |
| A pool's server names (since 3.54.0) | the InfraEnv's agentLabels | `server_prefix` `ocp-<redbull.io/flavor>-<redbull.io/size>-<redbull.io/site>-`: what the add-server workflow's pool draw asks server-scan for (team-redbull/workflows `29ef001`, the naming convention of 2026-11-22). `null` when the labels were not read, or when one is missing or not one lowercase word (`label_problems`, in the workflow's words: it refuses a pool draw into such an InfraEnv). The zone is in no server's name and the draw does not filter by it |
| A server's InfraEnv | the pools above | the one pool whose `server_prefix` starts the server's name; when none or several do (one flavor and size in several zones), the InfraEnv of a live lock on this MCE; else none (`infra_env: null`, the page's "No single InfraEnv") |
| Hardware | the rows | `vendor` and `model` |
| **Ready** (since 3.38.0; was `drawable`, the page's Free) | the rows | `AVAILABLE` servers the pool's `server_prefix` names (`null` when it has none), unlocked, out of maintenance, not contested, `HEALTHY` and reachable: what a pool draw could pick today, by the rule the workflow asks server-scan with (`/servers/available?health=HEALTHY`). server-scan's view; the workflow decides (it also checks the network category, two link-up NICs and a live recheck, which the rows do not carry) |
| **Needs fix** | the rows | the same, offered (unlocked, out of maintenance, not contested), but server-scan's health is not `HEALTHY` or the BMC is unreachable: a pool draw never picks it; a named install takes it only with `allow_unhealthy` (§5) |
| **Total** | the counts above | available + ready + needs fix: what the pool reaches once every free server is fixed and installed. On the MCE, each free server named for any of its pools is counted once. Locked, in-maintenance and contested servers are not counted |

An MCE that no row names is **unknown** (`known: false`), never zero.
server-scan unreadable: the route answers 502. The MCE's own InfraEnv list
unreadable (or live status off): its pools are the InfraEnvs its day1
cluster files name (`infra_envs_from: "day1"`), with no `server_prefix`
(only a held lock places a server in one, and none counts ready or needing a
fix), and `infra_envs_error` says why its own list is unknown. When the
MCE's list is read, it is the only source (no union).

**Used Agents (since 3.55.0, ADR-0057's amendment).** A free Agent that
carries a used-Agent key (herzi's `redbull.io/ever-installed`, or
`DAY1_EXCLUDED_AGENT_LABELS`'s keys when set: `used_labels`) is herzi's to
remove from the MCE, and no NodePool that excludes the label takes it. Day1
reads only those from the hub, one label-selected list per key
(`<key>,!agentMachineRef`, kept 30 s), joins each to its server-scan row as
the nodes view does, and takes that row out of the available ones: it is
counted in its InfraEnv label's pool (`pools[].used`, its servers by name)
and on the MCE (`used`), never in a total. Without live status `used` is
`null`; a failed read is `used_error`. `unguarded` lists the MCE's cluster
files' agent nodepools whose `excludeAgentLabels` lacks a key (by NodePool
name, with `missing`, and `replace` for an `upgradeType: Replace` one, which
the cluster's merge request leaves out): herzi removes no used Agent of
their InfraEnvs until each excludes it (herzi's plan, rule 6).

**Not shown in the alpha: herzi's InfraEnv annotations**
(`herzi.redbull.io/blocked-until`, `herzi.redbull.io/state`). Day1's MCE
read lists InfraEnv names and `spec.agentLabels`; reading their annotations
is a new hub read and a new grant. herzi's numbers and decisions (demand, target, need, dry
run) are in its metrics and logs only, which Wingman cannot read.

## 1. `GET /api/day1/inventory`: every MCE's pools

```json
{
  "mces": [
    {
      "site": "site1",
      "mce": "ocp4-prod-mce-site1-a",
      "known": true,
      "servers": 19,
      "in_clusters": 11,
      "available": 6,
      "usable": 6,
      "pools": [
        {
          "infra_env": "dell-r760-site1-64c-512gb-20tb",
          "available": 0,
          "usable": 0,
          "hardware": [],
          "ready": null,
          "needs_fix": null,
          "total": 0,
          "server_prefix": null,
          "label_problems": ["redbull.io/flavor is missing", "redbull.io/size is missing", "redbull.io/site is missing"],
          "used": []
        },
        {
          "infra_env": "r650-mtl-az1",
          "available": 2,
          "usable": 2,
          "hardware": [{"vendor": "dell", "model": "PowerEdge R650", "available": 2, "usable": 2}],
          "ready": 1,
          "needs_fix": 1,
          "total": 4,
          "server_prefix": "ocp-r650-mtl-site1-",
          "label_problems": [],
          "used": ["ocp-r650-mtl-site1-dlfake0901"]
        },
        {
          "infra_env": null,
          "available": 1,
          "usable": 1,
          "hardware": [{"vendor": "dell", "model": "PowerEdge R760", "available": 1, "usable": 1}],
          "ready": null,
          "needs_fix": null,
          "total": 1,
          "server_prefix": null,
          "label_problems": [],
          "used": []
        }
      ],
      "infra_envs": ["dell-r760-site1-64c-512gb-20tb", "r650-mtl-az1"],
      "infra_envs_error": null,
      "infra_envs_from": "mce",
      "ready": 1,
      "needs_fix": 1,
      "total": 8,
      "used": 1,
      "used_error": null,
      "unguarded": [
        {
          "cluster": "ocp4-prod-heron-site1",
          "nodepool": "prod-heron-site1-r650",
          "infra_envs": ["r650-mtl-az1"],
          "missing": ["redbull.io/ever-installed"],
          "replace": false
        }
      ]
    }
  ],
  "add_servers": {"available": true, "detail": null},
  "runs": {"available": true, "detail": null},
  "used_labels": {"keys": ["redbull.io/ever-installed"], "source": "herzi"}
}
```

- `mces`: every MCE folder of the day1 repo (read-only, convention 14), by
  site then name.
- `pools`: one per InfraEnv on the MCE, even with nothing available (so it
  can be filled), then `infra_env: null` for available servers matched to
  none; sorted by name, `null` last. `hardware` sorted by vendor, model.
- `infra_envs_from`: `mce` (the MCE's own list) or `day1` (the InfraEnvs its
  day1 cluster files name, while its own list is unknown; `infra_envs_error`
  says why).
- `server_prefix` and `label_problems` (§0, since 3.54.0): how the pool's
  servers are named, or why not. A pool with `label_problems` is one the
  workflow refuses a pool draw into; the page says so.
- `ready`, `needs_fix` (§0; `null` on the `infra_env: null` row and on a pool
  with no `server_prefix`) and `total`
  (always a number) per pool, and per MCE (a free server named for two of
  its pools counted once). Since 3.38.0; `drawable` is gone (it was `ready`).
- `add_servers.available` is `false`, with `detail` (one line, the web's
  tooltip on its disabled Install servers), when `DAY1_ADD_SERVERS` is off
  or there is no orchestrator. Live status is not needed (3.19.0).
- `runs.available` is `false`, with `detail`, without the orchestrator.
- `used`, `used_error`, `pools[].used`, `unguarded` and `used_labels` (§0,
  since 3.55.0): herzi's used Agents, apart from `available` and every
  `total`, and the agent nodepools that do not exclude the used-Agent keys.
  `used_labels.source` is `setting` (`DAY1_EXCLUDED_AGENT_LABELS`) or `herzi`
  (its label, the setting empty). The page raises `unguarded` once it
  matters: herzi has used Agents on the MCE, or the source is `setting`.

| Status | `code` | When |
|---|---|---|
| 501 | `FEATURE_DISABLED` | server-scan is not configured (`SERVER_SCAN_URL`) |
| 502 | `DEPENDENCY_UNAVAILABLE` | server-scan could not be read |

## 2. `GET /api/day1/inventory/mces/{mce}/infra-envs/{infra_env}/candidates`

A pool's servers, for the named-install picker: the `AVAILABLE` servers its
`server_prefix` names (§0), or, when it has none (labels unread, or lacking),
every `AVAILABLE` server, not filtered by name: the workflow does not match
a named server to the pool, and checks the server itself. Only what picking
needs. Not a fleet view: a
server's full record belongs to the future Server Scan area.

```json
{
  "mce": "ocp4-prod-mce-site1-a",
  "infra_env": "r650-mtl-az1",
  "server_prefix": "ocp-r650-mtl-site1-",
  "label_problems": [],
  "candidates": [
    {
      "id": "srv_…",
      "name": "ocp-r650-mtl-site1-<serial>",
      "vendor": "dell",
      "model": "PowerEdge R650",
      "health": "HEALTHY",
      "lock": null,
      "offered": true,
      "why_not": null,
      "ready": true,
      "health_problems": []
    },
    {
      "id": "srv_…",
      "name": "ocp-r650-mtl-site1-<serial>",
      "vendor": "dell",
      "model": "PowerEdge R650",
      "health": "CRITICAL",
      "lock": null,
      "offered": true,
      "why_not": null,
      "ready": false,
      "health_problems": ["health CRITICAL", "BMC unreachable"]
    },
    {
      "id": "srv_…",
      "name": "ocp-r650-mtl-site1-<serial>",
      "vendor": "dell",
      "model": "PowerEdge R650",
      "health": "HEALTHY",
      "lock": {"holder": "add-server-to-mce", "mce": "ocp4-prod-mce-site1-b", "infra_env": "r650-mtl-az2", "expires_at": "2026-11-13T18:00:00Z"},
      "offered": false,
      "why_not": "locked by add-server-to-mce until 2026-11-13T18:00:00+00:00",
      "ready": false,
      "health_problems": []
    }
  ]
}
```

- `lock` is `{holder, mce, infra_env, expires_at}` while server-scan's
  reservation is held (§3), else `null`.
- `why_not`, the first that applies: locked (by anyone), in maintenance,
  contested. The workflow fails a named run for each of these (§3), so
  Wingman does not offer them: its safety refusals, which nothing waives.
- `ready` (since 3.38.0): offered, `HEALTHY` and reachable, what a pool draw
  could pick. Offered and not ready: it **needs a fix**, and
  `health_problems` says why from the row (`health <tier>`,
  `BMC unreachable`); a named install takes it only with `allow_unhealthy`
  (§5), and fails in the workflow without it.
- The ready ones first, then those that need a fix, then the ones not
  offered; by name in each.

| Status | `code` | When |
|---|---|---|
| 404 | `NOT_FOUND` | No such MCE in the day1 repo |
| 422 | `VALIDATION_ERROR` | The InfraEnv is not a DNS label (`details.problems` says why) |
| 501 | `FEATURE_DISABLED` | server-scan not configured |
| 502 | `DEPENDENCY_UNAVAILABLE` | server-scan could not be read |

The MCE's InfraEnv list is read (cached) for the pool's labels; an
InfraEnv the list lacks, or no list, lists every free server, and an install
into an InfraEnv the MCE lacks fails in the workflow's `validating-infraenv`.

## 3. server-scan's lock, and what the workflow does with it

Read 2026-11-13 from team-redbull's public repositories.

- **The lock is server-scan's `reservation`** ("the install lock"). On
  `/servers/rows` it is `reservation{held, holder, mce_cluster, infra_env,
  expires_at}`; `held` is computed when read (no expiry, or the expiry
  ahead), so an expired lock reads `held: false`.
- **Who takes it:** the add-server-to-mce workflow (holder
  `add-server-to-mce`, or `install-server` for a run started before the
  rename): 2 h while installing, 24 h on success; the uninstall-server-from-hc
  workflow (holder `uninstall-server-from-hc`) for runs recorded before
  2026-11-19 only (a new run takes no lock and ends at a free Agent); and a
  person only through
  server-scan's admin API (`POST/DELETE /servers/{id}/reservation`; its UI
  has no such button). **herzi never calls server-scan**: it starts pool
  draws with `count` and treats a reserved server as a shortage.
- **A pool draw** asks server-scan for an `AVAILABLE`, healthy, reachable,
  unlocked server out of maintenance named `^ocp-<flavor>-<size>-<site>-`,
  from the InfraEnv's agentLabels (since team-redbull/workflows `29ef001`,
  2026-11-22; a worker predating the labels draws by the InfraEnv name's first
  three words). An InfraEnv missing one of the three labels fails the run
  (`InfraEnvAgentLabelsError`), nothing allocated. No zone filter.
- **A named install** is refused inside the run, as a FAILED run and never
  a 4xx at the start: a server that is not `AVAILABLE`, is contested or in
  maintenance (`ServerNotAvailableError`), or locked by another run
  (`ServerReservedError`). The workflow does not check a named server's
  name against the InfraEnv, and neither does day1 (since 3.54.0): the
  picker lists the servers the pool's labels name, when it knows them.
- **Health** (read 2026-11-16, team-redbull/workflows `health_waiver.py`):
  a named server `/servers/available` refuses is read once more and its
  reasons sorted. Safety (unknown to server-scan, claimed, contested, in
  maintenance, another run's lock) fails the run whatever was asked. Health
  (its tier not `HEALTHY`, its network category not `HEALTHY`, the BMC
  unreachable, the live recheck, a bond member whose link is not up) fails
  it too, unless the start asked for `allow_unhealthy`: then each is waived
  and recorded in the run's `allowed_unhealthy`.

## 4. `GET /api/day1/inventory/runs`: the add-server runs

```json
{
  "runs": [
    {
      "workflow_id": "add-server-to-mce-ocp4-prod-mce-site1-a_dell-r650-site1-96c-768gb_3",
      "status": "running",
      "started_at": "2026-11-13T12:00:00Z",
      "closed_at": null,
      "mce": "ocp4-prod-mce-site1-a",
      "infra_env": "dell-r650-site1-96c-768gb",
      "slot": 3,
      "server_name": "ocp-dell-r650-site1-96c-768gb-<serial>",
      "origin": "pool",
      "phase": "waiting-for-agent",
      "error": null,
      "health_checks_waived": []
    }
  ]
}
```

- The orchestrator's `GET /workflows/runs?workflow_type=AddServerToMceWorkflow&limit=200`,
  newest first; the 50 newest are shown, and the 20 newest are each read
  (`GET /workflows/runs/{id}`) for `phase`, `server_name` and `error`.
  Both reads are kept 10 s; a start drops them. A pool's slots are reused,
  so several runs may share an id, and a read by id answers for the newest
  of them: only the newest entry of an id gets `phase`, `server_name` and
  `error`; an older one keeps the list's `status`.
- Run ids: a pool draw is `add-server-to-mce-<mce>_<infraEnv>_<slot>` (slot
  1-100), a named install `add-server-to-mce-<mce>_<server, lowercased>`;
  the orchestrator adds `ocp4-` to the MCE. An id that is neither is shown
  with `mce`, `infra_env` and `slot` null.
- **`origin`**: `named` is a person (herzi only sends `count`); `pool` is
  "herzi or a person". The orchestrator records no `requested_by`, so a
  pool draw's author cannot be told. Never guessed.
- `phase` is the workflow's own word, passed through; Wingman keeps no list.
- **`health_checks_waived`** (since 3.38.0): the run's `allowed_unhealthy`
  (its progress's, else its result's), each `check: observed`
  (`server-scan-health: overall CRITICAL (raid=CRITICAL)`); empty for a run
  that waived nothing, and for an older entry of a reused id.
- **`server_id`** is gone since the Server Scan area was removed (ADR-0066):
  it was server-scan's id for `server_name`, only for the link to the
  server's page in that area. A run names its server as the workflow does.

| Status | `code` | When |
|---|---|---|
| 501 | `FEATURE_DISABLED` | No orchestrator (`WORKFLOWS_API_URL`) |
| 502 | `DEPENDENCY_UNAVAILABLE` | The orchestrator could not be read |

## 5. `POST /api/day1/inventory/mces/{mce}/infra-envs/{infra_env}/add-servers`

Body: `{"count": N}` (1-20, let the pool pick) or `{"server_names": [..]}`
(1-20 distinct names from §2's offered candidates); exactly one. With
`server_names`, `"allow_unhealthy": true` (since 3.38.0) waives the
workflow's health checks for every named server, never its safety
refusals; the page sends it only after the person confirms the servers
that need a fix. On a pool draw it is refused (`422`) before the workflow
is called, as the orchestrator refuses it.

Day1 checks that the MCE is a day1 MCE, the InfraEnv is a DNS label and
every named server is offered (§2); it does not read the MCE (since 3.19.0:
the workflow's `validating-infraenv` checks the MCE has the InfraEnv, a
FAILED run naming it otherwise, as on the orchestrator's own form). Then it
starts
`POST <orchestrator>/workflows/server-lifecycle/add-server-to-mce` with
`{infra_env, mce_cluster: <mce>, namespace?: MCE_INFRAENV_NAMESPACE,
count | server_names, allow_unhealthy?}` (`allow_unhealthy` only when
true), logs `servers_add_started` (who, MCE, InfraEnv, count or names,
`allow_unhealthy=true` when asked, at warning and "with health checks
waived", workflow ids), and answers:

```json
{
  "started": 2,
  "already_running": 0,
  "failed": 0,
  "runs": [
    {"workflow_id": "add-server-to-mce-…_1", "status": "started", "server_name": null, "slot": 1, "error": null}
  ]
}
```

with `202`. **Not retry-safe**: sending it again installs more servers. A
start is never retried (ADR-0006).

| Status | `code` | When |
|---|---|---|
| 403 | `FORBIDDEN` | Not an admin |
| 404 | `NOT_FOUND` | No such MCE in the day1 repo |
| 409 | `ADD_SERVER_ALREADY_RUNNING` | The orchestrator's 409: a named server already installing, or every slot of the pool busy |
| 422 | `VALIDATION_ERROR` | Neither or both of `count` and `server_names`; `allow_unhealthy` without `server_names`; the InfraEnv not a DNS label; a named server not offered (each in `details.problems`); the orchestrator's 422 |
| 501 | `FEATURE_DISABLED` | `DAY1_ADD_SERVERS` off, or no orchestrator |
| 502 | `DEPENDENCY_UNAVAILABLE` | Nothing was started: the orchestrator was not reached, or refused |
| 504 | `AMBIGUOUS_WRITE` | Sent, no answer: some may have started. Look at the runs before sending again |

## 6. Settings (day1)

| Variable | Default | Meaning |
|---|---|---|
| `DAY1_ADD_SERVERS` | `false` | Offers installing servers. Needs `WORKFLOWS_API_URL` (refused at start otherwise, ADR-0009); not live status (3.19.0). Off, admins see Install servers disabled with the reason |
| `SERVER_SCAN_URL` | (exists) | Inventory's counts; empty: the page answers 501 |
| `WORKFLOWS_API_URL` | (exists) | The runs; empty: no runs, no install |
| `MCE_INFRAENV_NAMESPACE` | (exists) | Sent as `namespace`, and where InfraEnvs are listed |

Chart: `day1.addServers.enabled`. No new grant: the MCE token already lists
InfraEnvs (ADR-0040).

`DAY1_FAKE_FLEET=true` (development) fakes the add-server runs too: they walk
a few sample phases on the fake fleet, and a fake herzi starts a pool draw
now and then on one short pool (`dev/fleet-fixtures/inventory.yaml`). A
named run of a server that needs a fix fails unless the start asked for
`allow_unhealthy`, and then records the waived checks, as the workflow does.

## 7. Metrics

`workflows` operation `start_add_server` (outcomes `ok`, `conflict`,
`rejected`, `unavailable`, `ambiguous`), with or without `allow_unhealthy`;
the runs reuse `list_runs` and `get_run`. No MCE, InfraEnv or server in a
label (ADR-0010).

## 8. Left for later

- **The shared table.** The runs use `apps/web/components/data-table/`
  (ADR-0047), without sorting, filters or a column picker; a pool's servers
  are a short list in the picker. Filters (by MCE, pool, origin, status)
  come when the runs outgrow one screen.
- **A link from each server to its record** in the future Server Scan area,
  once it exists.
- herzi's annotations (§0), its Lease ("is herzi running here?") and its
  numbers.
- `remove-server-from-mce`, the way back for an over-filled pool.
