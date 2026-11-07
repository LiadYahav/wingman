# ADR-0017: Provisioning is a ClusterProvisioner port: a merge request today, the create-cluster workflow later

Date: 2026-11-07
Status: Accepted

## Context

The team plans a Temporal `create-cluster` workflow (allocate the segment,
compose and commit the file, wait for the merge, verify the DHCP scope) and
a `deprovision-cluster` workflow. Neither exists yet. Until they do, Wingman
owns day1 (user decision, 2026-11-07): it proposes the change as a merge
request, CI runs `allocate-segment` on the branch, and a human merge is the
approval.

## Decision

- The use cases describe a change (`ClusterChange`: create, modify or
  delete one cluster file, on behalf of a user, guarded by the revision it
  was read at) and hand it to a `ClusterProvisioner` port.
- `GitClusterProvisioner` (today) turns it into one commit on a new branch
  `platform/<user>/<action>-cluster-<name>-<UTC stamp>` cut from the
  project's default branch, and one MR back into it, with the title,
  description footer and labels (`wingman`, `day1`, `<action>`) from
  `wingman_core.domain.mr_conventions` (ADR-0007). The commit is authored by
  the user. Nothing is retried (ADR-0006).
- `main.py` chooses the provisioner. A workflow-backed provisioner that
  starts `create-cluster` (and `deprovision-cluster`) replaces the Git one
  there; the use cases, validation and API stay.
- Specs are not provisioning: they always change through MRs in the specs
  project (`GitSpecChanges`).

## Alternatives rejected

- **Call GitLab from the use cases**: the switch to the workflow would then
  touch every use case.
- **Start the workflow now**: it does not exist.

## Consequences

- `ProvisionResult` holds a merge request today; it gains a workflow run
  when the workflow provisioner arrives, and the API's create response
  follows.
- The orchestrator API has no auth (accepted by the user); the workflow
  provisioner will call it from the backend only, behind `AdminUser`.

## Verification

`apps/day1-service/tests/unit/infrastructure/test_merge_requests.py` (one
commit, one file, MR conventions round-trip, default branch, author,
revision guards) and the lifecycle test in
`apps/day1-service/tests/api/test_cluster_lifecycle.py`.
