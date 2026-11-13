# Inventory Management: the API the web reads (2026-11-13)

The sidebar page **Inventory Management** (`/inventory`, ADR-0057):
everyone signed in reads it, only admins add servers. It answers three questions without opening server-scan, Temporal
or the orchestrator:

1. How many Agents does each MCE have available, by InfraEnv pool and
   hardware, as server-scan reports them?
2. Add servers to a pool myself: let the pool pick N, or name them.
3. What are the add-server runs doing, herzi's included?

Every route is under `/api/day1/inventory`. The reads (§1, §2, §4) take
`CurrentUser`; adding (§5) takes `AdminUser`, and the page shows no Add to
a viewer. Errors are RFC 9457 problems (ADR-0004). The browser never calls server-scan,
herzi or the orchestrator. `<mce>` is a day1 MCE folder
(`ocp4-<env>-mce-<site>-<x>`), `<infra_env>` an InfraEnv on that MCE.

## 0. Where the numbers come from

| Number | Source | Rule |
|---|---|---|
| An MCE's servers | server-scan `GET /api/v1/servers/rows`, through day1's one cached `ServerInventory` (the Nodes tab and placement read the same cache entry) | rows whose `mce_name` is the MCE folder |
| In clusters | the same rows | `openshift_state` `INSTALLED` |
| **Available** (Agents in the MCE's inventory, in no cluster) | the same rows | `openshift_state` `INSTALLED_TO_INVENTORY` |
| Usable | the same rows | available, out of maintenance, reachable, not stale, neither `CRITICAL` nor `UNKNOWN`, not contested: placement's rule (`mce_capacity.usable`), shared |
| A server's InfraEnv | the MCE's InfraEnv list (hub, cached as for the create form) | the InfraEnv `<e>` for which the server's name starts with `ocp-<e>` (the add-server workflow draws a pool with `^ocp-<infraEnv>`), the longest when several do; else the InfraEnv of a live lock on this MCE; else none (`infra_env: null`) |
| Hardware | the rows | `vendor` and `model` |
| Drawable (the page's **Free**) | the rows | `AVAILABLE` servers named `ocp-<infraEnv>…`, healthy, reachable, unlocked, out of maintenance: "servers in server-scan, not yet in this pool, that Add could pick". server-scan's count; the workflow decides |

An MCE that no row names is **unknown** (`known: false`), never zero.
server-scan unreadable: the route answers 502. The MCE's InfraEnvs
unreadable (or live status off): its rows are still counted, under
`infra_env: null`, and `infra_envs_error` says why.

**Not shown in the alpha: herzi's InfraEnv annotations**
(`herzi.redbull.io/blocked-until`, `herzi.redbull.io/state`). Day1's MCE
read lists InfraEnv names only; reading their annotations is a new hub read
and a new grant. herzi's numbers and decisions (demand, target, need, dry
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
          "infra_env": "dell-r650-site1-96c-768gb",
          "available": 2,
          "usable": 2,
          "hardware": [{"vendor": "dell", "model": "PowerEdge R650", "available": 2, "usable": 2}],
          "drawable": 1
        },
        {
          "infra_env": null,
          "available": 1,
          "usable": 1,
          "hardware": [{"vendor": "dell", "model": "PowerEdge R760", "available": 1, "usable": 1}],
          "drawable": null
        }
      ],
      "infra_envs": ["dell-r650-site1-96c-768gb", "dell-r760-site1-64c-512gb-20tb"],
      "infra_envs_error": null
    }
  ],
  "add_servers": {"available": true, "detail": null},
  "runs": {"available": true, "detail": null}
}
```

- `mces`: every MCE folder of the day1 repo (read-only, convention 14), by
  site then name.
- `pools`: one per InfraEnv on the MCE, even with nothing available (so it
  can be filled), then `infra_env: null` for available servers matched to
  none; sorted by name, `null` last. `hardware` sorted by vendor, model.
- `add_servers.available` is `false`, with `detail`, when `DAY1_ADD_SERVERS`
  is off, there is no orchestrator, or live status is off (the InfraEnvs
  come from the MCE).
- `runs.available` is `false`, with `detail`, without the orchestrator.

| Status | `code` | When |
|---|---|---|
| 501 | `FEATURE_DISABLED` | server-scan is not configured (`SERVER_SCAN_URL`) |
| 502 | `DEPENDENCY_UNAVAILABLE` | server-scan could not be read |

## 2. `GET /api/day1/inventory/mces/{mce}/infra-envs/{infra_env}/candidates`

A pool's servers, for the named-install picker: `AVAILABLE` servers named
`ocp-<infra_env>…`, with only what picking needs. Not a fleet view: a
server's full record belongs to the future Server Scan area.

```json
{
  "mce": "ocp4-prod-mce-site1-a",
  "infra_env": "dell-r650-site1-96c-768gb",
  "candidates": [
    {
      "id": "srv_…",
      "name": "ocp-dell-r650-site1-96c-768gb-<serial>",
      "vendor": "dell",
      "model": "PowerEdge R650",
      "health": "HEALTHY",
      "lock": null,
      "offered": true,
      "why_not": null
    },
    {
      "id": "srv_…",
      "name": "ocp-dell-r650-site1-96c-768gb-<serial>",
      "vendor": "dell",
      "model": "PowerEdge R650",
      "health": "HEALTHY",
      "lock": {"holder": "add-server-to-mce", "mce": "ocp4-prod-mce-site1-b", "infra_env": "dell-r650-site1-96c-768gb", "expires_at": "2026-11-13T18:00:00Z"},
      "offered": false,
      "why_not": "locked by add-server-to-mce until 2026-11-13T18:00:00+00:00"
    }
  ]
}
```

- `lock` is `{holder, mce, infra_env, expires_at}` while server-scan's
  reservation is held (§3), else `null`.
- `why_not`, the first that applies: locked (by anyone), in maintenance,
  contested. The workflow fails a named run for each of these (§3), so
  Wingman does not offer them. Health is shown and not refused (a named
  install may waive it).
- Offered first, then by name.

| Status | `code` | When |
|---|---|---|
| 404 | `NOT_FOUND` | No such MCE in the day1 repo, or no such InfraEnv on it |
| 501 | `FEATURE_DISABLED` | server-scan not configured, or live status off (the InfraEnvs come from the MCE) |
| 502 | `DEPENDENCY_UNAVAILABLE` | server-scan or the MCE could not be read |

## 3. server-scan's lock, and what the workflow does with it

Read 2026-11-13 from team-redbull's public repositories.

- **The lock is server-scan's `reservation`** ("the install lock"). On
  `/servers/rows` it is `reservation{held, holder, mce_cluster, infra_env,
  expires_at}`; `held` is computed when read (no expiry, or the expiry
  ahead), so an expired lock reads `held: false`.
- **Who takes it:** the add-server-to-mce workflow (holder
  `add-server-to-mce`, or `install-server` for a run started before the
  rename): 2 h while installing, 24 h on success; the uninstall-server-from-hc
  workflow (holder `uninstall-server-from-hc`); and a person only through
  server-scan's admin API (`POST/DELETE /servers/{id}/reservation`; its UI
  has no such button). **herzi never calls server-scan**: it starts pool
  draws with `count` and treats a reserved server as a shortage.
- **A pool draw** asks server-scan for `AVAILABLE`, healthy, reachable,
  unlocked servers out of maintenance named `^ocp-<infraEnv>`; one that loses
  the race moves to its next candidate.
- **A named install** is refused inside the run, as a FAILED run and never
  a 4xx at the start: a server that is not `AVAILABLE`, is contested or in
  maintenance (`ServerNotAvailableError`), or locked by another run
  (`ServerReservedError`). The workflow does not check a named server's
  name against the InfraEnv: Wingman offers only servers named
  `ocp-<infraEnv>…`.

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
      "error": null
    }
  ]
}
```

