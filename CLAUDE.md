# Wingman Platform - AI Agent Guide

This file provides context for AI coding assistants working on the Wingman codebase.

## Project Overview

Wingman is a GitOps-based Internal Developer Platform (IDP) for OpenShift cluster provisioning. It uses GitLab as its source of truth (no database).

### Core Concepts

- **Day1**: Cluster provisioning - creating new OpenShift clusters from specs
- **Day2**: Addon management - installing/configuring operators on existing clusters
- **Specs**: Cluster templates defining variables and default addons
- **MCE**: Multi-Cluster Engine - groups clusters by management plane

### Ecosystem (read before changing day1/day2 flows)

Wingman is being brought back on top of the team-redbull platform: server-scan (servers), segments-manager (VLAN segments), Temporal workflows + orchestrator API, herzi (fills InfraEnv pools), the hostedclusters-setup chart, gitops-day2. The current day1/day2 code predates it and does not match it. What we learned, the gaps and open questions are in `docs/ecosystem/README.md` (per-system detail in `docs/ecosystem/notes/`). There is **no Day1 create-cluster workflow yet** (planned); don't assume one exists.

## Repository Structure

```
apps/
  day1-service/     # FastAPI - cluster provisioning
  day2-service/     # FastAPI - addon management
  web/              # Next.js frontend
packages/
  shared-python/    # Shared utilities (gitlab_client, cache, models); edits apply to both services
chart/              # Helm chart for deployment
```

## Critical Patterns

### ALWAYS Use Async GitLab Methods

The GitLab client has sync methods that block the event loop (causing health check timeouts). Always use the `a`-prefixed async versions, and always `await` them:

```python
# WRONG - blocks event loop
content, _ = self.gl.read_file(path)
dirs = self.gl.list_directories(path)

# CORRECT - runs in thread pool
content, _ = await self.gl.aread_file(path)
dirs = await self.gl.alist_directories(path)
```

Use `asyncio.gather` for parallel GitLab operations.

### Error Handling for GitLab Operations

Catch specific exceptions (`wingman_shared.exceptions`): `NotFoundError` (file missing, usually return `None`) and `GitLabError` (log, then `raise HTTPException(500, ...) from exc`).

### YAML Parsing and Caching

- Parse YAML with `wingman_shared.yaml_utils.parse_multi_document` (returns `[]` on error; pass `return_error=True` for line/column/snippet). Don't call `yaml.safe_load` directly.
- Wrap every GitLab read in `cache.get_or_fetch(key, fetcher, ttl=...)` (`wingman_shared/cache.py`).

### Frontend Data Fetching

Use React Query with a real `staleTime` (e.g. `30_000`); don't use `staleTime: 0` without good reason. Avoid N+1 calls from the frontend.

```typescript
const { data } = useQuery({
  queryKey: ["clusters", name],
  queryFn: () => api.get(`/api/day1/clusters/${name}`),
  staleTime: 30_000,
});
```

### Frontend Stack Gotcha

Next.js 16 / React 19 / Tailwind 4 / zod 4: APIs differ from older docs. Read `apps/web/AGENTS.md` and `node_modules/next/dist/docs/` before frontend edits. `apps/web/proxy.ts` replaces middleware. UI primitives use `@base-ui/react` + shadcn.

## Running Locally

- Run from the service dir: `uv sync --extra dev && uv run uvicorn src.main:app --reload --port 8001` (day1) / `8002` (day2). Imports are relative, so it must be `src.main:app`.
- Services crash at startup without: `GITLAB_URL`, `GITLAB_ACCESS_TOKEN`, `JWT_SECRET_KEY`; day1 also needs `DAY1_GITLAB_PROJECT_ID`, `SPECS_GITLAB_PROJECT_ID`; day2 also `DAY2_SIGS_GROUP_PATH`. They read `.env` from the cwd (there is no `.env.example`, despite DEVELOPMENT.md). Full env reference: README.md.
- Local login without OpenShift OAuth: `DEV_AUTH_ENABLED=true` plus a non-empty `DEV_AUTH_SECRET` (day1).
- `CLUSTER_STATUS_ENABLED` is off by default and cannot run on minikube.

## Testing Commands

```bash
# Python lint
uvx ruff check apps/day1-service apps/day2-service packages/shared-python

# Python types
uvx mypy apps/day1-service/src --ignore-missing-imports
uvx mypy apps/day2-service/src --ignore-missing-imports

# Frontend lint, typecheck, build (CI also runs tsc; there is no typecheck script)
cd apps/web && npm run lint && npx tsc --noEmit && npm run build

# Frontend E2E tests (Playwright)
cd apps/web && npm run test:e2e          # Runs ALL specs in e2e/tests, including live ones (those fail without a backend)
cd apps/web && npm run test:e2e:ui       # Interactive test UI
cd apps/web && npm run test:e2e:headed   # Run tests in visible browser
cd apps/web && npx playwright test user-flows.spec.ts -g "name"   # Single mocked spec/test
```

