# ADR-0041: Reads refresh in the background, a merge costs what it changed, and a new replica warms itself

Date: 2026-11-12
Status: Accepted; amended 2026-11-13 (day2's chart repo lookups were missed: they too answer stale while one read refreshes them)

## Context

The user reported very slow loading in production, as if the cache were per
user. The server caches were never per user: GitLab is read with the
service's token, and no cache key names a user. What is per user is the
browser's own cache (`wingman-query-cache` in localStorage). Every person
and browser starts empty, it ends after 10 minutes, and a new build drops it.
So each person meets the server's cold cost themselves. That cost, measured
with `scripts/dev/bench_day1_reads.py` on 314 clusters at 0.2 s per GitLab
call:

| Case | Cluster list | Why |
|---|---|---|
| The first load after any merge to the day1 repo | 6.74 s, 327 calls | `last_change` ("changed by, at") looked up every cluster's history again when the branch moved (ADR-0035 named this and left it) |
| The first load on a new pod (deploy, restart, every replica) | 6.75 s, 327 calls | the same lookups, plus the archive |
| The first load after each TTL (30 s day1, 15 s day2) | 0.48 s | the branch-head check (and the project) ran inline |
| 20 people at once after a merge | 8.31 s | single-flight held the calls to one set; the wait is the lookups, then CPU |
| 20 open pages asking for live status | 12,000 MCE calls | live status read the hub uncached, per request |

A warm list costs 0.05 s, three quarters of it parsing every cluster file's
YAML again on each request. Pods run one uvicorn worker with half a CPU, so
that parse queues requests behind each other. The JSON went out uncompressed:
188 KiB for 314 clusters.

## Decision

- **A read may be answered stale while one fetch refreshes it**
  (`TtlCache.get_or_fetch(..., stale=)`, `wingman_core.infrastructure.cache`).
  - Past its TTL, a value is still answered for `stale` more seconds while
    one background fetch replaces it.
  - No value older than a minute (`MAX_AGE`, ADR-0011's bound) is ever
    answered. `stale_for(ttl)` is that minute less the TTL.
  - A refresh that fails keeps the old value until its time is over; then a
    read fetches inline and reports the error itself (ADR-0004).
  - A write's invalidation removes the value and lets go of any fetch of it
    already running: nothing a write made stale is answered, and a read
    after the write never joins a fetch that started before it (one did,
    while a background refresh ran; found in review).
  - It is used for each repository's branch head (`RepoSnapshots.head`, so
    day1 and day2), day1's projects, and day2's team list and day1 project.
    MR lists, approvals and the hub keep plain TTLs.
- **A moved head's files are fetched by the background check.** It starts
  the new archive download, so the next reader does not wait for it.
- **A merge costs a history lookup only for the files it changed.**
  - When the branch moves, a file whose bytes are the same at both heads
    keeps the last change it had (`CachedRepository.last_change`,
    `snapshots.unchanged`).
  - A file read file by file (no archive) is "unknown", never "the same", and
    is looked up again.
- **A new replica warms itself** (`wingman_core.infrastructure.warm_up`).
  - At start-up, in the background, day1 reads the cluster list (with every
    last change) and the flavors; day2 reads each team repo and its day1
    index.
  - Readiness does not wait for it: a request that arrives meanwhile joins
    the same fetches. A failure is logged; the first real read retries it.
- **A cluster file is parsed once per distinct text**
  (`ClusterService._parse`, at most 4,096 kept). The parsed values are
  never changed after, so requests share them.
- **Live status reads the hub through the same 10 s cache as the nodes view**
  (`CachedHubApi`, one instance for both; ADR-0038 had it read directly), so
  many open pages are one read of each HostedCluster and NodePool list.
- **nginx compresses JSON, JavaScript, CSS and SVG** (`gzip`, level 5, above
  1 KiB), never `text/event-stream`.

## Alternatives rejected

- **A shared cache across replicas (Redis).** It is a new stateful service in
  a disconnected install. After this ADR, a replica's share of a merge is one
  head check, one archive and one history lookup per changed file. The
  default is one replica per service. See `docs/ideas/shared-cache.md`.
- **A background loop that keeps every head fresh.** It costs GitLab calls
  when nobody is looking (every team repo every 15 s). A stale answer while
  people use the page, and an inline check after a quiet minute, cost
  nothing extra.
- **A longer TTL.** It would make every answer older, not just the one that
  arrives while a refresh runs. ADR-0011 keeps the minute.
- **PyYAML's C loader.** Its error messages and edge cases differ, and those
  messages are shown to people; caching the parse removes the repeat
  entirely.
- **A cap on live status's concurrency.** It made one person's list slower
  (7.5 s at 16). Each MCE's httpx client already holds at most 100
  connections, and the cache removes the repeats.

## Consequences

- **Measured, same harness and data as the context (314 clusters, 0.2 s per
  GitLab call):**

  | Case | Before | After |
  |---|---|---|
  | The first load after a merge | 6.74 s, 327 calls | 0.01 s (an answer at most a minute old), then 0.22 s with 1 call |
  | 20 people at once after a merge | 8.31 s | 0.20 s, then 0.30 s |
  | The first load after the TTL | 0.48 s | 0.01 s |
  | The first load on a new pod | 6.75 s | paid by the warm-up as the pod starts |
  | 20 open pages, live status | 12,000 MCE calls, 7.31 s | 600 calls, 5.91 s |
  | Ten warm lists, CPU | 1.32 s | 0.53 s |
  | The list on the wire | 188 KiB | 6 KiB gzipped (the test clusters are copies; real files compress less) |

- **Staleness is unchanged in kind and bounded the same:** at most a minute,
  and a person's own write is seen at once. After someone else merges, one
  more page can show the previous commit while the refresh runs.
- **"Changed by, at" can name an older commit** when a file changed and
  changed back between two head checks. It is shown, never used as a write
  guard (writes use `changed_since`, ADR-0035).
- **The previous head's archive is held** until the next move, for the
  comparison: at most one more day1 archive in memory.
- **Live status is at most 10 s old** (its stream polls every 30 s by
  default).

## Verification

- `packages/wingman-core/tests/unit/infrastructure/test_cache.py`: a stale
  value is answered while one fetch refreshes it; past its time it is fetched
  inline; a failed refresh keeps it until then; an invalidated value is
  never answered stale; a refresh across an invalidation is not kept; a read
  after an invalidation never joins a fetch from before it; the minute's
  bound.
- `test_snapshots.py`: past the TTL the known head answers while one check
  runs; a head older than a minute is checked first.
- `test_warm_up.py` (core, day1, day2): it runs in the background, logs a
  failure, is cancelled on shutdown; day1's first list after it makes no
  history lookup; day2 reads each team repo and the day1 repo once.
- day1 `test_repositories.py`: a branch move looks up the last change only
  of the files it changed.
- day1 `test_status_api.py`: five open pages share one read of the hub.
- `scripts/dev/bench_day1_reads.py --clusters 300 --latency 0.2`: the
  numbers above.
- `docs/ops/performance.md`: how to see the same in a deployment.

## Amendment (2026-11-13): the chart repo lookups

The decision missed day2's chart repo lookups (`GitLabChartRepository`:
`resolve`, `branches`, `values`). They kept a plain TTL, and the add-on list
looks up every chart repo's project and branches, so any load more than a TTL
after the last one waited on GitLab for each chart repo's `get_project`
(about 0.18 s) and `list_branches` (about 0.1 s). On the team's sandbox every
warm `GET /api/day2/addons` took 0.5 to 1.0 s; the team list and fleet
defaults, mostly under 0.1 s.

They now answer stale while one read refreshes them, as the rest do: within
the minute (`MAX_AGE`), a failed refresh keeps the last answer and is logged;
after it, a read fetches inline and an unreachable GitLab fails the page.
"No such project" is an answer and is refreshed the same way, and a moved or
renamed chart repo (`repourl-moved`) is seen on the first read after the
refresh. A version (a branch) made in the chart repo shows within the same
minute.

Pinned by `apps/day2-service/tests/unit/infrastructure/test_chart_repository.py`:
past the TTL the add-on list answers with no GitLab call awaited, and three
lists share one refresh of each lookup; a values file the same; a moved repo,
a repo that appears, and an unreachable GitLab after the minute.

Left with a plain TTL, on purpose: the MR lists (they decide duplicate
creates and placement), audit history, day1's commit and MR diffs (one read
when a page opens), day2's day1 index (keyed by commit and rebuilt from the
held archive without a GitLab call), and other systems' live state
(server-scan rows, segments-manager, the uninstall runs, the MCE hub, day1's
call to day2's installed list).
