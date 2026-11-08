# Workflow runs on the cluster page

**Status:** proposed.

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

The orchestrator's `upgrade-cluster` workflow is the upgrade flow, so the
flavor doesn't hold the version (flavors-v2.md). On the cluster page:
- the current version and the allowed targets (its upgrade-targets read);
- "Upgrade", which starts a run;
- the run's gates (approve, continue per nodepool, confirm day2) as buttons, admin only.

The confirm-day2 gate is where add-on compatibility can be checked before
day2 continues.

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
