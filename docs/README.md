# Wingman's docs

Where each document lives, and when to read it.

## Start here

| Read | When |
|---|---|
| [README.md](../README.md) | First: what Wingman does, its features, every API route and every setting |
| [architecture.md](architecture.md) | Before your first change: the processes, the systems around Wingman, auth, the layers, how a read and a write travel |
| [DEVELOPMENT.md](../DEVELOPMENT.md) | To run the stack locally, add an endpoint, run the tests |
| [deploy/helm/wingman/README.md](../deploy/helm/wingman/README.md) | To install or configure the chart |
| [apps/web/README.md](../apps/web/README.md) | To work on the web app (and [apps/web/AGENTS.md](../apps/web/AGENTS.md): Next.js 16 differs from older docs) |
| [CLAUDE.md](../CLAUDE.md) | If you are an agent: the standing conventions, the traps and where the work stands |

## adr/: the decisions

[adr/README.md](adr/README.md) lists every decision in one line, with the
template for a new one.

- **What**: one file per decision, numbered, with its context, the
  alternatives rejected and the test that pins it. A decision that changes is
  amended or superseded in place, never deleted.
- **Read it** before changing behaviour an ADR covers, and to learn why
  something is the way it is: the other docs cite ADRs rather than repeat them.
- **Gaps**: 0046, 0049 and 0051 were numbers reserved for planned work in
  [ideas/single-pane.md](ideas/single-pane.md) and have no file. The single
  pane's groundwork was decided in ADR-0047; cluster-navigator's data and RBAC
  get an ADR when they are built.

## ecosystem/: the platform around Wingman

| File | What it holds |
|---|---|
| [ecosystem/README.md](ecosystem/README.md) | The map of the team-redbull platform as read on 2026-11-07: who owns which data, how a cluster is created, the day1 values contract, the day2 layout, the team's open questions. Dated corrections mark what changed since |
| [ecosystem/notes/](ecosystem/notes/) | One study per system, each at the commit it read: server-scan, segments-manager, workflows (with the orchestrator's OpenAPI), hosted clusters and the chart, HyperShift's node state, day2 and KubeVirt (2026-10-22), the KubeVirt platform's model, names and procedures ([kubevirt-platform.md](ecosystem/notes/kubevirt-platform.md), 2026-11-23), and Wingman itself before the rewrite |

Read it before changing day1 or day2, or before calling a platform system.

## integrations/: the systems whose APIs Wingman follows

| File | What it holds |
|---|---|
| [integrations/server-scan.md](integrations/server-scan.md) | What Wingman reads from server-scan (the fleet rows and one server) and never does, the version it matches, where that code lives, the checklist for a new release, known gaps |
| [integrations/segments-manager.md](integrations/segments-manager.md) | The same for segments-manager (one segment, and links to its UI) |
| `integrations/<system>.yaml` | The map: each Wingman file and the upstream files it follows, the version Wingman matches (`synced_at`), what to watch and what is not followed. `scripts/upstream_diff.py <system>` reads it to list what changed upstream since |

Read it before bringing Wingman to a new release of either system, or before
reading more of one.

## ops/: operating a deployment

| File | What it holds |
|---|---|
| [ops/images.md](ops/images.md) | The three images and the nginx image: how they are built, pinned and published; read-only roots |
| [ops/metrics.md](ops/metrics.md) | The metric catalogue (names and labels are a contract, ADR-0010), the ServiceMonitor, alerts and the Grafana dashboard |
| [ops/runbook.md](ops/runbook.md) | One section per alert: what it means and what to do |
| [ops/performance.md](ops/performance.md) | Where a page's time goes, and the commands to measure it in a deployment |

## upgrade/: upgrading a deployed Wingman

[upgrade/README.md](upgrade/README.md) lists every release and says which ones
need operator steps; each of those has a guide (`<from>-to-<to>.md`), written
for an agent or a person inside the disconnected environment, with the checks
before, when to stop, and how to go back. Moving from the legacy services:
[upgrade/legacy-to-ecosystem.md](upgrade/legacy-to-ecosystem.md). Read the row
of every release between yours and the target. The hostedclusters-setup chart
patches Wingman needs, and how to apply and check them:
[upgrade/patches/hostedclusters-setup/README.md](upgrade/patches/hostedclusters-setup/README.md).

## ideas/: what could come next

[ideas/README.md](ideas/README.md) lists each idea with its status (decided,
proposed, blocked, parked, built). Read
[ideas/architecture-fit.md](ideas/architecture-fit.md) first: it is how the
team's architect divides the work between the systems. The decided plan for
one place for the platform is [ideas/single-pane.md](ideas/single-pane.md). An
idea is not a plan: it becomes work when it is decided, and its decision then
goes into an ADR with the code.

## notes/: the record

| File | What it holds |
|---|---|
| [notes/session-log.md](notes/session-log.md) | Every unit of work, newest first: what was built, released and left next |
| `notes/<date>-<topic>.md` | Most of the rest: a feature's web-visible API, or what changed in it, as it was when built (the day1 and day2 rewrites, each area's contract), for the web and for reviewers |
| `notes/2026-11-07-quality-bar-*.md` | The study of server-scan and herzi that set Wingman's quality bar |

Notes are history: they say what was true when they were written. For today,
read the code, the README's API Reference and the ADRs.

## Keeping the docs true

- Docs change in the same commit as the code; a new decision gets an ADR.
- `tests/repo/test_web_docs_contract.py` checks that the root README,
  DEVELOPMENT.md, the chart and web READMEs, `ops/` and `architecture.md` name
  only routes, settings, error codes and Helm keys that exist, and that the
  README lists every route and setting.
- `tests/repo/test_integrations_map.py` checks that every file `integrations/`'s maps
  name exists, and that a file names its map exactly when the map lists it.
- After a change, re-read the docs it made wrong.
