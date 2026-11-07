# Session log

Newest first. Each entry is the "Where to continue right now" section of
`CLAUDE.md` as it stood when the next unit of work started. Together with
`git log` and the ADRs each entry names, this is the record of the work.

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
