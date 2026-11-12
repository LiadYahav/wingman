# ADR-0007: An MR is `(project, iid)`; branch, title and description formats are a contract

Date: 2026-11-07
Status: Accepted

## Context

GitLab numbers merge requests per project: every team's day2 repo has its own
`!5`. The legacy day2 approval service found an MR by searching each team
project for that number and acting on the first hit, so approving, merging or
rejecting `!5` could act on the wrong team's change.

Wingman also writes structured MR titles (`[Wingman/Day1] Create cluster x`),
branches (`platform/{user}/...`) and description footers (`Author:`,
`Action:`, `Resource:`, `Repo:`). The audit view and approvals read them back,
and approvals take the real user from the footer because GitLab shows the
service account as the author. One code path (`bulk_install`) wrote
`[Day2] ...` instead, which nothing could parse.

## Decision

- `MergeRequestRef(project_id, iid)` is the only way to address an MR in code
  and in the API. Nothing takes a bare iid.
- `wingman_core.domain.mr_conventions` holds the builders and parsers, with
  `StrEnum`s for repo, verb and resource type. The formats are unchanged, so
  every MR already in GitLab still parses. A title whose resource name is not
  one word is refused at build time, because it would not parse back.
- Property tests pin round-tripping: whatever the builder writes, the parser
  reads back identically.

## Alternatives rejected

- **Global MR ids.** GitLab has them, but users, URLs and GitLab's UI speak in
  project-scoped iids.
- **Changing the formats.** Every historical MR would stop parsing.

## Note (2026-11-12, ADR-0044)

A flavor's rollout MR has a branch without a timestamp, so a rerun finds
it instead of opening another: `platform/rollout/<flavor>/v<version>/<cluster>`
(`rollout_branch`, `parse_rollout_branch`, pinned by a round-trip property
test). Its title is a sync's, `Sync cluster <name> to spec <flavor>
v<version>`, and it carries the `rollout` label.

## Consequences

- API routes for approvals carry the project (or a key that maps to exactly
  one project), never just a number.
- A new verb or resource type is an enum member plus a test.

## Verification

`packages/wingman-core/tests/unit/domain/test_mr_conventions.py` (round trips,
legacy footer still parses, non-Wingman titles rejected) and the contract test
`test_merge_request_iids_are_per_project`.
