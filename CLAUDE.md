# CLAUDE.md

Orients a Claude Code session on this repo; loaded every session, so it holds
only what an agent would get wrong without it. Start with
[docs/README.md](docs/README.md) (where every doc lives) and
[docs/architecture.md](docs/architecture.md) (the processes, the systems
around Wingman, the layers). `README.md` is the human quickstart,
`DEVELOPMENT.md` the developer guide, `docs/ecosystem/README.md` how Wingman
fits the team-redbull platform (read it before changing day1 or day2). A
release that needs operator steps adds a guide to `docs/upgrade/`, which an
agent inside the disconnected environment follows. The session history is `docs/notes/session-log.md`. Personal, untracked notes
(live sandbox URLs, local tokens) are in `CLAUDE.local.md`.

## What this is

Wingman is the team's self-service portal for OpenShift hosted clusters:
day1 (create, edit, delete a hosted cluster) and day2 (install and configure
charts on clusters). GitLab is its only store: every change is a merge request
into the day1 values repo (`gitops-day1/platform-config`) or a team's day2 repo
(`sigs/<team>`), and ArgoCD applies what is merged. Monorepo: `apps/web`
(Next.js 16), `apps/day1-service` and `apps/day2-service` (FastAPI),
`packages/wingman-core` (the shared core), `deploy/helm/wingman/` (Helm),
`dev/gitlab-fixtures` (production-shaped repo trees for tests and local GitLab).

## Standing project conventions — follow without being re-told

Explicit user instructions; violating one is a real mistake, not style.

1. **The quality bar is server-scan and herzi** (the team's best repos, in
   team-redbull). New code, tests, CI, docs and repo hygiene must not be below
   them. When unsure how to do something, look at how they do it.
2. **Git: commit and push after each completed stage**, on a feature branch,
   with Conventional Commit subjects (`feat:`, `fix:`, `docs:`, `ci:`,
   `test:`, `refactor:`). One unit of work per commit. Never push to `main`
   directly; merges go through a PR. The subjects since the last release set
   the next version (ADR-0031): any `feat:`/`feat(<scope>):` makes the merge a
   minor, any `!` before the colon (`feat!:`, `fix(day1)!:`) a major,
   otherwise a patch. Only subjects count: a `BREAKING CHANGE:` footer alone
   does not.
3. **This repo is public.** Never commit live URLs, tokens, internal hostnames,
   or findings about private systems (e.g. the production export in
   `~/Downloads/stack-export`). Put them in the git-ignored `CLAUDE.local.md`.
4. **Layers are enforced** (ADR-0001): domain → ports → application →
   infrastructure/observability → web. `uv run lint-imports` must pass. New
   external systems get a port, an adapter and a fake (DEVELOPMENT.md); never
   a client call from a router.
5. **GitLab only through `GitLabPort`** (ADR-0002). Service code reaches
   GitLab through the port and its adapter; nothing imports python-gitlab.
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
    Dependabot/Renovate; CI is kept current by hand (`docs/ops/ci-maintenance.md`).
11. **Docs change in the same commit as the code.** A new decision gets an ADR
    (template in `docs/adr/README.md`); a superseded one is marked, never
    deleted.
12. **Use parallel agents** where work splits into independent pieces.
13. **Wingman owns day1 until the planned `create-cluster` workflow exists**
    (user decision 2026-11-07). Keep provisioning behind an adapter so it can
    switch to starting the workflow. The orchestrator API has no auth; that is
    accepted. Since 3.7.0 (ADR-0042) the adapter exists:
    `DAY1_PROVISIONER=workflow` starts the platform's `provision-cluster`
    workflow; the default stays Wingman's own MR until the team switches.
14. **Site and MCE are read-only in Wingman** (user decision 2026-11-07).
    Wingman never creates them; MCE onboarding happens elsewhere.
15. **Don't add network policies** — they cause connectivity issues.
16. **Files and functions stay small** (ADR-0056): a source file ≤ 500 lines
    (a test ≤ 800), Python complexity ≤ 12, a web function ≤ 200 lines and
    complexity ≤ 30. `scripts/file-size-baseline.txt` and the per-function
    `noqa`/`eslint-disable` exemptions may only shrink: never add one, split
    the code. The ADR says where a router's schemas, a page's logic and pure
    helpers go.

## Where the work stands

