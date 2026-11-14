# Wingman Development Guide

How the code is laid out, how to run it locally, and how to add to it. The decisions behind
it, with their reasons, are the ADRs in `docs/adr/`; this guide links them rather than
repeating them. How Wingman fits the rest of the platform is `docs/ecosystem/README.md`.

## Architecture

GitLab is Wingman's only store: there is no database. Every change is a merge request into
the day1 project, the specs project or a team's project in the sigs group, and ArgoCD applies
what is merged.

| Process | Port | Purpose |
|---------|------|---------|
| `day1-service` (`wingman_day1`) | 8001 | Hosted clusters, specs, approvals and audit of those two projects, login (OpenShift OAuth) |
| `day2-service` (`wingman_day2`) | 8002 | Charts on the hub, MCEs, hosted and UPI clusters, through the team projects |
| `web` (Next.js) | 3000 | The UI; it holds no state of its own |
| `nginx` (in the chart) | 8080 | Routes `/api/auth`, `/api/day1`, `/api/webhooks` to day1, `/api/day2` to day2, the rest to web |

Both services are built on `packages/wingman-core` (`wingman_core`): the GitLab port with its
httpx adapter and in-memory fake, RFC 9457 errors, auth, metrics, the read cache and settings.

### Layers (ADR-0001)

Each service is `src/wingman_dayN/` with the same layers, and `uv run lint-imports` enforces
the direction (domain → ports → application → infrastructure → api):

| Where | What |
|-------|------|
| `domain/` | Pure rules and types: no I/O, no FastAPI |
| `ports.py` (day1: `ports/`) | The service's own ports (protocols); GitLab is core's `GitLabPort` (ADR-0002) |
| `application/` | Use cases, written against ports only |
| `infrastructure/` | Adapters for the ports, and their fakes |
| `api/` | FastAPI routers (`api/v1/`), the dependencies that hand them the use cases, error mapping |
| `settings.py` | Every environment variable the service reads (ADR-0009) |
| `main.py` | The composition root: the only place adapters are built and wired |

A new external system gets a port, an adapter and a fake; a router never calls a client.

## Running locally

```bash
uv sync --locked --all-packages --all-groups --all-extras
npm ci                      # at the repository root: one lockfile (ADR-0003)
```

### On the in-memory GitLab (no network)

`WINGMAN_GIT_BACKEND=fake` seeds an in-memory GitLab from `dev/gitlab-fixtures`. Each service
seeds its own, so a change one service makes is not seen by the other; use the local GitLab
below when that matters.

```bash
# Both terminals, from the repository root
export WINGMAN_ENVIRONMENT=development WINGMAN_GIT_BACKEND=fake \
  JWT_SECRET_KEY=local-jwt-secret-at-least-32-characters \
  DAY1_GITLAB_PROJECT_ID=gitops-day1/platform-config SPECS_GITLAB_PROJECT_ID=wingman/cluster-specs \
  DAY2_SIGS_GROUP_PATH=sigs DAY2_SERVICE_URL=http://127.0.0.1:8002

# Terminal 1: day1, with dev login
DEV_AUTH_ENABLED=true DEV_AUTH_SECRET=local-dev-login-secret-32-characters \
  uv run uvicorn wingman_day1.main:app --reload --port 8001

# Terminal 2: day2
uv run uvicorn wingman_day2.main:app --reload --port 8002

# Terminal 3: the web dev server, proxying /api/* to them
WINGMAN_DEV_DAY1_URL=http://127.0.0.1:8001 WINGMAN_DEV_DAY2_URL=http://127.0.0.1:8002 \
  npm run dev --workspace=web
```

