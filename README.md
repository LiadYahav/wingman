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
| **day2-service** | Charts on clusters through the gitops-day2 team repos | Python 3.13, FastAPI, wingman-core (httpx) |
| **wingman-core** | The shared core: the GitLab port and adapters, errors, auth, metrics, settings | Python 3.13, httpx, Pydantic |

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
│   └── wingman-core/          # The shared core (ADR-0001)
│       └── src/wingman_core/  # domain, ports, application, infrastructure, web
│
├── chart/                     # Helm chart for deployment
│   ├── templates/             # Kubernetes manifests
│   ├── values.yaml            # Production defaults
│   └── values.minikube.yaml   # Local development overrides
│
└── scripts/                   # Development & build scripts
    ├── gate.sh                # Everything CI runs, in CI's order
    ├── minikube-dev-setup.sh  # Local GitLab + minikube setup
    ├── build-images.sh        # Docker image builds into minikube
    └── dev/                   # Local GitLab: gitlab-up.sh, seed_gitlab.py, day1_live_e2e.py
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
| **InfraEnv smart dropdown** | When a spec template contains an `infra_env` variable, the cluster creation form fetches available InfraEnv CRDs from the selected MCE hosting cluster and presents them as a dropdown. Falls back to plain text input when `CLUSTER_STATUS_ENABLED=false`. |

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

`{cluster}` is a cluster id (`hub`, `mce:<site>:<env>:<mce>`,
`hosted:<site>:<env>:<mce>:<cluster>`, `upi:<site>:<env>:<cluster>`) or a bare
name that names one destination. Changes since the legacy service:
[docs/notes/2026-11-07-day2-api-changes.md](docs/notes/2026-11-07-day2-api-changes.md).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/teams`, `/addons[?team]`, `/addons/{team}/{addon}` | Teams (projects of the sigs group) and their `operators/` catalog |
| `GET` | `/addons/{team}/{addon}/versions`, `/values?version=` | Chart repo branches; the chart's own values at a branch |
| `GET` | `/clusters[?kind&site&env]`, `/clusters/{cluster}` | Destinations from every team repo and day1 |
| `GET` | `/clusters/{cluster}/addons` | Charts on the cluster: own folders and fleet defaults |
| `GET` | `/clusters/{cluster}/addons/{team}/{addon}` | The merged values, layer by layer, with provenance |
| `POST` | `/merge-preview` | The same, with edited cluster values |
| `POST`/`PUT`/`DELETE` | `/clusters/{cluster}/addons/{team}/{addon}` | Install / update / remove (each opens an MR) |
| `POST` | `/clusters/{cluster}/addons/bulk` | Install several charts: one MR per team |
| `GET` | `/clusters/{cluster}/history`, `/clusters/{cluster}/upgrade-check?to=` | Commits on the cluster's folders; pins a version change would lose |
| `GET` | `/lints[?team]` | render_chain.py's checks plus Wingman's own |
| `GET`/`PUT`/`POST` | `/approvals`, `/approvals/{team}/{iid}[/approve\|/reject]` | MRs addressed by team and number |
| `GET` | `/audit/commits`, `/audit/merge-requests`, `/audit/commits/{sha}/diff` | History across team repos |

### Auth Service

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/auth/login` | Initiate OpenShift OAuth |
| `GET` | `/api/auth/callback` | OAuth callback |
| `GET` | `/api/auth/me` | Get current user info |

## Environment Variables

Both services read their settings at start-up and refuse an unsafe or
incomplete configuration (ADR-0009). The chart sets them
(`chart/templates/configmap.yaml`, `secret.yaml`);
`tests/repo/test_chart_env_contract.py` fails when the chart and the settings
classes disagree. The full lists, with defaults, are in
`packages/wingman-core/src/wingman_core/settings.py` (shared) and each
service's `settings.py`.

### Day1 Service

```env
# Required (the settings refuse to start without them, ADR-0009)
GITLAB_URL=https://gitlab.example.com
GITLAB_TOKEN=<service account token>
DAY1_GITLAB_PROJECT_ID=gitops-day1/platform-config
SPECS_GITLAB_PROJECT_ID=wingman/cluster-specs
JWT_SECRET_KEY=at-least-32-characters-shared-with-day2

# Login: complete OpenShift OAuth settings, or dev login (never in production)
OPENSHIFT_OAUTH_HOST=oauth-openshift.apps.example.com
OPENSHIFT_API_HOST=api.example.com:6443
OPENSHIFT_OAUTH_CLIENT_ID=wingman-app
OPENSHIFT_OAUTH_CLIENT_SECRET=<secret>
OPENSHIFT_OAUTH_REDIRECT_URI=https://wingman.apps.example.com/login
DEV_AUTH_ENABLED=false
DEV_AUTH_SECRET=                  # at least 32 characters when dev login is on

# RBAC
WINGMAN_ADMIN_GROUPS=wingman-admins
WINGMAN_VIEWER_GROUPS=wingman-viewers

# Optional
DAY1_CLUSTER_NAME_STRIP_PREFIX=ocp4-   # ADR-0015: "" for the GitHub sandbox
DAY1_CACHE_TTL_SECONDS=30              # at most 60 (ADR-0011)
GITLAB_VERIFY_TLS=true                 # an internal CA goes in SSL_CERT_FILE
GITLAB_WEBHOOK_SECRET=                 # empty: the webhook answers 404
DAY2_SERVICE_URL=http://wingman-day2:8002
WINGMAN_ENVIRONMENT=production         # development allows the fake backend
WINGMAN_GIT_BACKEND=gitlab             # fake: in-memory, seeded from dev/gitlab-fixtures

# Live MCE status (enables the InfraEnv dropdown and cluster health)
CLUSTER_STATUS_ENABLED=false
MCE_API_DOMAIN=mgmt.example.com
MCE_TOKENS_FILE=/etc/wingman/mce-tokens/tokens
MCE_INFRAENV_NAMESPACE=           # empty = query all namespaces
```

