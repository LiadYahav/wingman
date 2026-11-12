# ADR-0042: A new cluster can be created by starting the provision-cluster workflow, behind a setting

Date: 2026-11-12
Status: Accepted; extends ADR-0017 (the provisioner's switch to a workflow)

## Context

Wingman has owned day1 creates (convention 13, ADR-0017): it renders the
cluster file, commits it on a branch and opens a merge request, and CI runs
allocate-segment on the branch. The platform team now has the
`provision-cluster` workflow, started through the workflows orchestrator.
It takes the cluster file as its body, judges it, reserves the segment,
pushes the file with the allocation on its own branch, opens the merge
request, waits for the merge, and then registers the cluster in day2's sig
repos (`docs/notes/2026-11-12-provision-cluster-workflow-api.md`).

The workflow only creates. Modify, delete, sync and import still change
the file through Wingman's merge requests.

## Decision

1. **`DAY1_PROVISIONER`** chooses how a create is proposed:
   `merge-request` (the default: nothing changes until the team turns it
   on) or `workflow`. `workflow` needs `WORKFLOWS_API_URL`, and day1
   refuses to start without it (ADR-0009). The chart sets it from
   `day1.provisioner`.
2. **A `ProvisionWorkflow` port** with an orchestrator adapter (beside the
   uninstall's, sharing its client rules) and a fake for `DAY1_FAKE_FLEET`.
   The create use case renders and checks the file exactly as before. In
   `workflow` mode its last step starts the workflow instead of handing a
   `ClusterChange` to the `ClusterProvisioner`:
   - `cluster` is the stem without `ocp4-`;
   - `mce` is the MCE folder;
   - the body is the rendered file with its provenance header.
   The `ClusterProvisioner` keeps every other change.
3. **Wingman starts the run and shows it; the workflow owns the rest.**
   Day1 keeps no list of its phases or checks:
   - the run's own phase is shown humanized, as for a node's uninstall
     (ADR-0038);
   - its merge request link is shown once the workflow reports one;
   - its error is shown in its own words.
   Day1 adds no check of its own for what the workflow judges (the
   24-character name, the forbidden keys): the orchestrator's 422 is shown
   with its words.
4. **Writes are not retried (ADR-0006).**
   - A `409` (a run for the cluster is going) is `ALREADY_EXISTS`.
   - A start sent without an answer is `AMBIGUOUS_WRITE` (504).
   - A start never sent is `DEPENDENCY_UNAVAILABLE` (502).
   - A `422` is `VALIDATION_ERROR`, with the orchestrator's detail.
5. **The API.**
   - `POST /clusters` answers `202` with the run in `workflow` mode, and
     `201` with the merge request otherwise.
   - `GET /clusters/{name}/provision-run` reads the run by its id,
     `provision-cluster-<stem>`.
   - `GET /clusters/provisioner` tells the form which mode is on.

## Alternatives rejected

- **A workflow-backed `ClusterProvisioner` replacing the Git one** (what
  ADR-0017 foresaw): the workflow covers only creates, so it would have
  forwarded every other change to the Git provisioner and widened
  `ProvisionResult` for all of them. A second port, used by create only,
  keeps modify, delete, sync and import untouched and typed.
- **Checking the workflow's rules in Wingman first** (the 24 characters, the
  forbidden keys): that re-implements the workflow's checks, which drift
  when it changes (the user's rule: Wingman only triggers and shows).
- **Sending only the inputs** and letting the workflow render: the workflow
  takes the file, and Wingman's template, flavor locks and machine-config
  checks are where the file is decided today.

## Consequences

- In `workflow` mode, the merge request is the workflow's. Wingman's
  approvals page, the pending rows and the name suggestion's "taken" set
  don't see it until it is merged (the API note's open questions). The
  workflow's own 409 stops a second start for the same cluster.
- The orchestrator has no auth and records no user. Day1 starts runs only
  for `AdminUser` and logs who did.
- A new metrics operation, `start_provision`, on the `workflows` dependency
  (`docs/ops/metrics.md`).

## Verification

- `apps/day1-service/tests/unit/infrastructure/test_provision_workflow.py`:
  the request (query, YAML body), and 202, 409, 422, 504, a dropped answer
  and an unreachable orchestrator, against a mocked transport; the run read
  (phase, merge request, error).
- `apps/day1-service/tests/api/test_provision_workflow_api.py`: create
  answers 202 with the run in `workflow` mode and 201 with the MR
  otherwise; the run route's 404 and 501; the mode route.
- `apps/web/e2e/tests/provision-workflow.spec.ts`: after Create, the run
  with its phase, merge request link and error; the merge-request mode
  unchanged.
