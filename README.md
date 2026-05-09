# Wingman Platform

Wingman is an Internal Developer Platform (IDP) for managing OpenShift HostedControlPlane (HCP) clusters via GitOps. It provides a web UI for cluster provisioning, addon management, and approval workflows, with all changes committed to GitLab and applied via ArgoCD.

## Architecture Overview

```
┌───────────────────────────────────────────────────────┐
│  OpenShift Cluster                                    │
│                                                       │
│                      ┌───────┐                        │
│                      │  web  │                        │
│                      └───┬───┘                        │
│                          │                            │
│                    ┌─────┴─────┐                      │
│                    ▼           ▼                      │
│  ┌───────────┐   ┌───────┐   ┌───────┐               │
│  │ OpenShift │◀──│ day1  │◀─▶│ day2  │               │
│  │   OAuth   │   └───┬───┘   └───┬───┘               │
│  └───────────┘       │           │                   │
│                      └─────┬─────┘                   │
│                            │                         │
└────────────────────────────┼─────────────────────────┘
                             ▼
                       ┌──────────┐
                       │  GitLab  │
                       └────┬─────┘
                            ▲
                       ┌────┴─────┐
                       │  ArgoCD  │
                       └────┬─────┘
                            ▼
                     ┌─────────────┐
                     │ MCE Clusters│
                     └─────────────┘
```

### Components

| Component | Description | Tech Stack |
|-----------|-------------|------------|
| **web** | Frontend UI | Next.js 16, React 19, TailwindCSS, React Query |
| **day1-service** | Cluster provisioning, specs, approvals | Python 3.13, FastAPI, python-gitlab |
| **day2-service** | Addon management, operator lifecycle | Python 3.13, FastAPI, python-gitlab |
| **shared-python** | Common utilities, models, GitLab client | Python 3.13, Pydantic |

### GitOps Flow

1. User makes change via UI (create cluster, install addon, etc.)
2. Backend creates a GitLab Merge Request with the changes
3. Another user reviews and approves the MR via UI
4. ArgoCD syncs the merged changes to the cluster

## Project Structure

```
cluster-platform/
├── apps/
│   ├── web/                    # Next.js frontend
│   │   ├── app/               # App Router pages
│   │   │   └── (app)/         # Authenticated routes
│   │   │       ├── clusters/  # Cluster management
│   │   │       ├── specs/     # Spec templates
│   │   │       ├── addons/    # Addon catalog
│   │   │       ├── approvals/ # MR review
│   │   │       └── audit/     # Audit trail
│   │   ├── components/        # React components
│   │   ├── lib/               # Utilities
│   │   ├── stores/            # Zustand stores
│   │   └── types/             # TypeScript types
│   │
│   ├── day1-service/          # Cluster provisioning API
│   │   └── src/
│   │       ├── routers/       # FastAPI route handlers
│   │       ├── services/      # Business logic
│   │       └── config.py      # Environment config
│   │
│   └── day2-service/          # Addon management API
│       └── src/
│           ├── routers/       # FastAPI route handlers
│           └── services/      # Business logic
│
├── packages/
│   └── shared-python/         # Shared Python utilities
│       └── src/wingman_shared/
│           ├── auth/          # OAuth, JWT, RBAC
│           ├── gitlab_client.py
│           ├── models.py      # Pydantic models
│           ├── cache.py       # In-memory caching
│           └── yaml_utils.py  # YAML handling
│
├── chart/                     # Helm chart for deployment
│   ├── templates/             # Kubernetes manifests
│   ├── values.yaml            # Production defaults
│   └── values.minikube.yaml   # Local development overrides
│
└── scripts/                   # Development & build scripts
    ├── minikube-dev-setup.sh  # Local GitLab + minikube setup
    ├── build-images.sh        # Docker image builds
    └── seed-test-data.py      # Seed GitLab with test data
```

## Recent Features

