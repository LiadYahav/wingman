# ADR-0011: GitLab reads are cached per replica for seconds; writes clear what they made stale

Date: 2026-11-07
Status: Accepted; superseded in part by ADR-0035 (files and trees at the default branch are read once per commit; the TTL now bounds how often a branch head is checked) and ADR-0041 (a read may be answered stale, never older than a minute, while one fetch refreshes it)

## Context

Every Wingman page is many GitLab reads: the cluster list walks
`sites/*/mces/*/hostedClusters/` and reads each file; the day2 views walk every
team repo. Without a cache a few users refreshing a page multiply into
hundreds of GitLab calls. The legacy cache had two flaws worth not repeating:
writes cleared the wrong key (`approvals:day1:list` while the list lived under
`approvals:combined:list`), so a user's own approval stayed visible as
pending; and nothing stopped a burst of identical misses from all going to
GitLab at once.

## Decision

- `TtlCache` (`wingman_core.infrastructure.cache`) is in-process, one per
  replica. TTLs are seconds to a minute, never longer: GitLab stays the source
  of truth, and other writers (people, CI, the allocate-segment workflow)
  change the repos behind Wingman's back.
- Concurrent misses for one key share a single fetch. A failed fetch is not
  cached. A value whose fetch overlapped an invalidation is returned but not
  stored, since it may predate the write.
- Writes invalidate the keys they made stale before the API answers, so the
  user's next read reflects their change. Keys are built by one function per
  key family in each service, and the write path invalidates through the same
  functions, so a key and its invalidation cannot drift apart.
- The GitLab webhook (day1) may invalidate too, but correctness never depends
  on it.

## Alternatives rejected

- **A shared cache (Redis).** Another stateful dependency in an air-gapped
  install, to save a few seconds of staleness between replicas. Revisit if
  replicas grow beyond a handful.
- **No cache.** GitLab load grows with page views, and the tree walks are slow.

## Consequences

- Two replicas can disagree for up to one TTL. A user can see their own change
  immediately only on the replica that made it; with sticky sessions or one
  replica per service that is invisible. Keep TTLs short.

## Verification

`packages/wingman-core/tests/unit/infrastructure/test_cache.py`: TTL expiry,
single-flight, failures not cached, prefix invalidation, a fetch across an
invalidation not kept, the size bound. Each service adds a test that its
write path clears its read keys and fails if the invalidation is removed.

## Amendment (2026-11-13): a dropped request never cancels a shared fetch

The first reader of a missing key used to run the fetch itself, and the
readers who joined it waited on its result. When that first request was
cancelled (the browser left the page, a client timed out), the fetch was
cancelled with it: every reader who had joined failed as if it had been
cancelled too, and nothing was kept, so the next reader fetched again.

The fetch now runs in a task of its own, and every reader awaits it shielded,
the first one included (as the snapshot store's archive reads already did,
ADR-0035). A cancelled reader stops waiting; the fetch finishes, the others
get its value, and it is kept as usual. Single-flight, failures not cached and
the invalidation rules are unchanged.

Pinned by `packages/wingman-core/tests/unit/infrastructure/test_cache.py`: a
cancelled first reader leaves the second its value, and a fetch whose only
reader was cancelled still keeps its value for the next.
