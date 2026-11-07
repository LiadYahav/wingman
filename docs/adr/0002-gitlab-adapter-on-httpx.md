# ADR-0002: GitLab is reached through an async httpx adapter, not python-gitlab

Date: 2026-11-07
Status: Accepted

## Context

python-gitlab is synchronous. The legacy client wrapped each method in
`asyncio.to_thread` and exposed both `read_file` and `aread_file`. Any call
site that used the sync name blocked the event loop; CLAUDE.md recorded the
result ("health check timeouts") and about 60 sync calls still sat inside
async code, so `asyncio.gather` over them ran serially. The client had no
timeout, returned `dict[str, Any]`, and raised python-gitlab exceptions that
each service translated differently.

Threads also do not end when a request is abandoned: a timed-out request
leaves its thread running against GitLab (server-scan recorded the same
lesson with blocking vendor SDKs).

## Decision

`GitLabHttpAdapter` implements `GitLabPort` on one shared `httpx.AsyncClient`
per process:

- the base URL is `<gitlab>/api/v4`; the token travels in the `PRIVATE-TOKEN`
  header, never in a URL, so it cannot reach a log line or an error message;
- every request has connect and read timeouts (`GITLAB_*_TIMEOUT_SECONDS`);
- responses become domain types (`FileContent`, `MergeRequest`, ...); GitLab
  error responses become `wingman_core.domain.errors` types, mapped by status
  and, for 400s, by GitLab's message text;
- reads retry 429, 502, 503, 504 and transport errors with backoff, honouring
  `Retry-After`; writes are sent once (ADR-0006);
- a merge waits, bounded, for GitLab's background mergeability check, which
  otherwise refuses an "approve and merge" right after "open" with 405.

## Alternatives rejected

- **Keep python-gitlab behind `to_thread`.** It keeps the thread problem and
  the two-names-per-method trap, and python-gitlab's objects leak into callers.
- **python-gitlab's async (`AsyncGitlab`).** It exists only in newer releases
  and still returns lazy objects instead of plain data.

## Consequences

- No call can block the event loop by accident: there is no sync API left.
- The adapter is about 450 lines Wingman owns. Its behaviour is pinned by
  unit tests on recorded GitLab response shapes and by the contract suite
  run against a real GitLab (ADR-0005).
- The text matching for 400 errors depends on GitLab's English messages. The
  live contract suite is what notices if a GitLab upgrade changes them.

## Verification

- `packages/wingman-core/tests/unit/infrastructure/test_gitlab_adapter.py`:
  path encoding, pagination, error mapping, read retries, writes sent once, the
  merge wait, and the token absent from every error text.
- `packages/wingman-core/tests/contract/test_live_gitlab_contract.py` runs the
  shared contract against a real GitLab.
