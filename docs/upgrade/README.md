# Upgrade guides

How to upgrade a Wingman that is already deployed, written for an agent (or
a person) working **inside the disconnected environment**: no internet, no
access to GitHub, and no memory of how this repo was built. Each guide is
self-contained. It says what to check before touching anything, when to
stop and report instead of improvising, and how to go back.

Every release is listed. A release with a guide needs operator steps:
follow the guide. Every other release is the [generic upgrade](#the-generic-upgrade-no-guide):
the new chart and the three images at the new tag, with the values you
already have.

| From | To: what changes | Upgrade |
|---|---|---|
| The legacy services (`src.main:app`, the chart before PR #17) | Any 3.x: the rewrite on `wingman-core` (`wingman_day1`, `wingman_day2`) | [legacy-to-ecosystem.md](legacy-to-ecosystem.md) |
| 3.0.0 | 3.0.1: releases are versioned from their commits (ADR-0031) | Generic |
| 3.0.1 | 3.0.2: live status reads the HostedCluster the chart names, `ocp4-<clusterName>`; the chart moves to `deploy/helm/wingman/` | Generic, with `$CHART` at its new path |
| 3.0 | 3.1: day2 flags moved chart repos; the upgrade ladder is read without `schemaVersion`; a renamed GitLab project is still found | Generic |
| 3.1 | 3.2: the day1, specs and team repos are read once per commit (ADR-0035), so lists load fast | Generic |
| 3.2 | 3.3: flavors v2 (enforced locks, checked machine configs, import and sync) | [3.2-to-3.3.md](3.2-to-3.3.md) |
| 3.3.0 | 3.3.1: network templates are read by the CI's name, `nm-conf-template-<hw>.bu` (3.3.0 refused every network config) | Generic |
| 3.3 | 3.4: a cluster's nodes by NodePool, from its MCE (new read-only MCE grants; optional server-scan and the workflows orchestrator) | [3.3-to-3.4.md](3.3-to-3.4.md) |
| 3.4.0 | 3.4.1: the flavor editor's add-on catalog stays in view beside a long selection | Generic |
| 3.4 | 3.5: the cluster's EPG from segments-manager, checked against the file's VLAN and segment (optional `segmentsManager.url`; no new grants) | [3.4-to-3.5.md](3.4-to-3.5.md) |
| 3.5 | 3.6.0: creating from a flavor: a nodepool sizing ratio, a suggested name with the next free letter, letters-only sequences for new clusters (ADR-0040); the generic network template (ADR-0027's amendment) | Generic. Optional, in the day1 repo, through an MR: add `mc-files/templates/nm-conf-template.bu` to offer the generic network config, which then becomes every nodepool's default. `MCE_INFRAENV_CACHE_SECONDS` (default 600) needs no value |
| 3.6.0 | 3.6.1: pages answer from cache while it refreshes, a merge re-reads only the files it changed, a new pod warms up, responses are gzipped (ADR-0041) | Generic: the chart changes (nginx gzip), so take the chart at `v3.6.1`, not only the images. To confirm the speed-up: [../ops/performance.md](../ops/performance.md) |
| 3.6 | 3.7.0: Create can start the platform's `provision-cluster` workflow instead of opening Wingman's merge request (ADR-0042), off by default | Generic while `day1.provisioner` stays `merge-request`. To turn the workflow on: [3.6-to-3.7.md](3.6-to-3.7.md) |
| 3.7 | 3.8.0: importing existing clusters into a flavor opens one merge request per cluster instead of one for all (ADR-0044); the import's result lists each MR and each cluster whose MR did not open | Generic. Import MRs opened before the upgrade (`Import spec <flavor> into <n> clusters`) stay as they are and can still be merged or closed |

### Skipping versions

Go straight to the newest release, and on the way do every guide whose
row you pass, in order. For example, from 3.3.x to 3.7.0: do
[3.3-to-3.4.md](3.3-to-3.4.md) (the MCE grants), then
[3.4-to-3.5.md](3.4-to-3.5.md) (`segmentsManager.url`, optional), each
with the newest `<tag>` instead of its own, then 3.6.0's optional template,
and 3.6-to-3.7.md only if the team turns the provision workflow on.
Rows marked Generic add nothing. A guide's checks still apply: run them
before its upgrade step.

### The generic upgrade (no guide)

`<ns>`, `<release>`, `<tag>` and `$CHART` mean what they mean in
[legacy-to-ecosystem.md](legacy-to-ecosystem.md): `$CHART` is
`deploy/helm/wingman/` of the repository at `v<tag>`, and the three images
`wingman-day1`, `wingman-day2` and `wingman-web` are in your registry at
`<tag>`.

```bash
helm history <release> -n <ns> | tail -3          # note the current revision, for a rollback
helm upgrade <release> $CHART -n <ns> --reset-then-reuse-values \
  --set image.day1.tag=<tag> --set image.day2.tag=<tag> --set image.web.tag=<tag>
kubectl -n <ns> rollout status deploy -l app.kubernetes.io/part-of=wingman --timeout=5m
```

With Helm older than 3.14, pass the release's values as a file instead
(step 7 of [3.3-to-3.4.md](3.3-to-3.4.md) shows how, without printing
secrets). Then open Wingman, sign in, and open the cluster list and one
cluster. Roll back with `helm rollback <release> <revision> -n <ns>`:
Wingman keeps no state of its own (rule 2 below).

Releases are named by version: from 3.0.1 on, every merge to main is a
release whose version comes from its commits (ADR-0031), and you deploy that
version (`3.6.1`) as the image tag of all three images.

## Rules for every upgrade

1. **Read before you write.** Discover what runs and check every
   precondition before changing anything. Each check names its stop
   condition. When one is hit, stop and report; don't work around it.
2. **Wingman keeps no state of its own.** GitLab is its only store
   (ADR-0002), so a Helm rollback restores the old version. Changes made in
   GitLab (a new template, a moved file) go through an MR, so they can be
   reverted too.
3. **No secrets in output.** Never print a token, a client secret or the
   JWT secret into a log, a report or a file you hand back. Refer to them by
   the Secret's name and key.
4. **One step at a time,** and record what you did, the command and its
   result. That record is the report.
5. **Never create a real cluster to test an upgrade.** Wingman's Preview
   runs every check a create runs, without committing anything.

## Adding a guide

A release that needs operator steps adds a guide here, in the same commit as
the change that needs it. Name the file `<from>-to-<to>.md`, add a row above,
and follow the shape of the existing guide: what changes, what to bring in,
discover, check, change, upgrade, verify, roll back, report.
A release without operator steps adds its row too, marked Generic, so
the table lists every release.
