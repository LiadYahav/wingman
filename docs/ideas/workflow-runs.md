# Workflow runs on the cluster page

**Status:** proposed. Checked against [architecture-fit.md](architecture-fit.md):
workflows own every multi-step operation; Wingman starts the customer ones
and shows them.

## The problem

When a cluster MR waits, the reason is often outside GitLab:
- the allocate-segment workflow hasn't written `vlanId` yet;
- the platform-config pipeline failed;
- later, the `create-cluster` workflow stopped on a check such as "not enough free hosts in the InfraEnv".

Today the user has to find the run in the Temporal UI.

## Proposal

A narrow view of the workflows that act on one cluster, read through a new
port (`WorkflowRuns`) with an adapter for the orchestrator API and a fake. It
is not a second Temporal UI:

| Wingman does | Wingman doesn't (the Temporal UI does) |
|---|---|
| Show this cluster's runs on the cluster page | List every workflow in the system |
| Show status, the current step and the error in plain words | Show event history, retries, workers or queues |
| Link "details" to the Temporal UI for that run | Replace the Temporal UI |
| Show the buttons a run waits on (approve, continue) to admins | Terminate or reset arbitrary runs |

Next to the runs, the MR's GitLab pipeline status: the platform-config CI
renders and validates every cluster file, so its result is the "does it
render" check.

## OCP upgrades

The flavor doesn't hold the version (flavors-v2.md). Upgrades are workflows,
and the architecture splits them on purpose: the control plane first
(procedure 14), then the workers per node type (procedure 13), so a slow
workload drain can never hold the API back. The tenant chooses the window.
On the cluster page:
- the current version and the allowed targets (the orchestrator's
  upgrade-targets read; a hosted cluster can't go beyond what its MCE
  supports);
- "Upgrade control plane", then "Upgrade workers" per node type, each
  starting a run;
- a run's gates (approve, continue) as buttons, admin only.

The workers' run checks that the pool can supply the surge nodes; Wingman
shows its refusal, it doesn't check. A version the MCE can't reach is a
version band move (procedure 18), which is a rebuild on another MCE, not an
upgrade.

The sandbox's `upgrade-cluster` workflow (one run with human gates) and
procedures 13 and 14 differ; which one Wingman drives is a question for the
architect (architecture-fit.md).

## The merge

Every customer workflow ends its Git part with "merge to main" by a person.
Wingman's approvals page already reviews and merges day1 and day2 MRs, so a
workflow's branch can be reviewed there too: the diff, the pipeline, the
run that wrote it. Whether the merge for workflow branches happens in Wingman
or in GitLab is a question for the architect.

## Open questions

- **Finding a cluster's runs.** The runs list filters only by workflow type,
  so a per-cluster view has to filter on the run-id prefix, for example
  `allocate-segment-HC-<cluster>`. A cluster filter in the orchestrator is
  cleaner: it also covers runs Wingman didn't start.
- **Auth.** The orchestrator has no authentication (accepted 2026-11-07,
  CLAUDE.md convention 13). Every action Wingman starts there is admin-only
  (`AdminUser`) and goes to the audit log.
- **The Temporal UI link.** Its address comes from settings, never from the
  repo.