Shipped features: README.md's feature table, with each one's ADR. **Not done
yet, in order:** (1) the architect's answers (`docs/ideas/architecture-fit.md`);
(2) flavors v2's "Left for later"; (3) ecosystem features (`docs/ideas/`).

## Key technical facts (cross-cutting traps)

- **Every file in `sites/<site>/mces/<mce>/hostedClusters/` becomes an ArgoCD
  Application**, and an empty one fails the generator. Never write a
  placeholder (`.gitkeep`) or sidecar there.
- **The cluster file is a values file** for the hostedclusters-setup chart:
  `owner`, `mastertag`, `nodepool[]` (`infraEnvName`, `replicas`, `labels`,
  `configs`). `vlanId` and `dhcp_values` are written by the allocate-segment
  workflow on the MR branch; `mcFiles`/`mcConfigMap` by CI. Wingman writes
  none of them, and must expect those commits on its MR branches.
- **`clusterName` differs**: production's ApplicationSet strips `ocp4-` from
  the file name (HostedCluster `ocp4-prod-x-site1` in `hcp-prod-x-site1`); the
  GitHub sandbox keeps it. Day1 follows `DAY1_CLUSTER_NAME_STRIP_PREFIX`
  (default `ocp4-`; `""` for the sandbox; ADR-0015).
- **Naming convention** `ocp4-<env>-<name>-<site>[-<seq>]`; the chart derives
  the day2 `<env>` from the MCE name and fails on names that don't follow it.
  Sites may contain dashes: match a name against its site folder, never split
  it (ADR-0014).
- **GitLab is asynchronous in places**: an MR's stored diff, its mergeability
  and its `sha` after a push are computed by background jobs, and a merged
  source branch is deleted later. The adapter handles the first three (a
  merge checks the branch head itself); don't assume the fourth.
- **A read's `last_commit_id` is the commit the repo was read at**, not the
  file's own last change (ADR-0035). It is a valid write guard, since GitLab
  checks "changed since that commit". Never decide staleness with
  `expected != current`: use `RepoReads.changed_since`. For "changed by, at",
  use `last_change`.
- **Every chart value is in `values.schema.json`** (ADR-0059), which refuses
  any other key: a new value gets its schema entry in the same commit, and a
  dropped one stays there, marked deprecated. A container that writes a file
  needs an `emptyDir` (read-only roots; `docs/ops/images.md`).
- **ty honours only `# type: ignore` or `# ty: ignore[rule]`**, never a
  mypy-style `# type: ignore[code]` (ADR-0008).
- **Next.js 16 / React 19 / Tailwind 4 / zod 4** differ from older docs. Read
  `apps/web/AGENTS.md` and `node_modules/next/dist/docs/` before frontend edits.
  `apps/web/proxy.ts` replaces middleware.

## Verifying your work

```bash
uv sync --locked --all-packages --all-groups --all-extras
scripts/gate.sh                    # everything CI runs, in CI's order
scripts/gate.sh ci                 # actionlint, zizmor, shellcheck (pinned tools, scripts/ci-tools.sh)
scripts/gate.sh python             # the Python half, incl. the requirement-export drift check and file sizes
scripts/gate.sh web                # npm ci, npm audit (allowlist), lint, typecheck, build
PLAYWRIGHT_CHANNEL=chrome scripts/gate.sh e2e   # the mocked Playwright suite (Playwright's own download hangs here)

# After any pyproject.toml change: relock and re-export, commit all three
uv lock && scripts/export-requirements.sh
# Images, from the repository root (docs/ops/images.md)
podman build -f apps/web/Dockerfile -t wingman-web:dev .

# Real GitLab (podman; ~8 GB VM, see the script header)
scripts/dev/gitlab-up.sh token     # start local GitLab CE 19.5.3 and make the dev token
uv run python scripts/dev/seed_gitlab.py --token wingman-local-dev-token-0001
WINGMAN_TEST_GITLAB_URL=http://localhost:8929 WINGMAN_TEST_GITLAB_TOKEN=wingman-local-dev-token-0001 \
  uv run pytest -m live_gitlab     # the GitLab contract against real GitLab

# A day1 cluster file through the chart, as ArgoCD renders it
helm template <cluster> <chart-dir> -f sites/configValues.yaml -f sites/<site>/values.yaml \
  -f sites/<site>/mces/<mce>/values.yaml -f <cluster-file> --set-string clusterName=<cluster>,site=<site>,mce=<mce>
```