Add `DAY1_FAKE_FLEET=true` to day1's line for the cluster page's Nodes tab and node uninstall
(ADR-0038), and the EPG on its **HostedCluster & network** card (ADR-0039). It replaces the MCE
hubs, server-scan, the workflows orchestrator and segments-manager with fakes seeded from
`dev/fleet-fixtures/`:
- `servers.yaml` is a made-up fleet in server-scan's own row shape, and its `sites` catalog
  (server-scan's configured sites): the Server Scan area's Sites page (`/server-scan`,
  ADR-0048) counts these rows by server-scan's rules over it; `site3` has no server, so its
  card shows 0. The Servers page (`/server-scan/servers`) lists them, and its maintenance
  toggle changes them in memory, recorded as by `dev` (no token, as on a server-scan with
  auth off);
- `server-records.yaml` is the hardware behind them, per model, in server-scan's shape: a
  server's page (`/server-scan/servers/<id>`) shows its row with its model's CPU, memory,
  drives, GPUs (the R760s), PSUs, NICs and Cisco's fabric uplinks, a few servers' health
  reasons, unread fields and an unreachable BMC; its History is made up from the row plus
  every maintenance change made since day1 started;
- `mce.yaml` places those servers in NodePools. `ocp4-prod-lark-site1` has an in-place update
  half done (one node rebooting), a pool short a node (no free Agent: two bound, one not
  approved) and a server only server-scan places there. `ocp4-prod-herzi-site1` has a Replace
  rollout (one node draining, its replacement writing its image to disk);
  `ocp4-prod-hawk-site1` and `ocp4-prep-amit-site2-a` are simply ready;
- `segments.yaml` is a made-up segments-manager ledger in its own `by-segment` shape: the
  segments the fixture clusters' files hold, with their EPGs, and two free ones. It agrees with
  the files except for `ocp4-prod-herzi-site1`, whose VLAN differs on purpose (1418 against the
  file's 1410), so the card's warning can be seen. `ocp4-prod-hawk-site1` has no segment yet:
  its VLAN and segment are pending.
- `inventory.yaml` adds servers in no MCE to the fleet (one locked by another add-server run,
  one in maintenance), the add-server runs' sample phases, past runs, and a fake herzi that
  starts a pool draw on `ocp4-prod-lark-site1`'s short pool now and then (ADR-0057).
- `skill/` is a short stand-in for server-scan's Claude Code skill (`SKILL.md` and one
  reference): the Server Scan area's Claude page (`/server-scan/claude`) shows it, and its
  download is it zipped as server-scan zips it, with `http://server-scan.example` written in
  unless `SERVER_SCAN_UI_URL` says otherwise.

The fake MCE also serves live status and InfraEnvs, as if `CLUSTER_STATUS_ENABLED` were on. An
uninstall walks a few sample phases, about 8 s each, then frees the server and removes its
Machine; the NodePool's replacement Machine then waits for a free Agent. On Inventory Management
(`/inventory`), add `DAY1_ADD_SERVERS=true` to add servers: a run walks a few sample phases,
about 8 s each, takes a server and leaves it in the MCE's inventory; herzi's runs show beside it. The fake fleet is
refused unless `WINGMAN_ENVIRONMENT=development`, and it works with either Git backend.

With `DAY1_FAKE_FLEET`, the card's links to segments-manager point at
`http://segments-manager.example` unless `SEGMENTS_MANAGER_UI_URL` says otherwise; nothing answers
there locally. Without the fake fleet, `SEGMENTS_MANAGER_UI_URL=https://segments-manager.example`
shows the links alone, and the EPG is "—".

Add `DAY1_PROVISIONER=workflow` as well to see Create start the provision-cluster workflow
(ADR-0042) instead of opening a merge request. The fake run walks a few sample phases, about
6 s each, and then waits at `awaiting-merge` with a merge request link to an example host;
nothing is written to GitLab. A file without a `mastertag` fails its run, and a second create
of the same name while its run waits is refused (409), as the real workflow does.

Add `DAY1_UPGRADES=true` to see a cluster's **Upgrade** through the upgrade-cluster workflow
(ADR-0055). The fake answers the targets from `dev/fleet-fixtures/upgrade.yaml`
(`ocp4-prod-lark-site1` and `ocp4-prod-herzi-site1` have NodePools, `ocp4-prod-owl-site1` has
nothing newer, any other cluster gets a default), and a started run walks the fixture's steps
on the clock: planning, `awaiting-approval` (Approve), a control-plane step,
`awaiting-day2-confirm` (Confirm day2), then `awaiting-continue` (Continue) and a roll for each
NodePool, and done. A decision the run is not waiting for is refused in words (409); Pause,
Resume and Abort work while it is open. Nothing is written to GitLab.

`DAY2_SERVICE_URL` matters: without it day1 asks the chart's `http://wingman-day2:8002`, and
every cluster's drift is Unknown. The web dev server proxies only when both
`WINGMAN_DEV_*_URL` are set (`apps/web/next.config.ts`); a production build never proxies.
Sign in on `http://localhost:3000/login` with any lowercase username and the
`DEV_AUTH_SECRET`. Approving needs a second user: nobody approves their own change.

### On a local GitLab

```bash
scripts/dev/gitlab-up.sh token     # GitLab CE in podman on http://localhost:8929, and a dev token
uv run python scripts/dev/seed_gitlab.py --token wingman-local-dev-token-0001
```

Then run the services as above without `WINGMAN_GIT_BACKEND=fake`, with
`GITLAB_URL=http://localhost:8929` and `GITLAB_TOKEN=wingman-local-dev-token-0001`. Every
variable is listed in the README's [Environment Variables](README.md#environment-variables).

## Adding an endpoint

1. **The rule**, if there is one, goes in `domain/`; **the use case** in `application/`, over
   the ports in `ports.py` (day1: `ports/`; GitLab through `GitLabPort`). GitLab reads go through the service's
   cached repositories, which use `TtlCache.get_or_fetch` (`wingman_core.infrastructure.cache`)
   with the service's TTL (ADR-0011); a write clears what it changed. A read every page waits
   on can pass `stale=stale_for(ttl)` to be answered while it refreshes (ADR-0041). Measure a
   read path at production size with `scripts/dev/bench_day1_reads.py` (docs/ops/performance.md).
2. **Wire it** in `main.py`: day1's `build_context` builds the `Day1Context`
   (`api/deps.py`); day2's `Day2Services.build` (`application/services.py`) builds day2's.
3. **The router** goes in `api/v1/`. It takes the use cases from `Context` (day1, `api/deps.py`)
   or `Services` (day2, `api/v1/dependencies.py`), and the user from `CurrentUser` (reads) or
   `AdminUser` (writes; `wingman_core.web.auth`). For example, from day1's `api/v1/sites.py`:

   ```python
   @sites_router.get("/{site}/mces")
   async def list_site_mces(site: Name, context: Context, user: CurrentUser) -> list[str]:
       """MCE folder names under a site."""
       return await context.sites.mce_names(site)
   ```

   A new router is registered in day1's `main.py` (`ROUTERS`) or in
   `wingman_day2/api/v1/__init__.py`.
4. **Errors**: raise an `AppError` subclass (`wingman_core.web.errors`) or a domain error the
   service maps to one (day1's `api/errors.py`, day2's `api/v1/errors.py`); never FastAPI's
   `HTTPException`, and never swallow a read error (ADR-0004). Writes carry the read's `last_commit_id` and are never retried
   (ADR-0006).
5. **Document it**: a row in the README's API Reference (`tests/repo/test_web_docs_contract.py`
   fails until the README and the routes agree), and the web types in `apps/web/types/`.

