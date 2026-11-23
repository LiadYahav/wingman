# ADR-0042: A new cluster can be created by starting the provision-cluster workflow, behind a setting

Date: 2026-11-12
Status: Accepted; extends ADR-0017 (the provisioner's switch to a workflow); amended 2026-11-13: Wingman sees the workflow's merge request; amended 2026-11-23: the workflow is the only way to create, the orchestrator is required and Wingman's create merge request is removed (see the amendments)

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
  workflow's own 409 stops a second start for the same cluster. (Since the
  2026-11-13 amendment, the approvals page, the "taken" set, the "already
  being created" check and MCE placement find it by its branch.)
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

## Amendment (2026-11-13): Wingman sees the workflow's merge request

**Wingman sees the workflow's merge request by its branch; it is still
reviewed and merged in GitLab.**

The user: "see inside the wingman also the MR that being created by the
workflow — count open MRs on provision-cluster/<stem>". The workflow's
source (team-redbull/workflows, `shared/cluster_names.py`) names the
merge request's source branch `provision-cluster/<file stem>`
(`provision-cluster/ocp4-prod-rcs-site1-a`), targets `main`, and gives it
no label and the title `Provision hosted cluster <stem> on <mce folder>`;
a re-run reuses the branch and the merge request. Its author is the
workflow's GitLab account.

1. **One rule, in the day1 domain.** `provision_branch_stem` in
   `wingman_day1.domain.workflows` gives the file stem for a branch that is
   `provision-cluster/<stem>`, else `None`. Nothing else reads that branch.
2. **It counts as an open create, in either mode.** A run may be started
   outside Wingman, so day1 lists the day1 project's open merge requests
   without a label filter (one more cached read, cleared like the others
   by a write or a merge request webhook) and keeps those on the
   workflow's branch. They are taken names for the name suggestion, a
   create of the same name is refused with the merge request's URL, and
   MCE placement counts each on its MCE and for its owner, read from its
   diff as for Wingman's own. An unlabelled merge request on any other
   branch is not counted. Wingman's labelled lists keep their meaning.
3. **Approvals lists it, view only.** `GET /api/day1/approvals` adds the
   workflow's open merge requests; `MRDetail.opened_by_workflow` is
   `"provision-cluster"` for them and `null` for Wingman's, so the web
   never reads branch names. The page marks the row with a
   `provision-cluster workflow` badge and opens it in GitLab, not on
   Wingman's review page.

**Why approval stays in GitLab.** Wingman's rule is that nobody approves
their own change, and it knows the requester from its own description
footer (ADR-0007). The workflow's merge request has no footer and the
orchestrator records no user (the API note's open question 5), so Wingman
cannot tell whether the person approving started the run. `Approvals` in
`wingman-core` still refuses any merge request without the `wingman`
label: approving, rejecting or editing the workflow's answers 404.

**Rejected:** listing provision runs from the orchestrator
(`GET /workflows/runs?workflow_type=…`) instead. That depends on the run's
class name (open question 4) and on the orchestrator answering, and a run
is not the merge request: GitLab is where the merge request is, and day1
already reads it.

**Verification:**
`apps/day1-service/tests/unit/domain/test_workflows.py` (the branch rule);
`apps/day1-service/tests/api/test_provision_merge_requests_api.py` (listed
with `opened_by_workflow`, a taken name, a refused create with its URL,
404 for detail, approve, reject and edit, a webhook shows a new one, an
unlabelled MR on another branch ignored);
`apps/day1-service/tests/api/test_placement_api.py`
(`test_the_provision_workflows_open_mr_counts_on_its_mce_and_for_its_owner`);
`apps/web/e2e/tests/approvals.spec.ts` (the badge and the GitLab link).

## Amendment (2026-11-23): the workflow is the only way, and the orchestrator is required

**Every create starts `provision-cluster`. `WORKFLOWS_API_URL` is
required, and Wingman's own create merge request is removed.**

The user: "Wingman default mode should be the day1 workflows! It's
production! Let's make it dependency and remove the old way completely,
save us code base!"

**Why.** Since team-redbull/workflows `ff1aba7` (2026-11-11) allocate-segment
no longer writes to Git: it refuses `values_branch` with a 422, and the
platform's guide stops the day1 CI from calling it. A merge request
Wingman opened therefore never got its `vlanId` and `dhcp_values`. The
segment is now reserved by `provision-cluster`, which appends both keys to
the file in the commit that pushes it on `provision-cluster/<stem>`.
`provision-cluster` is in production.

1. **One create.** `POST /api/day1/clusters` renders and checks the file as
   before (the preview runs every check a create runs), then starts the
   workflow and answers `202` with the run. It never answers `201` with a
   merge request again. `GET /clusters/{name}/provision-run` stays.
2. **The orchestrator is required.**
   - Day1 refuses to start in production without `WORKFLOWS_API_URL`
     (`check_runtime`, ADR-0009).
   - The chart fails its render without `workflows.url` unless
     `environment` is `development`.
   - In development and tests, without the orchestrator (or with
     `DAY1_FAKE_FLEET`), the in-memory `FakeProvisionWorkflow` stands in:
     its runs walk sample phases and write nothing to Git.
   - The rule that `workflows.url` needs `serverScan.url` (an uninstall
     checks the server first, ADR-0038) still holds, so a production
     install sets both.
3. **Removed, because only Wingman's create used them.**
   - the setting `DAY1_PROVISIONER`, its validator and `GET
     /clusters/provisioner` (now a 404);
   - `ClusterAction.CREATE`, so a `ClusterChange` always replaces or removes
     an existing file, guarded by its read;
   - the create branches of the merge-request writer
     (`create-cluster` branch, `Create cluster … from spec` title and
     commit, the new-file change);
   - the create MR's description: its review summary and its "MCE
     placement" section (the placement's record is the
     `mce_placement_chosen` log line and the metric, ADR-0050);
   - counting Wingman's own open create MRs by their title (the "already
     being created" check, the name suggestion's taken set, placement):
     only the workflow's, by their branch, are counted now;
   - a review edit's exemption for a cluster file not yet on the target
     branch (ADR-0055, ADR-0062): Wingman opens no such merge request.
4. **Kept.**
   - Wingman's own merge requests for every other change: modify, delete,
     sync, import, a flavor's rollout, the specs project and day2.
   - `wingman_core.domain.mr_conventions` unchanged: its builders serve
     those changes and its parsers still read the `Create cluster` merge
     requests in GitLab's history (the audit view).
   - Everything that finds the workflow's merge request by its branch
     (the 2026-11-13 amendment): name holds, "already being created",
     placement counts, the Approvals row.
   - `day1.provisioner` in `values.schema.json`, deprecated: accepted, ignored,
     rendering nothing (ADR-0059's rule for dropped keys).

**Checked against the workflow.** team-redbull/workflows main at
`29ef001`: the request still matches (`POST
/workflows/cluster-lifecycle/provision-cluster?cluster=&mce=`, the file as
an `application/yaml` body, `202 {workflow_id, run_id}`, 409, 422), as do
the run read, the workflow id `provision-cluster-<stem>` and the branch
`provision-cluster/<stem>`. The workflow names its merge request's state
`open`, `merged` or `closed` (not GitLab's `opened`), which Wingman shows as
it comes; the fake now says `open` too.

**Rejected:** keeping the merge-request create as an option for a platform
without the workflow. Without allocate-segment writing to Git it creates a
file with no segment, and the user asked for one way.

**Verification:**
`apps/day1-service/tests/api/test_provision_workflow_api.py` (every create
starts the workflow with the previewed file; `/clusters/provisioner` is
gone); `apps/day1-service/tests/api/test_cluster_lifecycle.py` (create,
the workflow's merge request holding the name, its merge, an edit and a
delete); `apps/day1-service/tests/unit/test_main.py` and
`tests/unit/test_settings.py` (production refuses to start without the
orchestrator; development stands in the fake);
`tests/repo/test_chart_env_contract.py` and `tests/repo/test_chart_schema.py`
(the chart's refusal, development without it, `day1.provisioner`
accepted and ignored); `apps/web/e2e/tests/provision-workflow.spec.ts` and
`cluster-creation.spec.ts` (Create always shows the run).
