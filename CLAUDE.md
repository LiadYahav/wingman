# CLAUDE.md

Orients a Claude Code session on this repo. `README.md` is the human
quickstart; `docs/ecosystem/README.md` is how Wingman fits the team-redbull
platform (read it before changing day1 or day2); `docs/adr/` holds the
decisions and their reasons; `docs/ops/` holds the operator contracts
(metrics); `docs/upgrade/` tells an agent inside the disconnected
environment how to upgrade a deployed Wingman (a release that needs
operator steps adds a guide there); `docs/ideas/` holds what could come
next and the decisions it waits on. The session history is `docs/notes/session-log.md`. Personal,
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
`apps/day2-service` (FastAPI), `packages/wingman-core` (the shared core),
`deploy/helm/wingman/` (Helm), `dev/gitlab-fixtures` (production-shaped repo trees for
tests and local GitLab).

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
   external systems get a port, an adapter and a fake; never a client call
   from a router.
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
  contract suite passing 30/30 on the fake and on GitLab CE 19.5.3, RFC 9457
  errors, metrics, settings, auth, cache, approvals); CI and
  `scripts/gate.sh`; ADRs 0001-0011; monitoring in the chart (ServiceMonitor,
  7 promtool-tested alerts with a runbook, a Grafana dashboard, all off by
  default) with a test tying alerts and dashboard to the metric catalogue.
- Done: day1 rewritten on `wingman-core` as `wingman_day1`
  (`apps/day1-service/src/wingman_day1`, ADRs 0012-0019), checked end to end
  against local GitLab with `scripts/dev/day1_live_e2e.py` and through both
  chart copies. Web-visible API changes:
  `docs/notes/2026-11-07-day1-api-changes.md`.
- Done: day2 rewritten as `wingman_day2` (four destination kinds, fleet
  defaults and exclusions, the platform's value stacks with provenance,
  lints, one MR per team; ADRs 0020-0024), held to the team's
  `render_chain.py` by an oracle test and run against GitLab CE 19.5.3.
  Web-visible API changes: `docs/notes/2026-11-07-day2-api-changes.md`.
- Done: CI's supply chain and releases (ADR-0030, ADR-0031, ADR-0032):
  hash-pinned per-service exports, the web image from the root lock, build on
  every PR, every merge to main a release versioned from its commits, a
  blocking npm audit, a nightly live-GitLab run.
- Done: both service images install only from the hash-pinned exports
  (`docs/ops/images.md`); the chart sets exactly the variables the services
  read (`tests/repo/test_chart_env_contract.py`) and probes
  `/health/live`/`/health/ready`.
- Done (2026-11-08): the web on both new APIs (shared dropdown, searchable
  combobox, empty, loading and error states); the whole stack checked live
  against the seeded local GitLab; report-only version drift (ADR-0025); the
  legacy `wingman-shared` removed; the delete dialog ready for the
  delete-cluster workflow (ADR-0033); OpenShift versions per MCE from the
  day1 repo's upgrade ladder; `docs/ideas/`, `docs/upgrade/`.
- Done (2026-11-08): the day1, specs and team repos are read once per commit
  from GitLab's archive (ADR-0035); the catalog on a production-sized repo went
  from 9 s and 357 GitLab calls per load to 0.03 s cached, 0.46 s after the TTL.
- **Not done yet, in order:** (1) flavors v2 (`docs/ideas/flavors-v2.md`;
  stages 1 and 2 on `roiblum/feat-flavors-v2`, the web pages to build);
  (2) the architect's
  answers (`docs/ideas/architecture-fit.md`); (3) chart hardening (a values
  schema, a pinned nginx image); (4) ecosystem features (`docs/ideas/`).

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
  the file name (HostedCluster `ocp4-prod-x-site1` in `hcp-prod-x-site1`); the GitHub
  sandbox keeps it. Day1 follows `DAY1_CLUSTER_NAME_STRIP_PREFIX` (default
  `ocp4-`; `""` for the sandbox; ADR-0015). See `docs/ecosystem/README.md`.
- **Naming convention** `ocp4-<env>-<name>-<site>[-<seq>]`; the chart derives
  the day2 `<env>` from the MCE name and fails on names that don't follow it.
  Sites may contain dashes: match a name against its site folder, never split
  it (ADR-0014).
- **GitLab is asynchronous in places**: an MR's stored diff, its mergeability
  and its `sha` after a push are computed by background jobs, and a merged
  source branch is deleted later. The adapter handles the first three (a
  merge checks the branch head itself); don't assume the fourth.
- **A read's `last_commit_id` is the commit the repo was read at**, not the
  file's own last change (ADR-0035: repos are read once per commit, from
  GitLab's archive). It is a valid write guard, since GitLab checks "changed
  since that commit". Never decide staleness with `expected != current`: use
  `RepoReads.changed_since`. For "changed by, at", use `last_change`.
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
scripts/gate.sh python             # the Python half, incl. the requirement-export drift check
scripts/gate.sh web                # npm ci, npm audit (allowlist), lint, typecheck, build
scripts/gate.sh e2e                # the mocked Playwright suite on a production build
PLAYWRIGHT_CHANNEL=chrome scripts/gate.sh e2e   # on installed Chrome (Playwright's download hangs here)

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

