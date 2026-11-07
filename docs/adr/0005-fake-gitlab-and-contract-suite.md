# ADR-0005: Tests run against an in-memory GitLab held honest by a contract suite

Date: 2026-11-07
Status: Accepted

## Context

Wingman's only source of truth is GitLab, and it had zero Python tests: every
behaviour needed a GitLab to observe. Three options exist. Mocks
(`MagicMock`) do not model behaviour: a mock happily returns the same MR
number for two projects, which is exactly the bug day2 has (ADR-0007). A real
GitLab per test run is several gigabytes, needs about 4 GB of RAM and minutes
to boot. A fake with real semantics is fast but can drift from GitLab.

## Decision

Three tiers:

1. **`InMemoryGitLab`** implements `GitLabPort` with real behaviour: projects
   in groups, branches, commits with full trees, atomic multi-file commits,
   `last_commit_id` conflicts, per-project MR numbers, duplicate-MR refusal,
   three-way merges that change the target branch, conflicts, and an injected
   clock. Every application and API test uses it, seeded from
   `dev/gitlab-fixtures` (real repo trees from the team's repos).
2. **Adapter unit tests** with `httpx.MockTransport` pin how REST responses
   and errors map (ADR-0002).
3. **One contract suite**, `wingman_core.testing.gitlab_contract`, runs
   against the fake on every test run and against a real GitLab when
   `WINGMAN_TEST_GITLAB_URL` and `WINGMAN_TEST_GITLAB_TOKEN` are set
   (`-m live_gitlab`; skipped otherwise). A behaviour the fake asserts must
   pass on real GitLab; a live failure means the fake drifted, and the fake is
   fixed first.

The fake doubles as a development backend (`WINGMAN_GIT_BACKEND=fake`), which
settings refuse in production (ADR-0009).

## Alternatives rejected

- **Mocks.** They encode the test author's belief about GitLab, which is the
  thing being tested.
- **A GitLab container in every CI run.** Too heavy for every push; it runs
  locally and can run on a schedule.

## Consequences

- Tests are fast (the core suite runs in under a second) and deterministic.
- Each new GitLab behaviour Wingman relies on needs a contract test first, or
  the fake has nothing holding it honest.

## Verification

- `packages/wingman-core/tests/contract/test_fake_gitlab_contract.py` (every run).
- `packages/wingman-core/tests/contract/test_live_gitlab_contract.py` against
  the local GitLab CE container (`scripts/dev/gitlab-up.sh`).
- 2026-11-07, GitLab CE 19.5.3: 27/27 pass on both. The first live run found
  two real behaviours the fake did not model, both now in the contract and
  the adapter: an MR's stored diff is computed in a background job (empty
  right after the MR opens, so open MRs are diffed with the compare API), and
  a merged MR's source branch is removed asynchronously.
