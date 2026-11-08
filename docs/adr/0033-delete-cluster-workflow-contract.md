# ADR-0033: The delete-cluster workflow has a contract before it exists

Date: 2026-11-08
Status: Accepted

## Context

Deleting a cluster opens an MR that removes its file (ADR-0017). That is
not a full teardown: the cluster's network segment is never released.
Releasing it belongs to the planned delete-cluster workflow (user decision
2026-11-08; `docs/ideas/architecture-fit.md`). That workflow owns the order:
drain, remove the files, wait for ArgoCD to prune, wait for the released
nodes to be wiped, delete the DHCP scope, and release the segment last. The
user asked for the web to be ready for it now, saying "not available yet"
until it exists.

## Decision

- A port, `ClusterDeleteWorkflow`, with two calls: `latest_run(ref)` and
  `start(ref, requested_by=...)`. A run is a `WorkflowRun`: id, status,
  phase, error. Only data crosses back.
- Two routes:
  - `GET /api/day1/clusters/{name}/delete-workflow`, for any signed-in user, returns `{"run": ...}`;
  - `POST /api/day1/clusters/{name}/delete-workflow`, admin only, takes `{"confirm": true}`
    and returns 202 with the run. The workflow's own input requires an explicit confirm,
    because the delete can't be undone.
- **Until an adapter exists, the context has none, and both routes answer 501
  `FEATURE_DISABLED`** with "not available yet" and what deleting does
  meanwhile. This is the same pattern as live status when it is off.
- The web asks the GET route. A 501 shows the workflow as "Not available
  yet", with its steps and a disabled button. Anything else shows the run,
  or a Start button for admins. Turning it on is an adapter (the
  orchestrator, through a port and a fake, like GitLab) and a line in
  `main.py`; the web doesn't change.

## Alternatives rejected

- **A web-only flag.** Turning it on would need a web rebuild, and the web
  would guess what the backend can do.
- **Releasing the segment from Wingman after the delete MR merges.** That
  would release it before ArgoCD has pruned and before the DHCP scope is
  gone; the order belongs to the workflow.

## Consequences

- The MR delete stays as it is until the adapter lands. Then the workflow
  replaces it for clusters it can delete.
- The run's statuses and phases are the orchestrator's strings, passed
  through. When the workflow exists, its real phase names replace the ones
  the web lists today (`docs/ideas/architecture-fit.md`).
