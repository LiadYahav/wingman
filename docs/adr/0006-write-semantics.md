# ADR-0006: Writes are guarded by `last_commit_id` and never retried

Date: 2026-11-07
Status: Accepted

## Context

Every Wingman change is a GitLab commit. Two things make writes delicate.
First, a file can change between the moment Wingman reads it and the moment
it writes: another user's edit, or, in the new day1 flow, the allocate-segment
workflow and CI committing `vlanId`, `dhcp_values` and `mcFiles` onto the MR
branch. Writing blindly overwrites their work. Second, a write that times out
may still have happened. Retrying a commit can commit twice; retrying a merge
can fail confusingly after it succeeded.

## Decision

- An update or delete that follows a read passes the read's `last_commit_id`.
  GitLab (and the fake) refuse it with `RevisionConflictError` if the file
  changed since; the application re-reads and decides, and tells the user.
- A merge passes the `sha` the reviewer approved; if the branch moved since,
  the merge is refused (`RevisionConflictError`) instead of merging unreviewed
  commits.
- The GitLab adapter sends writes exactly once. A write that fails before it
  is sent (connection refused) is `GitUnavailableError`. One that fails after
  (timeout, 5xx) is `AmbiguousWriteError`: the caller must re-read state, and
  the API answers 504 `AMBIGUOUS_WRITE` saying so.
- Reads are retried (ADR-0002).

## Alternatives rejected

- **Last write wins.** It silently discards the workflow's and CI's commits.
- **Retrying writes with idempotency keys.** GitLab's commit and merge APIs
  have none.

## Consequences

- Users occasionally see "changed since you opened it" and must reload. That
  is the honest answer.
- `wingman_dependency_requests_total{outcome="ambiguous"}` should be zero; an
  alert on it is planned (docs/ops/metrics.md).

## Verification

- Contract: `test_update_with_stale_last_commit_id_is_revision_conflict`,
  `test_merge_with_stale_sha_is_revision_conflict`, `test_commit_is_atomic`.
- Adapter: `test_writes_are_never_retried`.