Web: `npm run lint --workspace=web`, `cd apps/web && npx tsc --noEmit`,
`npm run build --workspace=web`. Playwright: `npm run test:e2e:mocked
--workspace=web` runs the `mocked` project (every spec but `live-*`; CI runs
it); the `live` project is `live-day1-flows.spec.ts` and `live-day2.spec.ts`,
against a running stack on a disposable GitLab (`PLAYWRIGHT_BASE_URL`, the dev
login secret; commands in `apps/web/README.md`). Playwright traps: route mocks match LIFO; SSE
keeps the network busy, so wait on `domcontentloaded`, never `networkidle`;
any unmocked endpoint's 401 redirects to `/login`.

The live GitLab contract runs nightly in CI (`.github/workflows/live-gitlab.yml`)
and fails unless every live test ran. Only GitHub can run the publish jobs
(the computed version, tag, push, release notes; ADR-0030, ADR-0031).

Then the step no command covers: re-read the docs your change made wrong.

## Keeping CI current (manual, roughly quarterly)

Nothing updates itself and there is no Dependabot or Renovate (ADR-0003,
ADR-0032). The pass:

1. **Action pins.** Compare each `uses:` comment (`# vX.Y.Z`) with the
   action's latest release. Resolve the new tag to its commit before pinning,
   dereferencing annotated tags:
   `gh api repos/<o>/<r>/git/ref/tags/<tag>` (an `object.type` of `tag` means
   one more `gh api repos/<o>/<r>/git/tags/<sha> --jq .object.sha`). Never
   copy a SHA from a README; server-scan was broken twice by tags that do not
   exist. Then `scripts/gate.sh ci`: zizmor refuses a tag pin and a comment that
   names another tag. `PaulHatch/semantic-version`'s defaults are the
   versioning rule (convention 2, ADR-0031): before bumping it, check that its
   `action.yml` defaults (`major_pattern`, `minor_pattern`,
   `search_commit_body`, `bump_each_commit`) did not change.
2. **Downloaded tools.** `scripts/ci-tools.sh` (actionlint, zizmor,
   shellcheck), `scripts/install-helm.sh` and the promtool step in `ci.yml`:
   new version plus every checksum, from the release's checksum file or the
   API's asset digests (the script header has the command).
3. **Vulnerable or unused.** `scripts/gate.sh python web` runs `pip-audit`,
   `deptry` and the npm audit gate. Prefer deleting an unused dependency to
   bumping it. A fixed advisory leaves `scripts/npm-audit-allowlist.txt` in the
   same commit (the gate fails until it does).
4. **Runtime deprecations.** Actions declare a Node runtime; GitHub removes
   old ones (server-scan had to replace a tagging action for that).
5. **Base images.** `apps/web/Dockerfile` (and the service Dockerfiles) pin
   UBI 9.8 by tag and digest, and CPython by checksum; docs/ops/images.md has
   the commands to resolve a new digest and checksums.
6. **ty and ruff** are pinned exactly in the root dev group; a ty bump moves
   diagnostics (ADR-0008), so bump it in its own commit and read new errors as
   ty changing. **hatchling** (root `build` group) follows the members'
   build-system; after a bump, `uv lock && scripts/export-requirements.sh`.
7. **Runner image.** Every job runs on `ubuntu-24.04`, not `ubuntu-latest`:
   when `ubuntu-latest` moved to 26.04, Playwright had no browser build for it
   and the E2E job failed. Move all jobs together, after checking Playwright
   supports the new image.
8. **GitLab CE** for the live contract: `live-gitlab.yml` and
   `scripts/dev/gitlab-up.sh` together, then record the run in ADR-0005.

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
- Images (docs/ops/images.md, ADR-0030, ADR-0031): CI builds all three on
  every PR. Every merge to main is a release: `PaulHatch/semantic-version`
  computes `X.Y.Z` from the commit subjects since the last `v*` tag
  (convention 2), `scripts/release.py plan` refuses one that exists or moves
  backwards, and CI creates the git tag `v<X.Y.Z>`, pushes
  `ghcr.io/<owner>/wingman-{day1,day2,web}` as `X.Y.Z`, `X.Y`, `X`, `latest`
  and `sha-<short_sha>` with signed provenance, and writes the release notes.
  There is no `VERSION` file (retired after v3.0.0). Deploy `X.Y.Z`, never
  `latest` or a `sha-` tag; a manual production build is of a release tag and
  named by its version.

## Where to continue right now

**This section holds exactly one entry — the most recent unit of work.** When
you finish yours, move this entry to the top of `docs/notes/session-log.md`
and write yours here.

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
