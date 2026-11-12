# A cache shared by every replica

**Status: Proposed** (2026-11-12). It waits on a decision: does the
deployment run more than one replica per service, and will the team operate
a Redis next to Wingman? ADR-0011 rejected a shared cache "to save a few
seconds of staleness between replicas"; this file revisits it with numbers.

## The question

Each day1 and day2 replica keeps its own cache. With N replicas behind a
Service, nothing one pod read helps another:

- a new pod starts cold;
- a merge is noticed and paid for by each pod;
- each pod has its own minute of staleness, so two pods can show two commits.

The browser's own cache (`wingman-query-cache`) is per person by nature, so
no server design changes that.

## What ADR-0041 already removed

Measured with `scripts/dev/bench_day1_reads.py` (314 clusters, 0.2 s per
GitLab call), per replica:

| Cost | Before ADR-0041 | After |
|---|---|---|
| A merge to the day1 repo | 314 history lookups, 6.7 s for whoever loads next | 1 head check (background), 1 archive, 1 lookup per changed file: 0.2 s |
| The TTL ending | 0.48 s inline | 0 inline (answered stale, refreshed in the background) |
| A new pod | 6.75 s for its first visitor | the same reads, made by the warm-up as it starts |
| Live status with 20 open pages | 12,000 MCE calls | 600 |

So what a shared cache would still save is, per extra replica:

- one head check per TTL per repository;
- one archive per merge;
- one history lookup per changed file;
- one warm-up per pod start.

That is seconds of GitLab time a day, not seconds of waiting for a person.

## For

- **Pods agree.** With two or more replicas and no sticky sessions, two
  loads in a row can show two commits until both refresh, at most a minute
  apart.
- **A pod starts warm**, even when someone hits it before its warm-up ends.
- **The team already runs one.** server-scan, the team's quality bar, keeps
  its cache in Redis (`infrastructure/redis/keys.py`), with key functions
  shared by readers and invalidators, as Wingman's `cache_keys.py` does.

## Against

- **A new stateful service** in a disconnected install: an image to mirror,
  a PVC or none, its own probes, alerts and upgrades, and a failure mode
  where Wingman must still answer when Redis is down.
- **Archives don't fit.** A day1 archive is tens of MB. Sharing it means
  sharing parsed results instead, which is a larger change than the cache.
- **The default is one replica** per service (`replicaCount`), where a
  shared cache saves nothing.

## If it is decided

1. A `CacheBackend` port with the `TtlCache` semantics (single-flight
   becomes a short Redis lock; stale-while-refresh and generations stay).
   Then an in-memory adapter (today's) and a Redis adapter, chosen by a
   setting, with the contract suite run on both (as ADR-0005 does for
   GitLab).
2. Share only small, derived values: branch heads, last changes, MR lists,
   hub reads. Keep archives per pod.
3. Fall back to the in-memory cache when Redis is unreachable, and count
   it in a metric.

Before that, a cheaper step for more than one replica is **affinity per
person**, so each person stays on one warm pod and sees one commit. The
Route's own stickiness does not reach day1: the Route goes to nginx, and
nginx proxies to the day1 Service's one ClusterIP. Two ways that do:
- a headless Service for day1 and day2, and `hash $http_authorization
  consistent;` in nginx's upstreams (nginx resolves the names at start-up,
  so a scale-up needs an nginx restart, or a `resolver` and a variable);
- `sessionAffinity: ClientIP` on the Services. Behind one nginx pod, this
  pins everyone to one backend pod, which defeats the replicas.