A new setting goes in the service's `settings.py`, the chart (`deploy/helm/wingman/templates/configmap.yaml`
or `secret.yaml`; `tests/repo/test_chart_env_contract.py` compares them) and the README's
settings list. Metric names and labels are a contract (ADR-0010, `docs/ops/metrics.md`).

## Testing

```bash
uv run pytest -q              # every Python test; the live GitLab ones skip without their variables
scripts/gate.sh python        # file sizes, ruff, ty, import-linter, pytest with coverage, pip-audit, deptry
scripts/gate.sh web           # npm ci, npm audit, lint, typecheck, build
scripts/gate.sh e2e           # the mocked Playwright suite on a production build
scripts/gate.sh               # everything CI runs, in CI's order
```

- **Unit and API tests** run on `InMemoryGitLab` (`wingman_core.infrastructure.fake_gitlab`),
  seeded from `dev/gitlab-fixtures` by each service's `tests/conftest.py`, which also builds the
  app on fakes and gives signed-in clients (day1's `client` and `token`, day2's `jane`, `bob` and
  `vic`). Tests run with
  `--import-mode=importlib`, so share helpers as fixtures, not imports.
- **The GitLab contract** (`packages/wingman-core/tests/contract`) runs on the fake and, with
  these variables, on a real GitLab (CI runs it nightly):

  ```bash
  scripts/dev/gitlab-up.sh token
  uv run python scripts/dev/seed_gitlab.py --token wingman-local-dev-token-0001
  WINGMAN_TEST_GITLAB_URL=http://localhost:8929 WINGMAN_TEST_GITLAB_TOKEN=wingman-local-dev-token-0001 \
    uv run pytest -m live_gitlab
  ```

- **day2's oracle** (`apps/day2-service/tests/oracle`) holds Wingman's discovery to the
  platform's `render_chain.py`; it needs `helm`.
- **Web**: the mocked Playwright suite needs no backend; the `live` specs run against a
  running stack on a disposable GitLab (`apps/web/README.md`).

Type checking is ty (ADR-0008): it honours only `# type: ignore` or `# ty: ignore[rule]`.

## Git workflow

Work on a feature branch and merge through a pull request; never push to `main`. Commit after
each completed stage, one unit of work per commit, with a Conventional Commit subject (`feat:`,
`fix:`, `docs:`, `ci:`, `test:`, `refactor:`). The subjects set the release version: a `feat:`
makes the merge a minor release, a `!` before the colon (`feat!:`) a major, anything else a patch
(CLAUDE.md, convention 2). Docs change in the same commit as the code; a new
decision gets an ADR (template in `docs/adr/README.md`).

## Deployment

`deploy/helm/wingman/README.md` installs the chart; `docs/ops/images.md` builds and publishes the images.
Every merge to main is a release, versioned from the commit subjects (ADR-0031). Deploy a
release by its version, the same for every image, with `image.<component>.tag`
(`image.day1.tag`, `image.day2.tag`, `image.web.tag`; for example `3.0.1`, never `latest`).
Operating it: `docs/ops/metrics.md` and `docs/ops/runbook.md`.
