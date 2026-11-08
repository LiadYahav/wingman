# Ideas

What Wingman could do next, with the reasons and the decisions they wait on.
An idea here is not a plan: it becomes work when it is decided, and then its
decision goes into an ADR (`docs/adr/`) with the code. The ecosystem map and
the phased plan these build on are in `docs/ecosystem/README.md`.

Wingman's direction: the platform's self-service catalog. It already reads
and writes GitLab (day1 and day2). The rest of the ecosystem (server-scan,
the workflows orchestrator, herzi) is read through a port, an adapter and a
fake, the same way (ADR-0001, ADR-0002). Each check or action stays in the
system that owns it; Wingman shows the result and starts the action. **Read
[architecture-fit.md](architecture-fit.md) first**: it is how the team's
architect divides the work between the systems, and every idea here is
checked against it.

## Status

| Status | Meaning |
|---|---|
| **Decided** | The user chose; the work is planned. The file records the choices. |
| **Proposed** | Worth doing; open questions listed in the file. |
| **Blocked** | Waits on access or on another team. |
| **Parked** | Not now; the reason is given. |

## Index

| Idea | Status | File |
|---|---|---|
| Where Wingman sits in the architecture: who owns what, the rules that follow, questions for the architect | Reference | [architecture-fit.md](architecture-fit.md) |
| Flavors v2: machine configs per nodepool, nodepool defaults, enforced locks, owner numbers, importing existing clusters, a redesigned flavor page | **Decided** 2026-11-08 | [flavors-v2.md](flavors-v2.md) |
| Workflow runs on the cluster page, OCP upgrades (control plane, then workers) and reviewing workflow branches | Proposed | [workflow-runs.md](workflow-runs.md) |
| Servers per hosted cluster from server-scan, why a cluster waits for workers, and moving capacity between clusters | Proposed | [servers-and-nodes.md](servers-and-nodes.md) |
| Day2 permissions per team: a team edits only its own `sigs/<team>` repo | Proposed | [day2-team-permissions.md](day2-team-permissions.md) |
| ArgoCD sync and health per cluster | Blocked: Wingman has no ArgoCD access; open question 10 in the ecosystem README (do day1 Applications sync automatically?) | — |
| Release the network segment when a cluster is deleted (start `release-segment` after the delete MR merges) | **Dropped** (user, 2026-11-08): the delete-cluster workflow releases it, as allocation belongs to the day1 workflow; not Wingman's. It releases last, after ArgoCD has pruned and the DHCP scope is gone (architecture-fit.md) | — |
| KubeVirt self-service (`create-vm` and the tenant flows) | Parked until day1 settles (ecosystem plan, phase 5) | — |
| Rendered preview of a cluster file before the MR | Parked: rendering the values through the chart belongs to the platform-config CI, which runs for every MR whether Wingman opened it or not. Wingman shows that pipeline's result (see workflow-runs.md) | — |
| Node-availability check before create (enough free hosts in the InfraEnv) | Belongs to the create workflow's admission step (not built yet); create never waits for supply. Wingman shows the answer, and a waiting cluster's pool state (servers-and-nodes.md) | — |
| Edit `exclusions.yaml` from the UI | Parked: deferred since the day2 rewrite; few edits a year | — |
| Bulk operations (replicas or an add-on version across many clusters in one MR) | Parked: undecided; flavors v2 sync covers the common case. If built: totals, never deltas | — |
| Notifications (an MR needs approval, was approved, failed) | Parked | — |
| Chart hardening (a values schema, a pinned nginx image) | Parked: undecided | — |
| Team questions on `clusterName` and off-convention MCEs | Parked: open questions 2 and 3 in the ecosystem README | — |

## Adding an idea

One file per idea that needs more than a line: the problem in a sentence,
the proposal, what it reads or writes, the open questions, and what it waits
on. Short ones get a row in the index. When an idea is decided, record the
choices and the date in its file; when it ships, its ADR supersedes the
file, and the row links to the ADR.