| Feature | Description |
|---------|-------------|
| **Two-phase spec/cluster form** | Specs define structure + immutable flags; clusters fill values. The form adapts to the spec shape at cluster-creation time — nodepool count is locked by the spec. |
| **Marketplace addon picker** | Browse and select Day2 addons from a marketplace UI on the spec creation/edit pages. Configure which fields are overrideable per cluster. |
| **YAML fields everywhere** | Dynamic form fields accept plain YAML — no JSON syntax required. Scalars (`high-perf-tuned`), maps, and lists all work naturally. |
| **Site/MCE from GitLab folders** | Site and MCE dropdowns are populated from existing GitLab folder paths; new names create new folders automatically. |
| **OCP versions from repo** | OpenShift version dropdown is sourced from `openshift-versions.txt` in the specs repo — no hardcoded list. |
| **Open in GitLab (addon)** | Each installed addon's kebab menu now includes an "Open in GitLab" link pointing to the per-cluster override directory. |
| **In-app documentation** | `/docs` route with full platform guide, concept explanations, worked examples, and troubleshooting. |
| **Aggregated approvals** | Approvals page aggregates open MRs from all repositories (Day1 + all Day2 team repos) in one view. |
| **Identity variable handling** | `cluster_name`, `site`, `mce` are dedicated identity inputs — they are not part of the dynamic variable form and always override spec defaults in Jinja2 rendering. |

## Deployment

See **[chart/README.md](chart/README.md)** for Helm chart deployment instructions.

## API Reference

### Day1 Service (Port 8001)

Base path: `/api/day1`

#### Clusters

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/clusters` | List all clusters |
| `GET` | `/clusters/drift-summary` | Get drift status for all clusters |
| `GET` | `/clusters/{name}` | Get cluster details |
| `GET` | `/clusters/{name}/status` | Get live cluster status (node pools, health) |
| `GET` | `/clusters/{name}/drift` | Get detailed drift analysis |
| `POST` | `/clusters/{name}` | Create cluster (returns MR) |
| `PUT` | `/clusters/{name}` | Update cluster (returns MR) |
| `DELETE` | `/clusters/{name}` | Delete cluster (returns MR) |
| `POST` | `/clusters/{name}/sync` | Sync cluster to spec (returns MR) |

#### Specs (Cluster Templates)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/specs` | List all specs |
| `GET` | `/specs/{name}` | Get spec details |
| `GET` | `/specs/{name}/clusters` | List clusters using this spec |
| `POST` | `/specs/{name}` | Create spec (returns MR) |
| `PUT` | `/specs/{name}` | Update spec (returns MR) |
| `DELETE` | `/specs/{name}` | Delete spec (returns MR) |

#### Approvals

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/approvals` | List open MRs |
| `GET` | `/approvals/{iid}` | Get MR details with diff |
| `POST` | `/approvals/{iid}/approve` | Approve and merge MR |
| `POST` | `/approvals/{iid}/reject` | Close MR without merging |
| `PUT` | `/approvals/{iid}` | Update MR content |

#### Audit

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/audit/commits` | List recent commits |
| `GET` | `/audit/commits/{sha}/diff` | Get commit diff |
| `GET` | `/audit/mrs` | List merged MRs |

### Day2 Service (Port 8002)

Base path: `/api/day2`

#### Addon Catalog

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/addons` | List all available addons |
| `GET` | `/addons/{team}/{addon}` | Get addon details |
| `GET` | `/addons/{team}/{addon}/versions` | List addon versions |
| `GET` | `/addons/{team}/{addon}/values` | Get default values at version |

#### Cluster Addons

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/clusters/{name}/addons` | List installed addons on cluster |
| `GET` | `/clusters/{name}/addons/{team}/{addon}` | Get merged addon values |
| `POST` | `/clusters/{name}/addons/{team}/{addon}` | Install addon (returns MR) |
| `POST` | `/clusters/{name}/addons/bulk` | Bulk install addons (returns MR) |
| `PUT` | `/clusters/{name}/addons/{team}/{addon}` | Update addon (returns MR) |
| `DELETE` | `/clusters/{name}/addons/{team}/{addon}` | Remove addon (returns MR) |

