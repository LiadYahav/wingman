# Session log

Newest first. Each entry is the "Where to continue right now" section of
`CLAUDE.md` as it stood when the next unit of work started. Together with
`git log` and the ADRs each entry names, this is the record of the work.

**2026-11-12 — create from a flavor: a sizing ratio, a suggested name, letter sequences (ADR-0040).**
PR #27 on `roiblum/feat-create-from-flavor` (built by a fork, reviewed here;
API: `docs/notes/2026-11-12-create-from-flavor-api.md`). A flavor may size
its nodepools by `spec.day1.nodepool_ratio` (`[1, 2, 1]`): the create form
asks for one size and the file gets plain `replicas`. Creating from a
flavor, the form fills in `ocp4-<env>-<flavor>-<site>-<letter>` from
`GET /clusters/name-suggestion` (the next letter no cluster file or open
create MR has; editable). A new cluster's sequence is one letter a-z; a
name without one is still accepted. The MCE's InfraEnv list is cached
(`MCE_INFRAENV_CACHE_SECONDS`, 600). Before it: 3.4.1 (#25, the add-on
catalog beside a long selection) and 3.5.0 (#26, the EPG from
segments-manager, ADR-0039; upgrade `docs/upgrade/3.4-to-3.5.md`).

**Next:**
- merge PR #27 (3.6.0; no operator steps);
- the speed fork (`roiblum/perf-shared-cache`) reports why loading is slow
  in production and what it fixed: review it and open its PR;
- left for later in ADR-0040: drift, import and sync of a ratio, resizing an
  existing cluster; whether a new cluster must have a letter;
- after deploying, check the Nodes tab and the EPG on a real cluster;
  flavors v2's "Left for later"; the architect's answers.

**2026-11-12 — the cluster's EPG from segments-manager (ADR-0039), 3.5.0.**
On `roiblum/feat-cluster-segment`. The cluster page's "HostedCluster &
network" card shows VLAN and Segment from the cluster file (`vlanId`,
`dhcp_values.network` as its /24: Git is the source of truth) and the EPG
segments-manager records for that segment (`GET /clusters/{name}/network`,
`docs/notes/2026-11-11-cluster-network-api.md`). Where segments-manager
disagrees with the file (VLAN, holder, status, no such segment), the card
warns; it never changes what is shown. `SEGMENTS_MANAGER_URL` (chart
`segmentsManager.url`) turns it on; `DAY1_FAKE_FLEET` fakes it from
`dev/fleet-fixtures/segments.yaml`. Upgrade: `docs/upgrade/3.4-to-3.5.md`.
3.4.0 and 3.3.1 are released; PR #25 (3.4.1, the flavor editor's add-on
catalog beside a long selection) is open.

**Next:**
- merge PR #25, then this one; two forks are working on their own branches
  and report for review: `roiblum/feat-create-from-flavor` (nodepool ratio
  in a flavor, InfraEnvs from the MCE, auto name with a letter seq) and
  `roiblum/perf-shared-cache` (why loading is slow; caches per replica);
- after deploying, check the Nodes tab and the EPG on a real cluster;
- flavors v2's "Left for later"; the architect's answers.

