# ADR-0004: API errors are RFC 9457 problems with an append-only error code

Date: 2026-11-07
Status: Accepted

## Context

The legacy services raise FastAPI's `HTTPException` with free-text details,
so the web app shows whatever string a service chose and cannot tell "the
cluster changed since you opened it" from "GitLab is down". Some read errors
were swallowed instead: a failed drift check showed as "not drifted", and a
cluster whose file failed to parse silently disappeared from the list.

## Decision

Every error response is RFC 9457 "Problem Details", `application/problem+json`,
built in one place (`wingman_core.web.exception_handlers`):

```json
{
  "type": "/problems/revision-conflict",
  "title": "Revision Conflict",
  "status": 409,
  "detail": "sites/site1/... has changed since 1a2b3c4d",
  "instance": "/api/day1/clusters/ocp4-prod-a-site1",
  "code": "REVISION_CONFLICT",
  "request_id": "req_...",
  "details": {}
}
```

- `code` is the stable member clients match on. `ErrorCode` is append-only:
  a shipped code is never renamed or removed.
- Services raise `AppError` subclasses. A `GitError` that reaches the boundary
  is translated (`from_git_error`), so "GitLab refused Wingman's token" (502
  `GIT_PERMISSION_DENIED`) is distinguishable from "you may not do this" (403
  `FORBIDDEN`).
- FastAPI's own 404 and 422 and any unexpected exception use the same shape.
  An unexpected one never echoes its message, only the request id.
- `type` is a relative reference; the air gap has no public URL to resolve.
- Swallowing a read error is not allowed: if part of a page cannot be read,
  the response says so.

This is server-scan's ADR-0002, adopted as is.

## Alternatives rejected

- **A bespoke envelope.** No advantage over the standard, and clients and tools
  already understand RFC 9457.
- **`fastapi-problem`.** The format is a handful of fields; not worth a
  dependency in an air-gapped mirror.

## Consequences

- The web app's API client parses one shape everywhere.
- The request id ties a user's error report to the service log line.

## Verification

`packages/wingman-core/tests/unit/web/test_exception_handlers.py` pins the
body, the Git error translation, framework errors, and that a 500 hides its
message but carries the request id (also as a header, which Starlette would
otherwise drop on 500s).