#### Approvals & Audit

Same endpoints as Day1 but for Day2 repository.

### Auth Service

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/auth/login` | Initiate OpenShift OAuth |
| `GET` | `/api/auth/callback` | OAuth callback |
| `GET` | `/api/auth/me` | Get current user info |

## Environment Variables

### Day1 Service

```env
# Required
GITLAB_URL=https://gitlab.example.com
GITLAB_ACCESS_TOKEN=glpat-xxx
DAY1_GITLAB_PROJECT_ID=wingman/clusters
SPECS_GITLAB_PROJECT_ID=wingman/specs
JWT_SECRET_KEY=your-secret-key

# OpenShift OAuth
OPENSHIFT_OAUTH_URL=https://oauth.openshift.example.com
OPENSHIFT_CLIENT_ID=wingman
OPENSHIFT_CLIENT_SECRET=xxx
OPENSHIFT_REDIRECT_URI=https://wingman.example.com/api/auth/callback

# RBAC
WINGMAN_ADMIN_GROUPS=wingman-admins
WINGMAN_VIEWER_GROUPS=wingman-viewers

# Optional
SERVICE_PORT=8001
LOG_LEVEL=INFO
GITLAB_DEFAULT_BRANCH=main
GITLAB_SSL_VERIFY=true
```

### Day2 Service

```env
# Required
GITLAB_URL=https://gitlab.example.com
GITLAB_ACCESS_TOKEN=glpat-xxx
DAY2_SIGS_GROUP_PATH=wingman/sigs
JWT_SECRET_KEY=your-secret-key

# RBAC (same as Day1)
WINGMAN_ADMIN_GROUPS=wingman-admins
WINGMAN_VIEWER_GROUPS=wingman-viewers

# Optional
SERVICE_PORT=8002
```

### Frontend

The web app uses relative API paths (`/api/day1`, `/api/day2`, `/api/auth`) — no build-time env vars
are required. The Next.js server proxies those paths to the backend services at runtime via the
ingress or the `apps/web/proxy.ts` dev proxy.

## Development Setup

See **[DEVELOPMENT.md](DEVELOPMENT.md)** for detailed development guide, architecture details, and contribution guidelines.

### Prerequisites

- Node.js 24+
- Python 3.13+
- Docker (for containerized deployment)
- Access to GitLab instance
- Access to OpenShift cluster (for OAuth)

### Local Development

```bash
# Frontend
cd apps/web && npm install && npm run dev

# Backend services (uses uv — no virtualenv management needed)
cd apps/day1-service && uv sync && uv run uvicorn src.main:app --port 8001 --reload
cd apps/day2-service && uv sync && uv run uvicorn src.main:app --port 8002 --reload

# Or use the development proxy (proxies /api/* to running backend services)
cd apps/web && npx tsx proxy.ts
```

### Docker Build

```bash
# Build all images
docker build -t wingman-day1:latest -f apps/day1-service/Dockerfile .
docker build -t wingman-day2:latest -f apps/day2-service/Dockerfile .
cd apps/web && docker build -t wingman-web:latest .

# For AMD64 (production)
docker buildx build --platform linux/amd64 -t wingman-day1:latest -f apps/day1-service/Dockerfile . --load
```

## Authentication & Authorization

### Authentication Flow

1. User clicks "Login" → redirected to OpenShift OAuth
2. User authenticates with OpenShift credentials
3. OAuth callback receives authorization code
4. Backend exchanges code for access token
5. Backend fetches user info (username, groups)
6. Backend issues JWT with embedded role
7. Frontend stores JWT, includes in Authorization header

### RBAC

Roles are determined by OpenShift group membership:

| Role | Groups | Permissions |
|------|--------|-------------|
| **admin** | `WINGMAN_ADMIN_GROUPS` | Full access (create, update, delete, approve) |
| **viewer** | `WINGMAN_VIEWER_GROUPS` | Read-only access |

The role is embedded in the JWT at login time and validated on each request.

## GitLab Structure

### Day1 Repository (Clusters + Specs)

```
wingman-clusters/
├── mces/
│   └── {mce}/
│       └── {cluster-name}.yaml    # Cluster definition
└── specs/
    └── {spec-name}.yaml           # Spec template
