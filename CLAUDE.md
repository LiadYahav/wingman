# Wingman Platform - AI Agent Guide

This file provides context for AI coding assistants working on the Wingman codebase.

## Project Overview

Wingman is a GitOps-based Internal Developer Platform (IDP) for OpenShift cluster provisioning. It uses GitLab as its source of truth (no database).

### Core Concepts

- **Day1**: Cluster provisioning - creating new OpenShift clusters from specs
- **Day2**: Addon management - installing/configuring operators on existing clusters
- **Specs**: Cluster templates defining variables and default addons
- **MCE**: Multi-Cluster Engine - groups clusters by management plane

## Repository Structure

```
apps/
  day1-service/     # FastAPI - cluster provisioning
  day2-service/     # FastAPI - addon management
  web/              # Next.js frontend
packages/
  shared-python/    # Shared utilities (gitlab_client, cache, models)
chart/              # Helm chart for deployment
```

## Critical Patterns

### ALWAYS Use Async GitLab Methods

The GitLab client has sync methods that block the event loop. Always use the `a`-prefixed async versions:

```python
# WRONG - blocks event loop, causes health check timeouts
content, _ = self.gl.read_file(path)
dirs = self.gl.list_directories(path)

# CORRECT - runs in thread pool
content, _ = await self.gl.aread_file(path)
dirs = await self.gl.alist_directories(path)
```

### Error Handling for GitLab Operations

Always catch specific exceptions:

```python
from wingman_shared.exceptions import NotFoundError, GitLabError

try:
    content, _ = await gl.aread_file(path)
except NotFoundError:
    return None  # File doesn't exist
except GitLabError as exc:
    logger.warning("GitLab API error: %s", exc)
    raise HTTPException(500, "GitLab error") from exc
```

### YAML Parsing

Use the shared YAML utilities that handle errors gracefully:

```python
from wingman_shared.yaml_utils import parse_multi_document, YamlParseResult

# Returns empty list on error, never crashes
docs = parse_multi_document(content)

# Or get detailed error info
result = parse_multi_document(content, return_error=True)
if result.error:
    # Has line, column, snippet for IDE-like error display
    logger.warning("Parse error: %s", result.error)
```

### Caching Pattern

Use the cache for all GitLab reads:

```python
async def get_data(self, key: str) -> Data:
    async def _fetch() -> Data:
        content, _ = await self.gl.aread_file(f"path/{key}.yaml")
        return Data.model_validate(parse_multi_document(content)[0])
    
    return await self.cache.get_or_fetch(
        f"prefix:{key}", _fetch, ttl=60.0
    )
```

### Frontend Data Fetching

Use React Query with appropriate caching:

```typescript
const { data } = useQuery({
  queryKey: ["clusters", name],
  queryFn: () => api.get(`/api/day1/clusters/${name}`),
  staleTime: 30_000,  // Don't refetch for 30s
});
```

## Common Tasks

### Adding a New API Endpoint

1. Create route in `src/routers/<domain>.py`
2. Create service method in `src/services/<domain>_service.py`
3. Register router in `src/main.py`
4. Add dependency in `src/dependencies.py`

### Adding a New Frontend Page

1. Create `app/(app)/<route>/page.tsx`
2. Add types to `types/index.ts`
3. Use React Query for data fetching

### Modifying Shared Code

Edit files in `packages/shared-python/src/wingman_shared/`
Both services automatically get updates.

## Testing Commands

```bash
# Python lint
uvx ruff check apps/day1-service apps/day2-service packages/shared-python

# Python types
uvx mypy apps/day1-service/src --ignore-missing-imports
uvx mypy apps/day2-service/src --ignore-missing-imports

# Frontend
cd apps/web && npm run lint && npm run build
```

## Building Docker Images

```bash
# For local/minikube (arm64 or native)
docker build -t wingman-day1:latest -f apps/day1-service/Dockerfile .
docker build -t wingman-day2:latest -f apps/day2-service/Dockerfile .
docker build -t wingman-web:latest apps/web/

# For production (amd64)
docker buildx build --platform linux/amd64 -t wingman-day1:latest -f apps/day1-service/Dockerfile . --load
docker buildx build --platform linux/amd64 -t wingman-day2:latest -f apps/day2-service/Dockerfile . --load
docker buildx build --platform linux/amd64 -t wingman-web:latest apps/web/ --load

# Save for air-gapped transfer
docker save wingman-day1:latest | gzip > wingman-day1.tar.gz
```

## Key Files Reference

| File | Purpose |
|------|---------|
| `packages/shared-python/src/wingman_shared/gitlab_client.py` | GitLab API wrapper with async methods |
| `packages/shared-python/src/wingman_shared/models.py` | Shared Pydantic models |
| `packages/shared-python/src/wingman_shared/yaml_utils.py` | YAML parsing with error handling |
| `apps/day2-service/src/services/addon_service.py` | Core addon management logic |
| `apps/day1-service/src/services/cluster_service.py` | Cluster provisioning logic |
| `apps/web/lib/api-client.ts` | Frontend API client |
| `apps/web/types/index.ts` | TypeScript type definitions |

## Performance Guidelines

1. **Batch API calls**: Avoid N+1 queries from frontend
2. **Use asyncio.gather**: For parallel GitLab operations
3. **Cache everything**: GitLab reads are expensive
4. **Set staleTime**: Frontend queries should cache appropriately

## Common Pitfalls

- **Don't use sync GitLab methods in async context** - causes health check timeouts
- **Don't forget `await`** on async GitLab calls - causes "coroutine never awaited"
- **Don't set staleTime: 0** on frontend queries without good reason
- **Don't add network policies** - they cause connectivity issues

## Auth/RBAC

- Users get `admin` or `viewer` role from GitLab group membership
- Role is embedded in JWT token
- Use `AdminUser` dependency for write operations
- Use `CurrentUser` for read-only endpoints
