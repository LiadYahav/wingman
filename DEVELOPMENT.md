# Wingman Development Guide

This guide covers everything developers need to know to contribute to the Wingman platform.

## Architecture Overview

Wingman is a GitOps-based Internal Developer Platform (IDP) for OpenShift cluster provisioning. It follows a no-database architecture where all state is stored in GitLab repositories.

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                       │
│                        apps/web/                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Day1 Service  │  │   Day2 Service  │  │   Auth Service  │
│   (FastAPI)     │  │   (FastAPI)     │  │   (via nginx)   │
│  apps/day1-*/   │  │  apps/day2-*/   │  │                 │
└────────┬────────┘  └────────┬────────┘  └─────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│ GitLab: day1    │  │ GitLab: sigs/*  │
│ (clusters/specs)│  │ (team addons)   │
└─────────────────┘  └─────────────────┘
```

### Services

| Service | Port | Purpose |
|---------|------|---------|
| `day1-service` | 8001 | Cluster provisioning, specs management |
| `day2-service` | 8002 | Addon catalog, cluster addon management |
| `web` | 3000 | Next.js frontend |
| `nginx` | 8080 | Reverse proxy, OAuth handling |

### Shared Package

`packages/shared-python/` contains common utilities:
- `gitlab_client.py` - Async GitLab API wrapper
- `cache.py` - In-memory LRU cache with TTL
- `yaml_utils.py` - YAML parsing with error handling
- `models.py` - Pydantic models shared across services
- `path_resolver.py` - GitLab path construction
- `mr_conventions.py` - MR title/description formatting

## Local Development Setup

### Prerequisites

- Python 3.13+
- Node.js 24+
- Docker & Docker Compose
- Minikube (for local Kubernetes)
- GitLab instance with test repositories

### Backend (Python Services)

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Day1 Service
cd apps/day1-service
uv sync
cp .env.example .env  # Configure GitLab tokens
uv run uvicorn src.main:app --reload --port 8001

# Day2 Service (separate terminal, from the repo root; env in apps/day2-service/src/wingman_day2/settings.py)
uv sync --locked --all-packages --all-groups --all-extras
WINGMAN_ENVIRONMENT=development WINGMAN_GIT_BACKEND=fake JWT_SECRET_KEY=<32+ chars> \
  DAY2_SIGS_GROUP_PATH=sigs DAY1_GITLAB_PROJECT_ID=gitops-day1/platform-config \
  uv run uvicorn wingman_day2.main:app --reload --port 8002   # fake: the dev/gitlab-fixtures repos
```

### Frontend (Next.js)

```bash
cd apps/web
npm install
npm run dev  # Starts on port 3000
```

### Running Tests

```bash
# Python lint + type check
uvx ruff check apps/day1-service packages/shared-python
uvx mypy apps/day1-service/src --ignore-missing-imports
scripts/gate.sh python   # day2 and wingman-core: ruff, ty, import-linter, pytest (incl. the render_chain oracle), deptry

# Frontend lint + build
cd apps/web && npm run lint && npm run build

# Mocked E2E tests (no backend required)
cd apps/web && npm run test:e2e

# Live E2E tests against the running stack (requires kubectl port-forward to 8080)
PLAYWRIGHT_BASE_URL=http://localhost:8080 npx playwright test e2e/tests/live-qa.spec.ts
PLAYWRIGHT_BASE_URL=http://localhost:8080 npx playwright test e2e/tests/live-user-flows.spec.ts
```

## Adding New Features

### Adding a New API Endpoint

1. **Create the route** in `src/routers/<domain>.py`:

```python
from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/day1", tags=["my-feature"])

class MyRequest(BaseModel):
    name: str
    value: int

@router.post("/my-endpoint")
async def my_endpoint(
    body: MyRequest,
    user: CurrentUser,  # Injected auth
    my_service: MyServiceDep,  # Injected service
) -> dict:
    return await my_service.do_something(body.name, body.value)
```

2. **Create the service** in `src/services/<domain>_service.py`:

```python
class MyService:
    def __init__(self, gl: GitLabClient, cache: CacheManager):
        self.gl = gl
        self.cache = cache

    async def do_something(self, name: str, value: int) -> dict:
        # Use async GitLab methods to avoid blocking
        content, _ = await self.gl.aread_file(f"path/{name}.yaml")
        return {"result": content}
```

3. **Register the router** in `src/main.py`:

```python
from .routers import my_feature
app.include_router(my_feature.router)
```

4. **Add dependency injection** in `src/dependencies.py`:

```python
def get_my_service() -> MyService:
    return MyService(gl=get_gitlab_client(), cache=get_cache())

MyServiceDep = Annotated[MyService, Depends(get_my_service)]
```

### Adding a New Frontend Page

> **Existing pages for reference**: `/clusters`, `/specs`, `/addons`, `/approvals`, `/audit`, `/docs`
> (see `apps/web/app/(app)/`). The `/docs` page is a good example of a pure TSX content page that uses
> no external markdown renderer.

1. **Create the page** in `app/(app)/<route>/page.tsx`:

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export default function MyPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["my-data"],
    queryFn: () => api.get("/api/day1/my-endpoint"),
  });

  if (isLoading) return <Skeleton />;
  return <div>{JSON.stringify(data)}</div>;
}
```

2. **Add types** in `types/index.ts`:

```typescript
export interface MyData {
  name: string;
  value: number;
}
```

### Adding Shared Python Code

1. Add code to `packages/shared-python/src/wingman_shared/`
2. Export in `__init__.py`
3. Both services import from `wingman_shared`

## Code Conventions

### Python

- **Async GitLab calls**: Always use `await gl.aread_file()` not `gl.read_file()` to avoid blocking the event loop
- **Error handling**: Catch `NotFoundError`, `GitLabError` from `wingman_shared.exceptions`
- **Caching**: Use `CacheManager.get_or_fetch()` for expensive operations
- **Types**: Use type hints everywhere, run `mypy` to verify

### TypeScript/React

- **Data fetching**: Use `@tanstack/react-query` with appropriate `staleTime`
- **Forms**: Use controlled components with validation
- **Styling**: Tailwind CSS with `cn()` utility for conditional classes

### Git Workflow

- Branch naming: `<username>/<action>-<resource>-<name>`
- Commit messages: Descriptive, include "Co-Authored-By: Claude" if AI-assisted
- All changes via MR, even for ops (GitOps philosophy)

## Performance Considerations

### Backend

1. **Use async GitLab methods**: The `python-gitlab` library is synchronous. Our wrapper uses `asyncio.to_thread()` internally, but you must call the `a`-prefixed methods (`aread_file`, `alist_directories`, etc.)

2. **Batch operations**: When fetching multiple items, use `asyncio.gather()`:
```python
results = await asyncio.gather(
    *[self.fetch_item(id) for id in ids],
    return_exceptions=True
)
```

3. **Cache aggressively**: Use the cache for anything fetched from GitLab:
```python
return await self.cache.get_or_fetch(
    f"prefix:{key}", 
    fetch_function, 
    ttl=60.0
)
```

### Frontend

1. **Batch API calls**: Avoid N+1 queries. Create bulk endpoints if needed.
2. **Use proper staleTime**: Don't set `staleTime: 0` unless truly necessary.
3. **Lazy load**: Use `enabled` flag in useQuery for conditional fetching.

## Testing

### Unit Tests

```python
# tests/test_my_service.py
import pytest
from unittest.mock import AsyncMock

async def test_my_feature():
    mock_gl = AsyncMock()
    mock_gl.aread_file.return_value = ("content", "sha")
    
    service = MyService(gl=mock_gl, cache=CacheManager())
    result = await service.do_something("test", 42)
    
    assert result["status"] == "ok"
```

### Integration Tests

Use the local minikube setup with test GitLab repositories.

## Deployment

See `chart/README.md` for Helm deployment instructions.

### Building Images

Production images are tagged with the **git commit SHA** so every deployment is
traceable. Use `latest` only for quick local testing.

```bash
SHA=$(git rev-parse --short HEAD)

# Build for local/minikube (native arch)
docker build -t wingman-day1:$SHA -f apps/day1-service/Dockerfile .
docker build -t wingman-day2:$SHA -f apps/day2-service/Dockerfile .
docker build -t wingman-web:$SHA -f apps/web/Dockerfile .

# Build all three for production (amd64, clean)
docker buildx build --platform linux/amd64 --no-cache -t wingman-day1:$SHA -f apps/day1-service/Dockerfile . --load
docker buildx build --platform linux/amd64 --no-cache -t wingman-day2:$SHA -f apps/day2-service/Dockerfile . --load
docker buildx build --platform linux/amd64 --no-cache -t wingman-web:$SHA -f apps/web/Dockerfile . --load

# Save for air-gapped transfer
docker save wingman-day1:$SHA | gzip > wingman-day1-$SHA.tar.gz
docker save wingman-day2:$SHA | gzip > wingman-day2-$SHA.tar.gz
docker save wingman-web:$SHA  | gzip > wingman-web-$SHA.tar.gz
```

Update `image.tag` in `chart/values.yaml` (or `--set image.tag=$SHA`) when deploying.

### Environment Variables

| Variable | Service | Description |
|----------|---------|-------------|
| `GITLAB_URL` | all | GitLab instance URL |
| `GITLAB_DAY1_TOKEN` | day1 | Token for day1 repo |
| `GITLAB_DAY2_TOKEN` | day2 | Token for sigs group |
| `GITLAB_SPECS_TOKEN` | day1 | Token for specs repo |
| `LOG_LEVEL` | all | DEBUG, INFO, WARNING, ERROR |
| `CACHE_*_TTL` | all | Cache TTL settings |

## Troubleshooting

### "coroutine was never awaited"

You called a sync GitLab method in async context. Use the `a`-prefixed version:
```python
# Wrong
content = gl.read_file(path)

# Correct
content = await gl.aread_file(path)
```

### Health checks timing out

The event loop is blocked. Ensure all GitLab calls use async methods.

### Cache not updating

Check TTL settings and call `cache.invalidate(key)` after mutations.