**2026-11-11 — 3.3.1 template fix; nodes by NodePool and node uninstall (ADR-0038).**
PR #23 (3.3.1): network templates are `nm-conf-template-<hw>.bu`, the CI's
name; 3.3.0 wanted `-hw-` and refused every network config (ADR-0027's
correction). Then, on `roiblum/feat-cluster-nodes` (a backend and a web agent
against `docs/notes/2026-11-11-cluster-nodes-api.md`, redesigned once by the
user):
- the cluster page's Nodes tab shows each NodePool from the MCE: its nodes
  (Machine → AgentMachine → Agent → BareMetalHost = server-scan's server),
  each missing piece and why, and which node an update is working on; servers
  server-scan lists that no Machine has sit apart. Nothing on the cluster list.
- Uninstall beside a node starts the platform's `uninstall-server-from-hc`
  and shows its run. Wingman only triggers and shows: the procedure and its
  checks are the workflow's.
- In-place updates: the MCE shows progress, the rebooting node and a failed
  one, never the drain before a reboot (`docs/ecosystem/notes/hypershift-node-state.md`).
  The guest Nodes would need each cluster's admin kubeconfig: not done.
- The MCE token needs more reads (the API note's §4, `docs/upgrade/3.3-to-3.4.md`).
  `DAY1_FAKE_FLEET=true` (development) fakes server-scan, the orchestrator and
  the MCE for demos.

**Next:**
- merge PR #23 (3.3.1), then the nodes PR (3.4.0); deploy with the 3.3→3.4 guide;
- check the workflow class name `UninstallServerFromHcWorkflow` (the runs list
  answers `[]` for any unknown type) and the MCE reads against a real hub;
- flavors v2's "Left for later"; the architect's answers.

**2026-11-08 — flavors v2, all stages, on `roiblum/feat-flavors-v2`.**
Main merged in (the branch's ADRs 0033/0034 became 0036/0037; the import asks
`changed_since`, ADR-0035). Day1: sync (`POST /clusters/{name}/sync[/preview]`,
removals confirmed, how each nodepool rolls), `owner` on cluster rows,
`enforced_locks` on flavors. Web (four parallel agents, then merged): the
flavor editor, the create form, the flavor page with import, value drift and
the sync dialog, owner filters; the UI says Flavor. Checked: the gate, 283
mocked E2E, the three live suites on the reseeded GitLab CE, and
`day1_live_e2e.py` (import and sync against real GitLab). Upgrade guide:
`docs/upgrade/3.2-to-3.3.md`.

**Next:**
- merge the PR (release 3.3) and deploy with the upgrade guide;
- flavors v2's "Left for later" (`docs/ideas/flavors-v2.md`);
- day1's first cluster list after a merge still costs one history lookup per
  cluster (ADR-0035, Consequences);
- the architect's answers (`docs/ideas/architecture-fit.md`).

**2026-11-08 — PR #20 released 3.1.0; repos read once per commit (ADR-0035).**
PR #20: a renamed chart repo no longer fails the catalog (`get_project` follows
GitLab's rename redirect, `chart-repo-unreadable`, `repourl-moved` on the Lints
page); the ladder is read without `schemaVersion`; CI retries tool downloads.
Then, on `roiblum/feat-repo-snapshots` (the user chose it):
- `GitLabPort.get_branch` and `read_archive`, with `RepoSnapshots` in core;
- day1 and day2 read files and trees through them;
- a read's `last_commit_id` is now the commit read at (see the key facts);
- day1's stale check asks `changed_since`, and "changed by" comes from
  `last_change`.
Old and new answers were compared on scaled local data and are identical.

**Next:**
- day1's first cluster list after a merge still costs one history lookup per
  cluster; carry unchanged files forward from a compare (ADR-0035,
  Consequences);
- flavors v2 on `roiblum/feat-flavors-v2`: stage 2's sync is half done in the
  worktree `agent-a35695ba357fd9bb2` as a WIP commit; then stage 3, the web
  pages and the flavor page redesign (apple-design skill); an upgrade guide
  for its operator steps. Merge main into it first: its ADRs 0033 and 0034
  collide with main's and become 0036 and 0037.

**2026-11-08 — releases 3.0.1 to 3.1.0: numbering, status, chart move, two
production bugs.** 3.0.1 versions every release from its commits (ADR-0031);
3.0.2 reads the HostedCluster `ocp4-<clusterName>` (ADR-0015 correction) and
moves the chart to `deploy/helm/wingman/`. PR #20 (3.1.0):
- a renamed chart repo no longer fails the whole catalog: `get_project`
  follows GitLab's rename redirect, an unreadable chart repo is that chart's
  `chart-repo-unreadable`, and the Lints page flags every `repourl-moved`;
- the upgrade ladder is read without `schemaVersion`, as production writes it
  (ADR-0034 correction).

**Next:**
- the user decides on reading each repo once per commit
  (`docs/ideas/repo-snapshots.md`);
- flavors v2 on `roiblum/feat-flavors-v2`: stage 2's sync is half done in the
  worktree `agent-a35695ba357fd9bb2` as a WIP commit; then stage 3, the web
  pages and the flavor page redesign (apple-design skill); an upgrade guide
  for its operator steps. Merge main into it first; watch ADR numbers.

**2026-11-08 — PR #17 finished and merged; flavors v2 started.** The web
followed both API notes; report-only drift (ADR-0025); the in-app docs
audited and guarded (`tests/repo/test_web_docs_contract.py`); UX basics; a
cleanup and review pass (legacy package gone, duplicates in core, the
agents' mistakes fixed); the delete-cluster workflow contract (ADR-0033);
versions from the upgrade ladder. The user's decisions are in
`docs/ideas/flavors-v2.md` and `architecture-fit.md`. **Next:** flavors v2 on
`roiblum/feat-flavors-v2`:
- stage 2's sync, half done in the worktree `agent-a35695ba357fd9bb2` as a
  WIP commit;
- stage 3, the web pages and the flavor page redesign (apple-design skill);
- an upgrade guide for its operator steps.

**2026-11-07 — integration of day1, day2 and CI.** Branch
`roiblum/feat-ecosystem-day1-day2`. Merged the three agent branches: day1
(`wingman_day1`, ADRs 0012-0019), day2 (`wingman_day2`, ADRs 0020-0024) and
CI (ADRs 0030-0032). Session tokens now expire by the injected clock. Every
Python package is on the strict bar (`scripts/python-packages.sh`). Run
locally: day1 `uv run uvicorn wingman_day1.main:app --port 8001`, day2 `uv run uvicorn
wingman_day2.main:app --port 8002` (env in each `settings.py`; both read
`GITLAB_TOKEN`; `WINGMAN_ENVIRONMENT=development WINGMAN_GIT_BACKEND=fake`
for the fixtures). **Next:** the web pages for both API change notes
(`docs/notes/2026-11-07-day{1,2}-api-changes.md`), the chart env, an
end-to-end run of the whole stack. **Deferred:** ArgoCD sync/status (no Argo
API access), `exclusions.yaml` edits, OCP-version pin MRs. **Open:** team
questions 2 (`clusterName`) and 3 (off-convention MCEs) in
`docs/ecosystem/README.md`.

**2026-11-07 — the day2 rewrite.** Branch `worktree-agent-a2d6d3b83dd18abaf`
(on `706935d`). `apps/day2-service/src/wingman_day2` replaces the legacy
service: four destination kinds discovered from team folders plus day1, the
platform's value stacks with per-key provenance, install/update/remove/bulk as
one MR per team (no per-cluster `targetRevision` unless an emergency pin is
asked for; removal orphans the workload, and says so), render_chain.py's lints
plus Wingman's, approvals by `(team, iid)` (ADRs 0020-0024). An oracle test
runs the team's own `render_chain.py` (vendored, with the platform charts,
through helm) against Wingman's discovery. Run it with
`uv run uvicorn wingman_day2.main:app --port 8002` from the repo root; env in
`wingman_day2/settings.py` (`GITLAB_TOKEN`, not `GITLAB_ACCESS_TOKEN`;
`DAY1_GITLAB_PROJECT_ID`; `WINGMAN_GIT_BACKEND=fake` for the fixtures).
**Next:** the web pages for the new API
(`docs/notes/2026-11-07-day2-api-changes.md`); the chart passes
`GITLAB_ACCESS_TOKEN` where wingman-core reads `GITLAB_TOKEN`. **Deferred:**
ArgoCD sync/status (no Argo API access), editing `exclusions.yaml` (needs
comment-preserving YAML), OCP-version pin edits as first-class MRs.

**2026-11-07 — day1 on `wingman-core`.** Branch
`worktree-agent-a8c8a548e56c6a474` (to merge into
`roiblum/feat-ecosystem-day1-day2`). `apps/day1-service/src/wingman_day1`
replaces the legacy `src/`: values file from the shared template in a
sandbox, naming rules, read-only sites/MCEs with default `mastertag` and hub
version, `ClusterProvisioner` (MR today), approvals on core `Approvals`
with the reviewed head, hub/OAuth/day2 over httpx behind ports (ADRs
0012-0019). Run locally: `WINGMAN_ENVIRONMENT=development
WINGMAN_GIT_BACKEND=fake JWT_SECRET_KEY=<32+ chars>
DAY1_GITLAB_PROJECT_ID=gitops-day1/platform-config
SPECS_GITLAB_PROJECT_ID=wingman/cluster-specs DEV_AUTH_ENABLED=true
DEV_AUTH_SECRET=<32+ chars> uv run uvicorn wingman_day1.main:app --port 8001`;
against local GitLab: `uv run python scripts/dev/day1_live_e2e.py --token
<local token> --sandbox-chart <chart dir>`. **Next:** the web changes in
`docs/notes/2026-11-07-day1-api-changes.md` and the chart's day1 env.
**Open:** the off-convention MCE rule (ADR-0014) waits on team question 3;
the default `clusterName` rule (ADR-0015) on question 2.

**2026-11-07 — the `wingman-core` foundation.** Branch
`roiblum/feat-ecosystem-day1-day2`. Shipped the core package (ADRs
0001-0010), CI and the gate, local GitLab scripts and the seeded fixtures.
**Next:** rewrite day1 on the core against `gitops-day1/platform-config`
(values file from the new template, naming rules, read-only sites/MCEs, read
`mastertag`/nodepools/VLAN, status names, MR branches that CI commits to), and
in parallel day2 against the gitops-day2 layout (four cluster kinds, defaults
and exclusions, the 10-layer values merge, version pins). **Open:**
production vs sandbox `clusterName`, canonical site codes and InfraEnv naming
(questions in `docs/ecosystem/README.md`).

**2026-11-07 — ecosystem map, the new day1 template, the UI refresh.**
`docs/ecosystem/` maps server-scan, segments-manager, the Temporal workflows,
herzi, the hostedclusters-setup chart, gitops-day2 and kubevirt-workflows,
and how Wingman fits them. The new `cluster-template.j2` renders the slim
values file and was checked with `helm template` against both chart copies.
Earlier the same day: the dark-first UI refresh (PR #16) and the legacy
Playwright specs fixed.