### Day2 Service

```env
# Required (the settings refuse to start without them, ADR-0009)
GITLAB_URL=https://gitlab.example.com
GITLAB_TOKEN=<service account token>
DAY2_SIGS_GROUP_PATH=gitops-day2-prod/sigs      # every project directly in it is a team
DAY1_GITLAB_PROJECT_ID=gitops-day1/platform-config   # read-only for day2 (versions, hosted clusters)
JWT_SECRET_KEY=at-least-32-characters-shared-with-day1

# RBAC (same as Day1)
WINGMAN_ADMIN_GROUPS=wingman-admins
WINGMAN_VIEWER_GROUPS=wingman-viewers

# Optional
DAY2_GITOPS_BRANCH=main          # the branch the platform reads; MRs target it
DAY2_CACHE_TTL_SECONDS=15        # at most 60 (ADR-0011)
WINGMAN_GIT_BACKEND=fake         # local only: an in-memory GitLab seeded from dev/gitlab-fixtures
WINGMAN_ENVIRONMENT=development  # default production, which refuses the fake backend
```

### Frontend

The web app uses relative API paths (`/api/day1`, `/api/day2`, `/api/auth`) — no build-time env vars
are required. In a deployment nginx routes them to the services; locally, `next dev` proxies them when
`WINGMAN_DEV_DAY1_URL` and `WINGMAN_DEV_DAY2_URL` are set (development server only; see
[apps/web/README.md](apps/web/README.md#running-against-local-services)).

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
# Backend services, from the repo root (uv workspace)
uv run uvicorn wingman_day1.main:app --port 8001 --reload
uv run uvicorn wingman_day2.main:app --port 8002 --reload

# Frontend, proxying /api/* to them (apps/web/README.md has a no-network setup on the fake GitLab)
cd apps/web && npm ci
WINGMAN_DEV_DAY1_URL=http://127.0.0.1:8001 WINGMAN_DEV_DAY2_URL=http://127.0.0.1:8002 npm run dev
```

### Docker Build

Production images are tagged with the **git commit SHA** — not `latest` — so every
release is traceable and rollbacks are one command.

```bash
SHA=$(git rev-parse --short HEAD)

# Build all three for production (linux/amd64, clean)
docker buildx build --platform linux/amd64 --no-cache -t wingman-day1:$SHA -f apps/day1-service/Dockerfile . --load
docker buildx build --platform linux/amd64 --no-cache -t wingman-day2:$SHA -f apps/day2-service/Dockerfile . --load
docker buildx build --platform linux/amd64 --no-cache -t wingman-web:$SHA -f apps/web/Dockerfile . --load

# Save for air-gapped / on-prem transfer
docker save wingman-day1:$SHA | gzip > wingman-day1-$SHA.tar.gz
docker save wingman-day2:$SHA | gzip > wingman-day2-$SHA.tar.gz
docker save wingman-web:$SHA  | gzip > wingman-web-$SHA.tar.gz
```

Pass `--set image.tag=$SHA` (or update `chart/values.yaml`) when deploying via Helm.

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

Each team is a project directly in the sigs group, laid out as the
gitops-day2 platform reads it (a folder existing is the registration;
details in `docs/ecosystem/notes/day2-kubevirt.md` and ADR-0020):

```
sigs/<team>/
├── operators/<chart>/{<chart>.yaml, values.yaml}         # team default (+ ocp-versions/<v>/ pins)
├── defaults/{hub,mces,hosted-clusters,upi}/<chart>/       # fleet defaults (+ exclusions.yaml)
└── sites/<site>/<env>/
    ├── mces/<mce>/in-cluster/<chart>/                     # charts on the MCE hub
    ├── mces/<mce>/<cluster>/<chart>/                      # charts on a hosted cluster
    └── upi/<cluster>/<chart>/                             # charts on a UPI cluster
```

## Key Concepts

### Clusters vs Specs

- **Spec**: A reusable template defining cluster configuration (worker pools, network settings, etc.)
- **Cluster**: An actual cluster instance, optionally linked to a spec
- **Drift**: When a cluster's configuration differs from its linked spec

### Addon Layers

Chart values are merged exactly as the platform's `deployApp.yaml` stacks them:
the chart's own `values.yaml` at the pinned revision, then up to ten team-repo
layers for a hosted cluster (team default, OCP-version pin, site, site+env,
fleet default and its env/cluster variants, MCE-wide, cluster-wide, the
cluster's chart folder). The preview shows which layer set each value
(ADR-0021).

### MR Workflow

All changes create Merge Requests instead of direct commits:

1. User initiates change → MR created with `wingman` label
2. MR appears in Approvals page
3. Different user reviews and approves
4. MR is merged → ArgoCD syncs changes

## Monitoring & Debugging

### Health Checks

- Day1: `GET /healthz` (`/health/live`), `GET /health/ready` (GitLab reachable), `GET /metrics`
- Day2: `GET /healthz` (`/health/live`), `GET /health/ready` (GitLab reachable), `GET /metrics`

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
2. Shared code goes in `packages/wingman-core`
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
