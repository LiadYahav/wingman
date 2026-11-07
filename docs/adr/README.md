# Architecture decision records

One file per decision, numbered, never deleted. A decision that changes is
superseded by a new ADR that says so; the old one stays and gets a
`Superseded by` status line. Every ADR uses the template below. The
**Verification** section names the test or measurement that pins the
decision, so the next person can tell it is still true.

```
# ADR-NNNN: <the decision, as a sentence>

Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by ADR-NNNN | Superseded in part by ADR-NNNN

## Context
## Decision
## Alternatives rejected
## Consequences
## Verification
```

| ADR | Decision |
|---|---|
| [0001](0001-layered-packages-with-ports.md) | Code is layered (domain, ports, application, infrastructure, web) and import-linter enforces it |
| [0002](0002-gitlab-adapter-on-httpx.md) | GitLab is reached through an async httpx adapter, not python-gitlab |
| [0003](0003-exact-pins-one-lockfile.md) | Dependencies are pinned exactly, in one workspace lockfile |
| [0004](0004-rfc9457-error-envelope.md) | API errors are RFC 9457 problems with an append-only error code |
| [0005](0005-fake-gitlab-and-contract-suite.md) | Tests run against an in-memory GitLab held honest by a contract suite |
| [0006](0006-write-semantics.md) | Writes are guarded by `last_commit_id` and never retried |
| [0007](0007-merge-request-identity-and-conventions.md) | An MR is `(project, iid)`; branch, title and description formats are a contract |
| [0008](0008-ty-type-checker.md) | ty is the type checker, as in server-scan |
| [0009](0009-settings-fail-closed.md) | Settings refuse insecure or fake-in-production configurations at start-up |
| [0010](0010-metrics-are-a-contract.md) | Metrics follow one catalogue with bounded labels, served off the public Route |
| [0011](0011-per-replica-read-cache.md) | GitLab reads are cached per replica for seconds; writes clear what they made stale |
| [0030](0030-releases-from-version-forward-only.md) | A release is a VERSION bump that only moves forward; images build on every PR and publish from main |
| [0032](0032-ci-supply-chain.md) | CI checks its own supply chain: zizmor-enforced SHA pins, checksum-verified tools, an npm audit that only shrinks |