Python tests: none exist yet (`src/tests/` holds only `__init__.py`). CI runs `pytest tests/ ... || echo "No tests found"`, so a pytest failure never fails CI. Single test once added: `cd apps/day1-service && uv run pytest src/tests/test_x.py::test_y`.

## E2E Testing with Playwright

Tests live in `apps/web/e2e/` (`fixtures/api-handlers.ts` has the route-intercept helpers: `injectAdminAuth`, `mockDashboardApis`, `mockDay1Api`, `mockDay2Api`, `mockAllApis`).

- `user-flows.spec.ts` is fully mocked (no backend). The older feature specs use the page objects in `e2e/pages/`.
- `live-user-flows.spec.ts` and `live-qa.spec.ts` hit the real stack (minikube): `PLAYWRIGHT_BASE_URL=http://localhost:8080 npx playwright test live-qa.spec.ts`.

### Key patterns to know

- **Route intercept order**: Playwright uses LIFO matching — the last `page.route()` registered
  wins for a given URL. Register broad wildcard routes first in `setupMocks`, then override with
  specific ones in `beforeEach` blocks.
- **`*` vs `**` in globs**: `*` matches one path segment; `**` matches across `/`. Use `**` when
  a URL has variable-depth paths (e.g. `**/audit/commits/**/diff` for `{repo}/{sha}/diff`).
- **ClusterInstalledResponse shape**: `{ cluster: string, mce: string, installed: InstalledAddon[] }`.
  Mock responses must match this — not a bare array.
- **SSE keeps network alive**: `waitForLoadState("networkidle")` never resolves. Always use
  `waitForLoadState("domcontentloaded")` plus an explicit `waitForTimeout()`.
- **401 from any unmocked endpoint triggers `window.location.href = "/login"`** (see `api-client.ts`).
  Every endpoint a page could call must be intercepted in the mock — including secondary ones like
  `/api/day2/gitlab-info` on the cluster addons page.

Selectors use `data-testid` (e.g. `addon-card-{team}-{name}`, `field-row-{path}` with dots replaced by dashes); grep existing tests for the conventions.

## Building Docker Images

CI (`.github/workflows/ci.yml`) pushes `ghcr.io/<owner>/wingman-{day1,day2,web}` on merges to main with 3 tags: `<short_sha>`, `latest`, and `v<VERSION>` (from the root `VERSION` file). Bumping `VERSION` is the only release mechanism; it is not synced to `chart/Chart.yaml` or the pyproject/package.json versions. `chart/values.yaml` defaults `image.*.tag` to `latest`.

Manual production builds are tagged with the **git commit SHA** (not `latest`) so deployments are traceable and rollbacks unambiguous:

```bash
SHA=$(git rev-parse --short HEAD)

# Production (amd64) — --no-cache for a clean build; drop --platform/--no-cache for local/minikube
docker buildx build --platform linux/amd64 --no-cache -t wingman-day1:$SHA -f apps/day1-service/Dockerfile . --load
docker buildx build --platform linux/amd64 --no-cache -t wingman-day2:$SHA -f apps/day2-service/Dockerfile . --load
docker buildx build --platform linux/amd64 --no-cache -t wingman-web:$SHA apps/web/ --load

# Air-gapped transfer: docker save wingman-<svc>:$SHA | gzip > wingman-<svc>-$SHA.tar.gz
```

Update `image.tag` in `chart/values.yaml` (or `--set image.tag=$SHA`) when deploying a new build.

## Conventions and Pitfalls

- Commits use conventional-commit prefixes (`feat:`, `fix:`, `docs:`, `ci:`, `refactor:`).
- Platform-generated branches (`platform/{user}/{action}-{resource}-{ts}`) and MR titles (`[Wingman/Day1|Day2|Specs] Verb type name`) are parsed by the audit service. Don't change them casually (`wingman_shared/mr_conventions.py`).
- Don't add network policies - they cause connectivity issues.

## Auth/RBAC

- Users get `admin` or `viewer` role from **OpenShift** group membership (`WINGMAN_ADMIN_GROUPS` / `WINGMAN_VIEWER_GROUPS`, see `wingman_shared/auth/rbac.py`). Both services must share the same `JWT_SECRET_KEY` and group settings.
- Role is embedded in JWT token
- Use `AdminUser` dependency for write operations
- Use `CurrentUser` for read-only endpoints
- Services that need cluster status use `ClusterStatusServiceDep` (`dependencies.py`), which returns 501 when the feature is disabled.
