# ADR-0024: Chart versions and defaults come from the chart repo on the same GitLab, at the resolved revision and path

Date: 2026-11-07
Status: Accepted

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
