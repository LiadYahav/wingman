# ADR-0024: Chart versions and defaults come from the chart repo on the same GitLab, at the resolved revision and path

Date: 2026-11-07
Status: Accepted; amended 2026-11-14 (ADR-0060: a team's chart repos sit in `<team>/helm-charts`; how a `repourl` is resolved is unchanged)

## Context

A chart repo (`helm-charts/<chart>`) has one frozen branch per release, and
the platform pins by branch name. The legacy service listed branches minus a
hard-coded few, treated `main` as the default, and read `values.yaml` at the
repo root even when the deploy config's `path` pointed at a subchart
(`dhcp-api-token` uses `charts/dhcp-api-token`).

## Decision

- The chart repo is the GitLab project the merged deploy config's `repourl`
  names, when its scheme and host are this GitLab's (`GITLAB_URL`, sub-path
  aware); anything else is reported as "not on this GitLab", never guessed.
- Versions are the repo's branches: the default branch first, then the rest
  newest release first (natural order).
- `targetRevision` defaults to `HEAD`, which is read as the repo's default
  branch. Chart defaults are `<path>/values.yaml` at that revision; a missing
  file or revision is a stated problem on the preview, not an empty map.

## Alternatives rejected

- **Helm repositories or OCI.** Not what the platform uses today.

## Consequences

- With `repoUrl` miscased, a preview shows no chart defaults and says why.

## Verification

`tests/unit/application/test_reads.py` (catalog versions, unreadable defaults,
a repo elsewhere) and `tests/api/test_api.py` (versions, values at a version).

## Amendment (2026-11-14): a team's charts sit in `<team>/helm-charts`

The Context's `helm-charts/<chart>` was one shared group. A team's chart repos
now sit in its own group, `<team>/helm-charts/<chart>` (ADR-0060), and the
fixtures model that. Nothing in this decision changes: the chart repo is still
whatever project the merged `repourl` names on this GitLab, at any depth, and
an address outside the team's group is read like any other. Only a new
add-on's suggested address follows the layout (ADR-0060).