```

### Day2 Repository (Addons)

Each team is a separate GitLab project under the `sigs` subgroup:

```
wingman/sigs/
├── network/                       # Team: network
│   ├── operators/
│   │   └── {addon}/
│   │       └── {addon}.yaml       # Addon definition + ArgoCD metadata
│   └── mces/
│       └── {mce}/
│           └── {cluster}/
│               └── {addon}/
│                   ├── values.yaml       # Override values
│                   └── argocd.yaml       # Override metadata
├── storage/                       # Team: storage
│   └── ...
└── security/                      # Team: security
    └── ...
```

## Key Concepts

### Clusters vs Specs

- **Spec**: A reusable template defining cluster configuration (worker pools, network settings, etc.)
- **Cluster**: An actual cluster instance, optionally linked to a spec
- **Drift**: When a cluster's configuration differs from its linked spec

### Addon Layers

Addon values are merged from three layers (later layers override earlier):

1. **Chart defaults**: `values.yaml` from the Helm chart repository
2. **Team defaults**: `operators/{addon}/{addon}.yaml` in team project
3. **Cluster overrides**: `mces/{mce}/{cluster}/{addon}/values.yaml`

### MR Workflow

All changes create Merge Requests instead of direct commits:

1. User initiates change → MR created with `wingman` label
2. MR appears in Approvals page
3. Different user reviews and approves
4. MR is merged → ArgoCD syncs changes

## Monitoring & Debugging

### Health Checks

- Day1: `GET /healthz`
- Day2: `GET /healthz`

### Cache Stats

- Day1: `GET /api/day1/cache/stats`
- Day2: `GET /api/day2/cache/stats`

### Logs

Both services log to stdout. In Kubernetes:

```bash
kubectl logs -n wingman -l app.kubernetes.io/component=day1
kubectl logs -n wingman -l app.kubernetes.io/component=day2
```

Background cache warming logs:
```
INFO: Day1 cache warmer starting in 5 seconds...
INFO: Day1 cache pre-warm: refreshing cluster list, specs, approvals
INFO: Day1 cache pre-warm complete
```

## Contributing

### Code Style

- **Python**: Follow PEP 8, use type hints, run `ruff` for linting
- **TypeScript**: Use strict mode, prefer interfaces over types
- **Commits**: Use conventional commits (`feat:`, `fix:`, `chore:`)

### Adding a New Feature

1. Backend changes go in `services/` (business logic) and `routers/` (HTTP layer)
2. Shared code goes in `packages/shared-python`
3. Frontend pages go in `app/(app)/`, components in `components/`
4. Add types to `types/index.ts` for API responses

### Testing Locally

```bash
# Run Python type checks
cd apps/day1-service && mypy src/

# Run frontend type checks
cd apps/web && npx tsc --noEmit

# Run frontend linting
cd apps/web && npm run lint
```

## Troubleshooting

### "Insufficient scope" errors

The GitLab access token needs `api` scope. Regenerate it with full API access.

### MR approval fails

1. Check the service token has Maintainer+ role on the project
2. Check GitLab project settings don't prevent the approval
3. Check logs for the actual GitLab error response

### Cache not refreshing

The backend refreshes cache every 2 minutes. To force refresh:
- Use the "Refresh" button in the UI
- Restart the service pods

### Frontend shows stale data

React Query caches data for 2 minutes. Hard refresh (Ctrl+Shift+R) clears the cache, or wait for `staleTime` to expire.

## License

Proprietary - Internal use only.
