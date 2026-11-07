# CLAUDE.md

Orients a Claude Code session on this repo. `README.md` is the human
quickstart; `docs/ecosystem/README.md` is how Wingman fits the team-redbull
platform (read it before changing day1 or day2); `docs/adr/` holds the
decisions and their reasons; `docs/ops/` holds the operator contracts
(metrics). The session history is `docs/notes/session-log.md`. Personal,
untracked notes (live sandbox URLs, local tokens) are in `CLAUDE.local.md`.
This file is loaded every session, so it stays short.

## What this is

Wingman is the team's self-service portal for OpenShift hosted clusters:
day1 (create, edit, delete a hosted cluster) and day2 (install and configure
charts on clusters). GitLab is its only store: every change is a merge request
into the day1 values repo (`gitops-day1/platform-config`) or a team's day2 repo
(`sigs/<team>`), and ArgoCD applies what is merged. It was written before the
ecosystem it now has to fit (server-scan, segments-manager, Temporal
workflows, herzi, the hostedclusters-setup chart, the reworked gitops-day2
layout); the rewrite is in progress (see Current status).

Monorepo: `apps/web` (Next.js 16), `apps/day1-service` and
`apps/day2-service` (FastAPI), `packages/wingman-core` (the new shared core),
`packages/shared-python` (legacy shared code, being replaced), `chart/`
(Helm), `dev/gitlab-fixtures` (production-shaped repo trees for tests and
local GitLab).

## Standing project conventions — follow without being re-told

Explicit user instructions; violating one is a real mistake, not style.

1. **The quality bar is server-scan and herzi** (the team's best repos, in
   team-redbull). New code, tests, CI, docs and repo hygiene must not be below
   them. When unsure how to do something, look at how they do it.
2. **Git: commit and push after each completed stage**, on a feature branch,
   with Conventional Commit subjects (`feat:`, `fix:`, `docs:`, `ci:`,
   `test:`, `refactor:`). One unit of work per commit. Never push to `main`
   directly; merges go through a PR.
3. **This repo is public.** Never commit live URLs, tokens, internal hostnames,
   or findings about private systems (e.g. the production export in
   `~/Downloads/stack-export`). Put them in the git-ignored `CLAUDE.local.md`.
4. **Layers are enforced** (ADR-0001): domain → ports → application →
   infrastructure/observability → web. `uv run lint-imports` must pass. New
   external systems get a port, an adapter and a fake; never a client call
   from a router.
5. **GitLab only through `GitLabPort`** (ADR-0002). New code never imports
   python-gitlab or `wingman_shared.gitlab_client`.
6. **Writes are guarded and never retried** (ADR-0006): updates carry the
   read's `last_commit_id`, merges carry the reviewed `sha`, and an
   `AmbiguousWriteError` is surfaced, not retried.
7. **An MR is `(project, iid)`** and the branch/title/description formats in
   `wingman_core.domain.mr_conventions` are a contract (ADR-0007).
8. **Errors are RFC 9457 problems** (ADR-0004). Raise `AppError` subclasses;
   never `HTTPException`; never swallow a read error.
9. **Metrics names and labels are a contract** (ADR-0010,
   `docs/ops/metrics.md`). No unbounded label values.
10. **Exact pins, one lockfile** (ADR-0003). `uv sync --locked` must pass. No
    Dependabot/Renovate.
11. **Docs change in the same commit as the code.** A new decision gets an ADR
    (template in `docs/adr/README.md`); a superseded one is marked, never
    deleted.
12. **Use parallel agents** where work splits into independent pieces.
13. **Wingman owns day1 until the planned `create-cluster` workflow exists**
    (user decision 2026-11-07). Keep provisioning behind an adapter so it can
    switch to starting the workflow. The orchestrator API has no auth; that is
    accepted.
14. **Site and MCE are read-only in Wingman** (user decision 2026-11-07).
    Wingman never creates them; MCE onboarding happens elsewhere.
15. **Don't add network policies** — they cause connectivity issues.

## Current status

- Done: ecosystem map (`docs/ecosystem/`); the new day1 template
  (`dev/gitlab-fixtures/wingman/cluster-specs/cluster-template.j2`, verified
  with `helm template` against both chart copies); fixtures; the
  `wingman-core` foundation (GitLab port, httpx adapter, in-memory fake,
  contract suite passing 27/27 on the fake and on GitLab CE 19.5.3, RFC 9457
  errors, metrics, settings, auth, cache, approvals); CI and
  `scripts/gate.sh`; ADRs 0001-0011; monitoring in the chart (ServiceMonitor,
  7 promtool-tested alerts with a runbook, a Grafana dashboard, all off by
  default) with a test tying alerts and dashboard to the metric catalogue;
  the day2 rewrite (`wingman_day2`: four destination kinds, fleet defaults
  and exclusions, the platform's value stacks with provenance, lints, MRs per
  team; ADRs 0020-0024; an oracle test against the team's `render_chain.py`;
  run against GitLab CE 19.5.3).
