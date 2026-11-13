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
| 3.7 | 3.8.0: a team creates add-ons, edits their team defaults and sync options, and makes them fleet defaults from Wingman (ADR-0043); day2 writes are per team: a team that does not give Wingman's GitLab account Developer on its project is read-only | [3.7-to-3.8.md](3.7-to-3.8.md) if any team should not, or does not, give Wingman write access; otherwise Generic |
| 3.8 | 3.9.0: **Quick Links** for admins (ADR-0052): every cluster's ArgoCD and console, generated from the day1 repo, the team's links from the chart, status dots checked by day1, ArgoCD counts with read-only tokens | Generic: every MCE is listed when `clusterStatus.mceDomain` is set. To add the hub, the team's links and the counts: [3.8-to-3.9.md](3.8-to-3.9.md) |
| 3.9 | 3.10.0: a flavor's changes reach each cluster through its own merge request (ADR-0044): drift is measured against the version a cluster is on, and a newer one is an update; a new flavor version opens one MR per cluster that follows it, with the day2 add-on MRs that version needs; an import opens one MR per cluster; a flavor edit needs a new version | Generic. After the upgrade, the first rollout trigger (opening a flavor's page, the specs webhook, Reconcile, or merging a flavor MR) opens an MR for every cluster that is behind its flavor's newest version: nothing changes on a cluster until its MR merges, and closing one declines that version. Day1 asks day2 for add-on MRs with an admin service session signed by the shared `JWT_SECRET_KEY` (no new setting); a team that gives Wingman no write access (ADR-0043) gets its add-ons listed in the day1 MR instead. Import MRs opened before 3.10 (`Import spec <flavor> into <n> clusters`) stay as they are |
| 3.10 | 3.11.0: Wingman picks a new cluster's MCE from the site, prod or prep, the version and the owner, and shows every candidate's numbers; an admin may choose another with a reason (ADR-0050). An MCE's API address may be given beside its token (ADR-0045) | [3.10-to-3.11.md](3.10-to-3.11.md) when live status is on: grant each MCE token `list` on nodes and pods **before** upgrading, or that MCE is never picked. With live status off, Generic |
| 3.11 | 3.12.0: an Operators page per team: which destinations each fleet default reaches (`exclusions.yaml`, edited in place), a destination's own values and deploy config; every day2 authoring write lists what it does to each destination and is confirmed against its preview (ADR-0053); a team whose access cannot be read is read-only, the others unaffected | Generic: no new value, Secret, grant or variable. A script that called the 3.8 to 3.11 authoring API without a preview now gets 422 `confirm-changes`/`confirm-against-preview` when the write changes a destination: send the preview's `needs_confirmation` and `digest` |
| 3.12 | 3.12.2: the create form always asks for the site, prod or prep and the version, never the MCE, and Wingman picks it; with live status off placement decides on the day1 repo and server-scan and says the free pods and servers were not checked (ADR-0050's amendment) | Generic |
| 3.12 | 3.13.0: the Operators pages are folded into **Addons**, one place called add-ons (ADR-0053's amendments): the Addons page creates an add-on and edits its team default again, and an add-on's page (`/addons/<team>/<chart>`) has its defaults with values per env and per MCE, hosted cluster or UPI cluster, and **Deploy on specific MCEs** (one install MR per MCE). Wingman no longer writes `exclusions.yaml` or own deploy configs (their two endpoints are gone). 3.12.0's `/operators` and `/teams/<team>/operators…` links redirect; the API's `/teams/{team}/operators` paths stay as aliases of `/teams/{team}/addons` | Generic |
| 3.13.0 | 3.13.1: Wingman made lighter. Quick Links lists links only: no status dots, no ArgoCD counts (ADR-0052's amendment). The Destinations page is removed and `/destinations` opens Clusters; a destination's name on an add-on's page opens its charts (ADR-0020's amendment). `/health/ready` asks GitLab only until it has answered once per pod (ADR-0054) | Generic. Optional clean-up, nothing breaks if skipped: drop the values `quickLinks.status`, `quickLinks.sslVerify` and `quickLinks.argocdTokensSecret` (`--reset-then-reuse-values --set quickLinks.status=null --set quickLinks.sslVerify=null --set quickLinks.argocdTokensSecret=null`), delete the ArgoCD tokens Secret (usually `wingman-argocd-tokens`) and the read-only accounts made for it in each ArgoCD, and remove `ping:` and `argocd:` from the links in `quickLinks.sections` (until then the page names them as unknown keys). A GitLab outage no longer makes the pods unready; it shows on the requests, and a pod that never reached GitLab still never becomes ready |
| 3.13.1 | 3.13.2: the add-on's values are called **Sig values** (chart values → Sig values → cluster values) and Edit team default is **Edit add-on** (ADR-0043's amendment; the API and the merge request titles keep their names); the create form's MCE section is shorter: one row per MCE with its reasons in tooltips, the pick marked on its row, the rule behind an ⓘ | Generic |
| 3.13.2 | 3.13.3: the Addons page answers from cache: day2's chart repo lookups (project, version branches, values) answer stale while one read refreshes them, like every other read (ADR-0041's amendment), so `/addons` stops waiting on GitLab after the first load; links in lists prefetch on hover or focus, not on render, so a page load no longer queues its API calls behind them | Generic |
| 3.13.3 | 3.13.4: a code cleanup with no change in behaviour: unused code and leftovers removed, duplicated helpers merged (one HTTP client builder in day1, one place that opens a day2 merge request, one pagination in the web), turbo removed from the root, and knip in the web lint so unused files, exports and dependencies fail the build | Generic. Building the web image from source needs knip 6.45.1 and its native `oxc` packages in the npm mirror (the build stage installs dev dependencies); the running images are unchanged |
| 3.13.4 | 3.13.5: CI only: the mocked E2E suite runs on two runners with four workers each (a run takes ~3.5 min instead of ~9.5), and a test that passed only on retry is annotated on the run | Generic: the images are unchanged |
| 3.13.5 | 3.13.6: a fix in the read cache: when the first request for a value was cancelled (a page left mid-load, a client timeout), the requests waiting on the same GitLab read failed with it and the read was thrown away; now the read finishes, they get its value and it is kept (ADR-0011's amendment) | Generic |
| 3.13.6 | 3.14.0: Wingman sees the `provision-cluster` workflow's merge request by its branch, `provision-cluster/<stem>` (ADR-0042's amendment), in either provisioner mode: it holds its cluster's name for the name suggestion and the "already being created" check, counts on its MCE for placement, and is listed on Approvals, marked as the workflow's, to review and merge in GitLab (`opened_by_workflow` on `GET /api/day1/approvals`) | Generic: no new value, Secret or grant; Wingman's GitLab token already lists the day1 project's merge requests |

### Skipping versions

Go straight to the newest release, and on the way do every guide whose
row you pass, in order. For example, from 3.3.x to 3.11.0: do
[3.3-to-3.4.md](3.3-to-3.4.md) (the MCE grants, with the ClusterRole of
[3.10-to-3.11.md](3.10-to-3.11.md) step 5 so one apply covers both), then
[3.4-to-3.5.md](3.4-to-3.5.md) (`segmentsManager.url`, optional), each
with the newest `<tag>` instead of its own, then 3.6.0's optional template,
3.6-to-3.7.md only if the team turns the provision workflow on,
3.7-to-3.8.md's discovery (which teams give Wingman write access),
3.8-to-3.9.md for Quick Links' hub and team links (optional; its ArgoCD tokens are gone since 3.13.1),
and 3.10-to-3.11.md's grant check.
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