- The orchestrator's `GET /workflows/runs?workflow_type=AddServerToMceWorkflow&limit=200`,
  newest first; the 50 newest are shown, and the 20 newest are each read
  (`GET /workflows/runs/{id}`) for `phase`, `server_name` and `error`.
  Both reads are kept 10 s; a start drops them.
- Run ids: a pool draw is `add-server-to-mce-<mce>_<infraEnv>_<slot>` (slot
  1-100), a named install `add-server-to-mce-<mce>_<server, lowercased>`;
  the orchestrator adds `ocp4-` to the MCE. An id that is neither is shown
  with `mce`, `infra_env` and `slot` null.
- **`origin`**: `named` is a person (herzi only sends `count`); `pool` is
  "herzi or a person". The orchestrator records no `requested_by`, so a
  pool draw's author cannot be told. Never guessed.
- `phase` is the workflow's own word, passed through; Wingman keeps no list.

| Status | `code` | When |
|---|---|---|
| 501 | `FEATURE_DISABLED` | No orchestrator (`WORKFLOWS_API_URL`) |
| 502 | `DEPENDENCY_UNAVAILABLE` | The orchestrator could not be read |

## 5. `POST /api/day1/inventory/mces/{mce}/infra-envs/{infra_env}/add-servers`

Body: `{"count": N}` (1-20, let the pool pick) or `{"server_names": [..]}`
(1-20 distinct names from §2's offered candidates); exactly one.

Day1 checks that the MCE is a day1 MCE, the InfraEnv is on its list and
every named server is offered (§2); then it starts
`POST <orchestrator>/workflows/server-lifecycle/add-server-to-mce` with
`{infra_env, mce_cluster: <mce>, namespace?: MCE_INFRAENV_NAMESPACE,
count | server_names}`, logs `servers_add_started` (who, MCE, InfraEnv,
count or names, workflow ids), and answers:

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
| 404 | `NOT_FOUND` | No such MCE in the day1 repo, or no such InfraEnv on it |
| 409 | `ADD_SERVER_ALREADY_RUNNING` | The orchestrator's 409: a named server already installing, or every slot of the pool busy |
| 422 | `VALIDATION_ERROR` | Neither or both of `count` and `server_names`; a named server not offered (each in `details.problems`); the orchestrator's 422 |
| 501 | `FEATURE_DISABLED` | `DAY1_ADD_SERVERS` off, no orchestrator, or live status off |
| 502 | `DEPENDENCY_UNAVAILABLE` | Nothing was started: the orchestrator was not reached, refused, or the InfraEnvs could not be read |
| 504 | `AMBIGUOUS_WRITE` | Sent, no answer: some may have started. Look at the runs before sending again |

## 6. Settings (day1)

| Variable | Default | Meaning |
|---|---|---|
| `DAY1_ADD_SERVERS` | `false` | Offers adding servers. Needs `WORKFLOWS_API_URL` (refused at start otherwise, ADR-0009) and, at run time, live status for the InfraEnvs |
| `SERVER_SCAN_URL` | (exists) | Inventory's counts; empty: the page answers 501 |
| `WORKFLOWS_API_URL` | (exists) | The runs; empty: no runs, no install |
| `MCE_INFRAENV_NAMESPACE` | (exists) | Sent as `namespace`, and where InfraEnvs are listed |

Chart: `day1.addServers.enabled`. No new grant: the MCE token already lists
InfraEnvs (ADR-0040).

`DAY1_FAKE_FLEET=true` (development) fakes the add-server runs too: they walk
a few sample phases on the fake fleet, and a fake herzi starts a pool draw
now and then on one short pool (`dev/fleet-fixtures/inventory.yaml`).

## 7. Metrics

`workflows` operation `start_add_server` (outcomes `ok`, `conflict`,
`rejected`, `unavailable`, `ambiguous`); the runs reuse `list_runs` and
`get_run`. No MCE, InfraEnv or server in a label (ADR-0010).

## 8. Left for later

- **The shared table.** The runs and a pool's servers are simple lists.
  TODO: switch the runs to `apps/web/components/data-table/` once the
  Segments branch (ADR-0047) is on main.
- **A link from each server to its record** in the future Server Scan area,
  once it exists.
- herzi's annotations (§0), its Lease ("is herzi running here?") and its
  numbers.
- `remove-server-from-mce`, the way back for an over-filled pool.