Web: `npm run lint --workspace=web` (eslint and knip), `cd apps/web && npx tsc
--noEmit`, `npx vitest run`, `npm run build --workspace=web`. Playwright:
`npm run test:e2e:mocked --workspace=web` runs every spec but `live-*` (CI
runs it in two shards); the `live` specs need a running stack on a disposable
GitLab (`apps/web/README.md`). Traps: route mocks match LIFO; SSE keeps the
network busy, so wait on `domcontentloaded`, never `networkidle`; any
unmocked endpoint's 401 redirects to `/login`; with `PLAYWRIGHT_CHANNEL=chrome`
on macOS a run can hang after its last test (`pkill -f GoogleUpdater.app`);
locally Playwright reuses whatever listens on :3000, so when another checkout
may be serving there, start your own (`PORT=31xx npm run dev`) and set
`PLAYWRIGHT_BASE_URL`.

Then the step no command covers: re-read the docs your change made wrong.

## Running the services

- From the repo root: `uv run uvicorn wingman_day1.main:app --port 8001`,
  `uv run uvicorn wingman_day2.main:app --port 8002`. Settings are in each
  service's `settings.py` plus `wingman_core.settings`; README.md lists them.
  The token is `GITLAB_TOKEN` (not the legacy `GITLAB_ACCESS_TOKEN`).
- No GitLab needed: `WINGMAN_ENVIRONMENT=development WINGMAN_GIT_BACKEND=fake`
  seeds an in-memory GitLab from `dev/gitlab-fixtures`. Local login:
  `DEV_AUTH_ENABLED=true` and a `DEV_AUTH_SECRET` of 32+ characters (day1),
  sent as `secret` to `POST /api/auth/dev-login`.
- Roles come from OpenShift groups (`WINGMAN_ADMIN_GROUPS` /
  `WINGMAN_VIEWER_GROUPS`) and travel in the app JWT; both services share
  `JWT_SECRET_KEY`. `AdminUser` guards writes, `CurrentUser` reads.
- Every merge to main is a release (ADR-0030, ADR-0031, `docs/ops/images.md`):
  CI computes `X.Y.Z` from the commit subjects, tags `v<X.Y.Z>` and pushes the
  three images. Deploy `X.Y.Z`, never `latest` or a `sha-` tag; a manual
  production build is of a release tag and named by its version. Only GitHub
  can run the publish jobs.

## Where to continue right now

**This section holds exactly one entry — the most recent unit of work.** When
you finish yours, move this entry to the top of `docs/notes/session-log.md`
and write yours here.

**2026-11-17 — 3.44.0 to 3.44.3: credits per area, the docs refresh, a layout for the integrations.**
- **Credits** (3.44.0, 3.44.1): five quick clicks on an area's brand show who
  built it, each person with their years (`lib/areas.ts`).
- **Docs** (3.44.2, 3.44.3): the in-app Documentation page covers the
  Overview, Cluster Workflows, Inventory Management, Quick Links, Segments and
  Server Scan (a test opens every Contents entry); `docs/README.md` indexes the
  docs, `docs/architecture.md` is the overview to read first; this file was
  shortened (its CI pass is `docs/ops/ci-maintenance.md`, its status history
  is at the end of `docs/notes/session-log.md`).
- **In progress, the owner's decision:** server-scan and segments-manager
  each get one package in day1 (`integrations/<system>/`, ADR-0001's layers
  inside, ADR-0001's 2026-11-17 amendment) and one folder in the web
  (`apps/web/features/<system>/`); then a map of which upstream files each
  Wingman file follows, a compare script for a new upstream release, and a
  short guide per system in `docs/integrations/`.

**Next:**
- Scale's scale-down policy per NodePool (the user): a flavor and
  create-form choice that `cluster-template.j2` writes as the entry's
  annotation (the specs project's template needs it too); more in
  `CLAUDE.local.md`. Then, when the workflow is deployed: turn Scale on and
  a first live run.
- cluster-navigator's data on the cluster page and per MCE
  (`docs/ideas/single-pane.md` workstream 5).
- Flavors v2's "Left for later": missing add-ons in one MR per team, the
  cluster-name prefix in the web, a preview of an unsaved flavor.
- Tuning: a lock per pool.
- Code organisation, later (the user): 28 files left in the size baseline.
- The team's questions: herzi, provision-cluster's 24 characters, RBAC, a
  shared Git store.