- **Not done yet, in order:** (1) day1 rewrite on `wingman-core` against
  `gitops-day1/platform-config`; (3) web pages for the new data (day2's API
  changes are listed in `docs/notes/2026-11-07-day2-api-changes.md`); (4)
  end-to-end check against the seeded local GitLab; (5) images installing from the lock (hash-pinned
  per-service exports), chart hardening and a values schema; (6) ecosystem features (servers per hosted cluster from
  server-scan, workflow runs).

## Key technical facts (cross-cutting traps)

- **Every file in `sites/<site>/mces/<mce>/hostedClusters/` becomes an ArgoCD
  Application**, and an empty one fails the generator. Never write a
  placeholder (`.gitkeep`) or sidecar there. The legacy MCE-create path did.
- **The cluster file is a values file** for the hostedclusters-setup chart:
  `owner`, `mastertag`, `nodepool[]` (`infraEnvName`, `replicas`, `labels`,
  `configs`). `vlanId` and `dhcp_values` are written by the allocate-segment
  workflow on the MR branch; `mcFiles`/`mcConfigMap` by CI. Wingman writes
  none of them, and must expect those commits on its MR branches.
- **`clusterName` differs**: production's ApplicationSet strips `ocp4-` from
  the file name (`openshift-prod-x-site1` in `hcp-prod-x-site1`); the GitHub
  sandbox keeps it. See `docs/ecosystem/README.md`.
- **Naming convention** `ocp4-<env>-<name>-<site>[-<seq>]`; the chart derives
  the day2 `<env>` from the MCE name and fails on names that don't follow it.
- **GitLab is asynchronous in places**: an MR's stored diff and its
  mergeability are computed by background jobs, and a merged source branch is
  deleted later. The adapter handles the first two; don't assume the third.
- **ty honours only `# type: ignore` or `# ty: ignore[rule]`**, never a
  mypy-style `# type: ignore[code]` (ADR-0008).
- **Next.js 16 / React 19 / Tailwind 4 / zod 4** differ from older docs. Read
  `apps/web/AGENTS.md` and `node_modules/next/dist/docs/` before frontend edits.
  `apps/web/proxy.ts` replaces middleware.

## Verifying your work

```bash
uv sync --locked --all-packages --all-groups --all-extras
scripts/gate.sh                    # everything CI runs, in CI's order
scripts/gate.sh python             # only the Python half

# Real GitLab (podman; ~8 GB VM, see the script header)
scripts/dev/gitlab-up.sh token     # start local GitLab CE 19.5.3 and make the dev token
uv run python scripts/dev/seed_gitlab.py --token wingman-local-dev-token-0001
WINGMAN_TEST_GITLAB_URL=http://localhost:8929 WINGMAN_TEST_GITLAB_TOKEN=wingman-local-dev-token-0001 \
  uv run pytest -m live_gitlab     # the GitLab contract against real GitLab

# A day1 cluster file through the chart, as ArgoCD renders it
helm template <cluster> <chart-dir> -f sites/configValues.yaml -f sites/<site>/values.yaml \
  -f sites/<site>/mces/<mce>/values.yaml -f <cluster-file> --set-string clusterName=<cluster>,site=<site>,mce=<mce>
```

Web: `npm run lint --workspace=web`, `cd apps/web && npx tsc --noEmit`,
`npm run build --workspace=web`. Playwright: `cd apps/web && npm run test:e2e`
runs every spec, including `live-*` ones that need a backend; the mocked ones
are `user-flows.spec.ts` and the page-object specs. Playwright traps: route
mocks match LIFO; SSE keeps the network busy, so wait on `domcontentloaded`,
never `networkidle`; any unmocked endpoint's 401 redirects to `/login`.

Then the step no command covers: re-read the docs your change made wrong.

## Legacy services (until rewritten)

- Run from the service dir: `uv run uvicorn src.main:app --reload --port 8001`
  (day1) / `8002` (day2); imports are relative.
- Required env: `GITLAB_URL`, `GITLAB_ACCESS_TOKEN`, `JWT_SECRET_KEY`; day1
  `DAY1_GITLAB_PROJECT_ID`, `SPECS_GITLAB_PROJECT_ID`; day2
  `DAY2_SIGS_GROUP_PATH`. Local login: `DEV_AUTH_ENABLED=true` and a non-empty
  `DEV_AUTH_SECRET` (day1). Full reference: README.md.
- Roles come from OpenShift groups (`WINGMAN_ADMIN_GROUPS` /
  `WINGMAN_VIEWER_GROUPS`) and travel in the app JWT; both services share
  `JWT_SECRET_KEY`. `AdminUser` guards writes, `CurrentUser` reads.
- Images: CI pushes `ghcr.io/<owner>/wingman-{day1,day2,web}` on main with
  `<short_sha>`, `latest`, `v<VERSION>`. Manual production builds are tagged
  with the commit SHA.

## Where to continue right now

**This section holds exactly one entry — the most recent unit of work.** When
you finish yours, move this entry to the top of `docs/notes/session-log.md`
and write yours here.

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
