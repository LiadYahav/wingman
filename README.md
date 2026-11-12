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
| **web** | Frontend UI | Next.js 16, React 19, Tailwind CSS 4, TanStack Query |
| **day1-service** | Hosted clusters, specs, approvals, audit, login | Python 3.13, FastAPI, wingman-core (httpx), Jinja2 |
| **day2-service** | Charts on clusters through the gitops-day2 team repos | Python 3.13, FastAPI, wingman-core (httpx) |
| **wingman-core** | The shared core: the GitLab port and adapters, errors, auth, metrics, settings | Python 3.13, httpx, Pydantic |

### GitOps Flow

1. User makes change via UI (create cluster, install addon, etc.)
2. Backend creates a GitLab Merge Request with the changes
3. Another user reviews and approves the MR via UI
4. ArgoCD syncs the merged changes to the cluster

## Project Structure

```
wingman/
├── apps/
│   ├── web/                       # Next.js frontend (apps/web/README.md)
│   │   ├── app/                   # App Router: login/, and the signed-in pages in (app)/:
│   │   │                          #   clusters, specs, addons, destinations, lints,
│   │   │                          #   approvals, audit, docs, settings
│   │   ├── components/            # ui, common, layout, clusters, specs, addons
│   │   ├── hooks/ lib/ stores/    # query hooks, the API client and helpers, the auth store
│   │   ├── types/                 # day1.ts, day2.ts, problem.ts (index.ts re-exports them)
│   │   └── e2e/                   # Playwright: the mocked and live projects
│   │
│   ├── day1-service/              # Hosted clusters, specs, approvals, audit, login (port 8001)
│   │   ├── src/wingman_day1/
│   │   │   ├── domain/            # Pure rules: names, paths, the template, cluster files
│   │   │   ├── application/       # Use cases, over ports only
│   │   │   ├── infrastructure/    # Adapters (day2, MCE hubs, OpenShift OAuth) and their fakes
│   │   │   ├── api/               # deps.py, errors.py, v1/ (the FastAPI routers)
│   │   │   ├── ports.py           # day1's own ports
│   │   │   ├── settings.py        # Every variable day1 reads
│   │   │   └── main.py            # The composition root
│   │   └── tests/
│   │
│   └── day2-service/              # Charts on destinations (port 8002): the same layout,
│       └── src/wingman_day2/      #   with api/v1/dependencies.py and the render_chain oracle in tests/oracle/
│
├── packages/
│   └── wingman-core/              # The shared core (ADR-0001)
│       └── src/wingman_core/      # domain, ports, application, infrastructure, observability, web
│
├── deploy/
│   ├── helm/wingman/              # Helm chart (deploy/helm/wingman/README.md)
│   │   ├── templates/             # Kubernetes manifests
│   │   ├── values.yaml            # Production defaults
│   │   └── values.minikube.yaml   # Local development overrides
│   └── python/                    # Hash-pinned requirement exports the images install from
├── dev/gitlab-fixtures/           # Production-shaped repo trees: the fake backend's and the local GitLab's seed
├── docs/                          # adr/, ecosystem/, ops/, notes/
├── tests/repo/                    # Repository contracts: chart env, docs, CI scripts, observability
│
└── scripts/                       # Development & build scripts
    ├── gate.sh                    # Everything CI runs, in CI's order
    ├── minikube-dev-setup.sh      # Local GitLab + minikube setup
    ├── build-images.sh            # Image builds into minikube
    └── dev/                       # Local GitLab: gitlab-up.sh, seed_gitlab.py, day1_live_e2e.py
```

## Features

| Feature | Description |
|---------|-------------|
| **Two-phase spec/cluster form** | Specs (flavors) set the nodepools a cluster starts with, presets and locked values; clusters fill the rest. The create form shows a locked value read-only, prefills presets, starts each nodepool (and one added at create) with the team's machine-config defaults, picks configs and hardware types from `mc-files/` (the generic network template `nm-conf-template.bu`, written as plain `nm-conf`, first and the default when the repo has it), and shows day1's problems at their fields (ADR-0026 to ADR-0029). |
| **Marketplace addon picker** | Browse and select Day2 addons from a marketplace UI on the spec creation/edit pages. Configure which fields are overrideable per cluster. |
| **YAML fields everywhere** | Dynamic form fields accept plain YAML — no JSON syntax required. Scalars (`high-perf-tuned`), maps, and lists all work naturally. |
| **Sites and MCEs from GitLab folders** | Site and MCE dropdowns list the day1 repo's folders. They are read-only: Wingman never creates a site or an MCE (ADR-0018). |
| **OCP versions per MCE** | The OpenShift version dropdown offers the day1 repo's upgrade ladder (`upgrade/ladder.yaml`) in the minors the chosen MCE can host (`upgrade/mces/<mce>.yaml`); an MCE without its file offers none, and create refuses a version the MCE can't host. |
| **Open folder in GitLab** | Each installed chart's ⋮ menu links to its folder in the team repo. |
| **In-app documentation** | `/docs` route with full platform guide, concept explanations, worked examples, and troubleshooting. |
| **Aggregated approvals** | Approvals page aggregates open MRs from the day1, specs and every Day2 team repo in one view. |
| **Reserved template inputs** | `cluster_name`, `site`, `mce` and `openshift_release_version` are set by the create form itself — they are not part of the dynamic variable form and always override spec presets in Jinja2 rendering. |
| **Cluster nodes by NodePool** | The cluster page's Nodes tab shows each NodePool's nodes from the cluster's MCE: what is there, what a short pool is missing and why (no free Agent, and why each matching one is not free), and which node an update is working on, traced Machine → AgentMachine → Agent → server. server-scan adds each server's health and link, and the servers it places in the cluster that no Machine leads to. An admin can start the platform's `uninstall-server-from-hc` workflow on one node and follow its run; the workflow owns the procedure and its checks (ADR-0038). Needs `CLUSTER_STATUS_ENABLED`; `SERVER_SCAN_URL` and `WORKFLOWS_API_URL` add the rest. |
| **A cluster's network from Git** | The cluster page's **HostedCluster & network** card shows the VLAN and the /24 segment from the cluster file, which the allocate-segment workflow writes (Git is the source of truth). With `SEGMENTS_MANAGER_URL`, segments-manager adds the segment's EPG and is checked against the file: a VLAN, cluster or status that disagrees is a warning, and segments-manager down never hides the file's values (ADR-0039). Nothing is written to segments-manager. |
| **InfraEnv smart dropdown** | When a spec template contains an `infra_env` variable, the cluster creation form fetches available InfraEnv CRDs from the selected MCE hosting cluster and presents them as a dropdown. day1 keeps each hub's list for `MCE_INFRAENV_CACHE_SECONDS` (10 minutes). Falls back to plain text input when `CLUSTER_STATUS_ENABLED=false`. |
| **A suggested cluster name** | Creating from a flavor, the form fills in `ocp4-<env>-<flavor>-<site>-<letter>`: the MCE's env and the first letter no cluster or open create MR has. The name stays editable. A new cluster's sequence is one letter, `a` to `z`, never a number (ADR-0040). |
| **Nodepools sized by a ratio** | A flavor may give its nodepools a ratio (`nodepool_ratio: [1, 2, 1]`): the create form asks for one size and sets each nodepool's replicas to its ratio times that size; create refuses replicas off the ratio (ADR-0040). |
| **Create through the provision-cluster workflow** | With `DAY1_PROVISIONER=workflow` (off by default), Create renders and checks the file as before and then starts the platform's `provision-cluster` workflow, which reserves the segment, opens the merge request and waits for it; the page shows the run's phase, its merge request and its error (ADR-0042). Modify, delete, sync and import still open Wingman's merge requests. |

## Deployment

See **[deploy/helm/wingman/README.md](deploy/helm/wingman/README.md)** for Helm chart deployment instructions.

## API Reference

Every route needs a session token (`Authorization: Bearer <token>`, from login) except
`GET /api/auth/config`, `POST /api/auth/callback`, `POST /api/auth/dev-login`, the GitLab webhook
and the health and metrics routes. A change needs the admin role and opens a merge request: it
answers with the MR, and nothing changes until the MR is merged. Updates and deletes carry the
`last_commit_id` they were based on, and are refused with `409 REVISION_CONFLICT` if the file has
moved on (ADR-0006). Every error is an RFC 9457 problem with a stable `code` (ADR-0004). On its
own port, each service also serves its OpenAPI schema (`/openapi.json`, browsable at `/docs`).
Changes since the legacy services:
[day1](docs/notes/2026-11-07-day1-api-changes.md), [day2](docs/notes/2026-11-07-day2-api-changes.md).

### Day1 Service (Port 8001)

`site` and `mce` query parameters are optional on a cluster's routes: cluster names are unique.

#### Login and build

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/auth/config` | Where the login page sends the browser, and whether dev login is on |
| `POST` | `/api/auth/callback` | Exchange the OpenShift OAuth code for a Wingman session (403 in no Wingman group) |
| `POST` | `/api/auth/dev-login` | A session without OpenShift; 404 unless `DEV_AUTH_ENABLED` |
| `GET` | `/api/auth/me` | The signed-in user and role |
| `GET` | `/api/day1/build` | The `version` and `commit` the service runs |

#### Clusters

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day1/clusters` | Every cluster file; off-convention and unparsable ones are flagged, not hidden |
| `POST` | `/api/day1/clusters` | Create a cluster from a spec: opens the MR that adds its file (`201`), or with `DAY1_PROVISIONER=workflow` starts the platform's `provision-cluster` workflow and answers its run (`202`, ADR-0042) |
| `GET` | `/api/day1/clusters/provisioner` | What Create does here: `{"mode": "merge-request" \| "workflow"}` |
| `GET` | `/api/day1/clusters/{name}/provision-run` | The new cluster's provision-cluster run: the workflow's status, phase, merge request and error (404 none; 501 in merge-request mode) |
| `POST` | `/api/day1/clusters/preview` | Exactly the file a create would commit, after every check a create runs |
| `GET` | `/api/day1/clusters/drift-summary` | Drift of every cluster |
| `GET` | `/api/day1/clusters/name-suggestion` | A free name for a new cluster from a flavor (`?site=&mce=&flavor=`, ADR-0040) |
| `POST` | `/api/day1/clusters/bulk-status` | Live status of many clusters |
| `GET` | `/api/day1/clusters/{name}` | The cluster's file, values and naming |
| `PATCH` | `/api/day1/clusters/{name}` | Modify the cluster (opens the MR that replaces its file) |
| `DELETE` | `/api/day1/clusters/{name}` | Delete the cluster (opens the MR that removes its file) |
| `GET` | `/api/day1/clusters/{name}/delete-workflow` | The newest delete-cluster workflow run (501 until the workflow exists, ADR-0033) |
| `POST` | `/api/day1/clusters/{name}/delete-workflow` | Start the delete-cluster workflow, with `{"confirm": true}` (admin; 501 until it exists) |
| `GET` | `/api/day1/clusters/{name}/network` | The cluster's VLAN and segment from its file, the EPG segments-manager records for that segment, and where segments-manager disagrees with the file (`ledger` is `null` when segments-manager is off; `ledger_error` when it failed, never a failed read; ADR-0039) |
| `GET` | `/api/day1/clusters/{name}/nodes` | The cluster's NodePools and their nodes from its MCE, joined to server-scan's servers and their newest uninstall runs, plus the servers no Machine leads to (501 when `CLUSTER_STATUS_ENABLED` is off; ADR-0038) |
| `POST` | `/api/day1/clusters/{name}/nodes/{server_id}/uninstall` | Start the platform's `uninstall-server-from-hc` workflow on one node, with `{"server_name": "<its name>"}` (admin; 501 without `SERVER_SCAN_URL` and `WORKFLOWS_API_URL`; never retried, so a lost answer is `504 AMBIGUOUS_WRITE`) |
| `GET` | `/api/day1/clusters/{name}/current-yaml` | The file's text on the default branch |
| `GET` | `/api/day1/clusters/{name}/history` | Commits that changed the file |
| `GET` | `/api/day1/clusters/{name}/drift` | The cluster against its flavor: the locked values its file does not hold, and its missing Day2 add-ons |
| `POST` | `/api/day1/clusters/{name}/sync/preview` | What syncing the cluster to its flavor would write: each locked value it does not hold, the configs removed, the nodepools whose nodes roll, and what blocks it (`hardware` choices when a nodepool's network config can't be read) |
| `POST` | `/api/day1/clusters/{name}/sync` | Open one day1 MR that sets those values; refused unless `confirm_removals` names exactly the preview's removals |
| `GET` | `/api/day1/clusters/{name}/status` | The HostedCluster and NodePools on the MCE hub (`?mce=`; 501 when live status is off) |
| `GET` | `/api/day1/clusters/{name}/status/stream` | The same as server-sent events, every `DAY1_STATUS_POLL_SECONDS` |

#### Sites and MCEs (read-only, ADR-0018)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day1/sites` | Site folders of the day1 repo |
| `GET` | `/api/day1/sites/{site}/mces` | MCE folder names under a site |
| `GET` | `/api/day1/mces` | Every MCE (or one site's, `?site=`), with its default mastertag, hub version and naming |
| `GET` | `/api/day1/mces/{mce}/openshift-versions` | The releases a new cluster on the MCE may use (`upgrade/` in the day1 repo), newest first, with `problems` when its files are missing or broken |
| `GET` | `/api/day1/mces/{mce}/infraenvs` | InfraEnv names on the MCE hub (501 when live status is off) |
| `GET` | `/api/day1/machine-configs` | The machine configs a nodepool can use (`mc-files/` in the day1 repo: static configs and network hardware types, `generic` first when the generic template exists) and the specs repo's nodepool defaults |

#### Specs (presets for the create form)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day1/specs` | Every spec; one that does not parse carries `load_error` instead of vanishing |
| `POST` | `/api/day1/specs` | Create a spec (opens an MR) |
| `GET` | `/api/day1/specs/template` | The shared `cluster-template.j2` |
| `GET` | `/api/day1/specs/template/schema` | The template's inputs as a form schema; reserved inputs only with `?include_reserved=true` |
| `GET` | `/api/day1/specs/{name}` | One spec, with the shared template filled in |
| `PUT` | `/api/day1/specs/{name}` | Update a spec (opens an MR) |
| `DELETE` | `/api/day1/specs/{name}` | Delete a spec (opens an MR) |
| `GET` | `/api/day1/specs/{name}/history` | Commits that changed the spec's file |
| `GET` | `/api/day1/specs/{name}/at/{sha}` | The spec file's text at a commit |
| `GET` | `/api/day1/specs/{name}/clusters` | Clusters created from the spec, with their drift |
| `GET` | `/api/day1/specs/{name}/drift` | Drift of every cluster created from the spec |
| `POST` | `/api/day1/specs/{name}/import/preview` | Each picked existing cluster against the spec: whether it can join (`ready`, `relink`, `linked`, `refused`) and what will show as drift |
| `POST` | `/api/day1/specs/{name}/import` | Link up to 50 existing clusters to the spec: one MR that writes only each file's flavor header |

#### Approvals and audit

An MR is `(repo, iid)`: `?repo=day1` (the default) or `?repo=specs` (ADR-0007).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day1/approvals` | Open Wingman MRs in both projects |
| `GET` | `/api/day1/approvals/{iid}` | One MR and its diff; `mr.sha` is what an approval must name |
| `PUT` | `/api/day1/approvals/{iid}` | Commit edited files on top of the MR's branch (never a force-push) |
| `POST` | `/api/day1/approvals/{iid}/approve` | Approve and merge the reviewed commit (403 for the requester, 409 if the branch moved) |
| `POST` | `/api/day1/approvals/{iid}/reject` | Close the MR without merging |
| `GET` | `/api/day1/audit/commits` | Newest commits on both default branches (`?per_page=&page=`) |
| `GET` | `/api/day1/audit/merge-requests` | Newest Wingman MRs in both projects, any state |
| `GET` | `/api/day1/audit/commits/{repo}/{sha}/diff` | What one commit changed |
| `POST` | `/api/webhooks/gitlab` | Clear what a push or MR event in the day1 or specs project made stale (`X-Gitlab-Token`; 404 unless `GITLAB_WEBHOOK_SECRET` is set) |

### Day2 Service (Port 8002)

`{cluster}` is a cluster id (`hub`, `mce:<site>:<env>:<mce>`,
`hosted:<site>:<env>:<mce>:<cluster>`, `upi:<site>:<env>:<cluster>`) or a bare
name that names one destination (`?mce=` when it names more than one).

#### Catalog and lints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day2/build` | The `version` and `commit` the service runs |
| `GET` | `/api/day2/gitlab-info` | Where the sigs group lives, for links |
| `GET` | `/api/day2/teams` | Every team: each project directly in the sigs group |
| `GET` | `/api/day2/addons` | Every catalog entry (`operators/<chart>/`), or one team's (`?team=`) |
| `GET` | `/api/day2/addons/{team}/{addon}` | One catalog entry |
| `GET` | `/api/day2/addons/{team}/{addon}/versions` | The chart repo's branches, default branch first |
| `GET` | `/api/day2/addons/{team}/{addon}/values` | The chart's own `values.yaml` at `?version=` |
| `GET` | `/api/day2/lints` | Every check on the team repos (`?team=`): render_chain.py's rules plus Wingman's own |

#### Destinations and their charts

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day2/clusters` | Every destination from day1 and the team repos (`?kind=&site=&env=`) |
| `GET` | `/api/day2/clusters/{cluster}` | One destination |
| `GET` | `/api/day2/clusters/{cluster}/addons` | The charts on it: its own folders and fleet defaults |
| `GET` | `/api/day2/clusters/{cluster}/addons/{team}/{addon}` | The chart's merged values, layer by layer, with provenance |
| `POST` | `/api/day2/clusters/{cluster}/addons/{team}/{addon}` | Install the chart (opens an MR) |
| `PUT` | `/api/day2/clusters/{cluster}/addons/{team}/{addon}` | Change its values or revision (opens an MR) |
| `DELETE` | `/api/day2/clusters/{cluster}/addons/{team}/{addon}` | Remove its folder (opens an MR); ArgoCD orphans the workload, which keeps running |
| `POST` | `/api/day2/clusters/{cluster}/addons/bulk` | Install several charts: one MR per team, all validated before any opens |
| `POST` | `/api/day2/merge-preview` | The merged values with edited cluster values, before writing them |
| `GET` | `/api/day2/clusters/{cluster}/history` | Commits that touched the destination's folders, across team repos |
| `GET` | `/api/day2/clusters/{cluster}/upgrade-check` | Version-pinned charts that would fall back to their team default at `?to=` |

#### Approvals and audit

An MR is `(team, iid)`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day2/approvals` | Open Wingman MRs across every team repo, newest first |
| `GET` | `/api/day2/approvals/{team}/{iid}` | One MR and its diff |
| `PUT` | `/api/day2/approvals/{team}/{iid}` | Push edits of files the MR changes onto its branch |
| `POST` | `/api/day2/approvals/{team}/{iid}/approve` | Approve and merge the reviewed commit (403 for your own change, 409 if it moved) |
| `POST` | `/api/day2/approvals/{team}/{iid}/reject` | Close without merging |
| `GET` | `/api/day2/audit/commits` | Commits across team repos, newest first (`?per_page=&page=`) |
| `GET` | `/api/day2/audit/merge-requests` | Wingman MRs in any state across team repos |
| `GET` | `/api/day2/audit/commits/{sha}/diff` | What a commit changed, in the team repo that has it (`?team=`) |

### Health and metrics (both services)

On each service's own port: nginx routes only `/api/...` to the services, so these are not
reachable through the Route.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health/live` | The process serves requests (the liveness probe); never checks dependencies |
| `GET` | `/healthz` | The same, at the legacy probe path |
| `GET` | `/health/ready` | Every readiness check (GitLab) passes; 503 otherwise (the readiness probe) |
| `GET` | `/metrics` | Prometheus metrics (`docs/ops/metrics.md`) |

## Environment Variables

Both services read their settings at start-up and refuse an unsafe or
incomplete configuration (ADR-0009). The chart sets them
(`deploy/helm/wingman/templates/configmap.yaml`, `secret.yaml`);
`tests/repo/test_chart_env_contract.py` fails when the chart and the settings
classes disagree. Defaults are in
`packages/wingman-core/src/wingman_core/settings.py` (shared) and each
service's `settings.py`.

### Both services

```env
# Required
JWT_SECRET_KEY=at-least-32-characters      # the same for day1 and day2
GITLAB_URL=https://gitlab.example.com      # not needed with WINGMAN_GIT_BACKEND=fake
GITLAB_TOKEN=<service account token>       # not needed with WINGMAN_GIT_BACKEND=fake

# Optional
GITLAB_VERIFY_TLS=true                     # an internal CA goes in SSL_CERT_FILE
GITLAB_CONNECT_TIMEOUT_SECONDS=5
GITLAB_READ_TIMEOUT_SECONDS=20
JWT_EXPIRY_HOURS=8                         # 1 to 24
WINGMAN_ADMIN_GROUPS=wingman-admins        # comma-separated OpenShift groups
WINGMAN_VIEWER_GROUPS=wingman-viewers
WINGMAN_ENVIRONMENT=production             # development or test allow the fake backend
WINGMAN_GIT_BACKEND=gitlab                 # fake: in-memory, seeded from WINGMAN_FIXTURES_DIR
WINGMAN_FIXTURES_DIR=                      # default dev/gitlab-fixtures
WINGMAN_VERSION=dev                        # set by the image (docs/ops/images.md)
WINGMAN_COMMIT=unknown                     # set by the image
```

### Day1 Service

```env
# Required
DAY1_GITLAB_PROJECT_ID=gitops-day1/platform-config   # a numeric id or a group/project path
SPECS_GITLAB_PROJECT_ID=wingman/cluster-specs

# Login: complete OpenShift OAuth settings, or dev login (never in production)
OPENSHIFT_OAUTH_HOST=oauth-openshift.apps.example.com
OPENSHIFT_API_HOST=api.example.com:6443
OPENSHIFT_OAUTH_CLIENT_ID=wingman-app
OPENSHIFT_OAUTH_CLIENT_SECRET=<secret>
OPENSHIFT_OAUTH_REDIRECT_URI=https://wingman.apps.example.com/login
OPENSHIFT_SSL_VERIFY=true                 # true, false, or a CA bundle path
OPENSHIFT_TIMEOUT_SECONDS=10
DEV_AUTH_ENABLED=false
DEV_AUTH_SECRET=                          # at least 32 characters when dev login is on

# Optional
SPECS_ROOT_PATH=specs                     # the spec files' folder in the specs project
DAY1_CLUSTER_NAME_STRIP_PREFIX=ocp4-      # ADR-0015: "" for the GitHub sandbox (legacy name: MCE_CLUSTER_NAME_PREFIX)
DAY1_CACHE_TTL_SECONDS=30                 # at most 60 (ADR-0011); how often a branch head is checked (ADR-0035)
GITLAB_WEBHOOK_SECRET=                    # empty: the webhook answers 404
DAY2_SERVICE_URL=http://wingman-day2:8002 # for drift
DAY2_TIMEOUT_SECONDS=5

# Live MCE status (enables the InfraEnv dropdown, cluster health and the nodes by NodePool;
# the nodes need more MCE reads: deploy/helm/wingman/README.md, the MCE token's RBAC)
CLUSTER_STATUS_ENABLED=false
MCE_API_DOMAIN=mgmt.example.com           # https://api.<mce>.<domain>:6443
MCE_TOKENS_FILE=/etc/wingman/mce-tokens/tokens
MCE_SSL_VERIFY=true                       # true, false, or a CA bundle path
MCE_TIMEOUT_SECONDS=10
MCE_INFRAENV_NAMESPACE=                   # empty = all namespaces (the chart does not set it yet)
MCE_INFRAENV_CACHE_SECONDS=600            # how long a hub's InfraEnv list is kept; 0 = read every time
DAY1_STATUS_POLL_SECONDS=30               # the live status stream (the chart does not set it yet)

# The nodes' servers from server-scan, uninstall through the workflows orchestrator (ADR-0038; off by default)
SERVER_SCAN_URL=                          # e.g. http://server-scan-api.<ns>.svc:8000; empty: nodes without servers, no uninstall
SERVER_SCAN_UI_URL=                       # where node links point (server-scan's UI); default SERVER_SCAN_URL
SERVER_SCAN_TOKEN=                        # a server-scan viewer token (Bearer), from a Secret; empty: no header
SERVER_SCAN_SSL_VERIFY=true               # true, false, or a CA bundle path
SERVER_SCAN_TIMEOUT_SECONDS=10
WORKFLOWS_API_URL=                        # e.g. http://workflows-orchestrator-api.<ns>.svc:8080; needs SERVER_SCAN_URL
WORKFLOWS_SSL_VERIFY=true                 # true, false, or a CA bundle path
WORKFLOWS_TIMEOUT_SECONDS=10
DAY1_FAKE_FLEET=false                     # development only: an MCE, server-scan, the orchestrator and segments-manager in memory, from dev/fleet-fixtures
DAY1_PROVISIONER=merge-request            # how a create is proposed (ADR-0042): merge-request, or workflow (start provision-cluster; needs WORKFLOWS_API_URL)

# segments-manager: the cluster's EPG, checked against the file (ADR-0039; off by default; read only)
SEGMENTS_MANAGER_URL=                     # its API, e.g. http://segments-manager.<ns>.svc:8000; empty: no EPG
SEGMENTS_MANAGER_UI_URL=                  # where the cluster page's links point (its UI); default SEGMENTS_MANAGER_URL; both empty: no link
SEGMENTS_MANAGER_SSL_VERIFY=true          # true, false, or a CA bundle path
SEGMENTS_MANAGER_TIMEOUT_SECONDS=5
```

### Day2 Service

```env
# Required
DAY2_SIGS_GROUP_PATH=gitops-day2-prod/sigs           # every project directly in it is a team
DAY1_GITLAB_PROJECT_ID=gitops-day1/platform-config   # read-only for day2 (versions, hosted clusters)

# Optional
DAY2_GITOPS_BRANCH=main          # the branch the platform reads; MRs target it
DAY2_CACHE_TTL_SECONDS=15        # at most 60 (ADR-0011); how often a branch head is checked (ADR-0035)
```

### Frontend

The web app uses relative API paths (`/api/day1`, `/api/day2`, `/api/auth`) — no build-time env vars
are required. In a deployment nginx routes them to the services; locally, `next dev` proxies them when
`WINGMAN_DEV_DAY1_URL` and `WINGMAN_DEV_DAY2_URL` are set (development server only; see
[apps/web/README.md](apps/web/README.md#running-against-local-services)).

## Development Setup

See **[DEVELOPMENT.md](DEVELOPMENT.md)** for running the stack locally, the architecture, testing and contributing.

### Prerequisites

- Node.js 24+
- Python 3.13+ and [uv](https://docs.astral.sh/uv/)
- Podman or Docker (images, and the local GitLab)
- A GitLab instance, or none: the services can run on an in-memory GitLab
- An OpenShift cluster for OAuth, or dev login locally

### Local Development

```bash
uv sync --locked --all-packages --all-groups --all-extras
cd apps/web && npm ci
```

Then start both services on the in-memory GitLab and the web dev server in front of them, as
[DEVELOPMENT.md](DEVELOPMENT.md#running-locally) shows.

### Docker Build

Every merge to main is a release: CI computes its version from the Conventional Commit
subjects, tags it `v3.0.1`, and publishes the images as `3.0.1` (plus the moving `3.0`, `3`,
`latest` and a `sha-<short sha>` tag). Production deploys a full version, never `latest`, so
every release is traceable and rollbacks are one command (docs/ops/images.md).

To build a release yourself, check out its tag and name the images by its version:

```bash
git checkout v3.0.1
VERSION=3.0.1
COMMIT=$(git rev-parse HEAD)

# Build all three for production (linux/amd64, clean)
docker buildx build --platform linux/amd64 --no-cache --build-arg VERSION=$VERSION --build-arg COMMIT=$COMMIT -t wingman-day1:$VERSION -f apps/day1-service/Dockerfile . --load
docker buildx build --platform linux/amd64 --no-cache --build-arg VERSION=$VERSION --build-arg COMMIT=$COMMIT -t wingman-day2:$VERSION -f apps/day2-service/Dockerfile . --load
docker buildx build --platform linux/amd64 --no-cache --build-arg VERSION=$VERSION --build-arg COMMIT=$COMMIT -t wingman-web:$VERSION -f apps/web/Dockerfile . --load

# Save for air-gapped / on-prem transfer
docker save wingman-day1:$VERSION | gzip > wingman-day1-$VERSION.tar.gz
docker save wingman-day2:$VERSION | gzip > wingman-day2-$VERSION.tar.gz
docker save wingman-web:$VERSION  | gzip > wingman-web-$VERSION.tar.gz
```

Deploy them with `--set image.day1.tag=$VERSION --set image.day2.tag=$VERSION --set image.web.tag=$VERSION`
(or set the tags in your values file).

## Authentication & Authorization

### Authentication Flow

1. The login page asks `GET /api/auth/config` where to send the browser, and redirects to OpenShift OAuth
2. User authenticates with OpenShift credentials
3. OpenShift redirects back to `/login` with an authorization code, which the page sends to `POST /api/auth/callback`
4. Day1 exchanges the code for an OpenShift access token
5. Day1 fetches the user and their groups from the OpenShift API
6. Day1 issues a JWT with the role embedded (day2 checks it with the same `JWT_SECRET_KEY`)
7. Frontend stores JWT, includes in Authorization header

### RBAC

Roles are determined by OpenShift group membership:

| Role | Groups | Permissions |
|------|--------|-------------|
| **admin** | `WINGMAN_ADMIN_GROUPS` | Full access (create, update, delete, approve) |
| **viewer** | `WINGMAN_VIEWER_GROUPS` | Read-only access |

The role is embedded in the JWT at login time and validated on each request. Someone in
neither group cannot sign in; admin wins over viewer.

## GitLab Structure

### Day1 and specs repositories

```
gitops-day1/platform-config/            # DAY1_GITLAB_PROJECT_ID
├── sites/
│   ├── configValues.yaml
│   └── {site}/
│       ├── values.yaml
│       └── mces/{mce}/
│           ├── values.yaml                     # the MCE's defaults: its mastertag prefills a new cluster's version, when the MCE offers it
│           ├── version.yaml                    # the hub's own version
│           └── hostedClusters/{cluster}.yaml   # one values file per hosted cluster: the only file Wingman writes here
└── upgrade/                            # read by the cluster-upgrade workflow and by Wingman (ADR-0034)
    ├── ladder.yaml                     # the verified releases, one or more per minor
    └── mces/{mce}.yaml                 # the minors the MCE can host: the create form offers the ladder's rungs in them

wingman/cluster-specs/                  # SPECS_GITLAB_PROJECT_ID
├── cluster-template.j2                 # the shared template every cluster file is rendered from
└── specs/{name}.yaml                   # one file per spec (SPECS_ROOT_PATH)
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

- **Spec**: A preset for the create form (nodepool shape, preset template inputs, the Day2 addons its clusters should get); every spec fills the one shared `cluster-template.j2`
- **Cluster**: An actual cluster instance, optionally linked to a spec
- **Drift**: A value the cluster's flavor locks that its file does not hold, or an add-on the flavor lists that is not installed (ADR-0036); a different version is reported, not drift (ADR-0025). Sync to flavor fixes the values in one MR (ADR-0037)

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

Metrics, alerts and their runbook: `docs/ops/metrics.md`, `docs/ops/runbook.md`.

### Logs

Both services log to stdout. In Kubernetes:

```bash
kubectl logs -n wingman -l app.kubernetes.io/component=day1
kubectl logs -n wingman -l app.kubernetes.io/component=day2
```

A configuration a service refuses (ADR-0009) is logged at start-up, naming the variable, and the pod exits.

## Contributing

### Code Style

- **Python**: type hints everywhere; `ruff` and `ty` (ADR-0008) on the strict bar (`scripts/python-packages.sh`)
- **TypeScript**: Use strict mode, prefer interfaces over types
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `ci:`, `test:`, `refactor:`), one unit of work each

### Adding a New Feature

1. Backend code goes in its layer (ADR-0001): `domain/`, `application/` (use cases over the ports in
   `ports.py`), `infrastructure/` (adapters and fakes), `api/v1/` (routers); `uv run lint-imports` holds the
   layers. GitLab only through `GitLabPort` (ADR-0002). DEVELOPMENT.md walks through a new endpoint.
2. Shared code goes in `packages/wingman-core`
3. Frontend pages go in `app/(app)/`, components in `components/`
4. Add API types to `types/day1.ts`, `types/day2.ts` or `types/problem.ts` (`types/index.ts` re-exports them)

### Testing Locally

```bash
scripts/gate.sh python   # ruff, ty, import-linter, pytest, pip-audit, deptry
scripts/gate.sh web      # npm ci, npm audit, lint, typecheck, build
scripts/gate.sh          # everything CI runs, in CI's order
```

## Troubleshooting

### "Insufficient scope" errors

The GitLab access token needs `api` scope. Regenerate it with full API access.

### MR approval fails

1. Check the service account can merge into the target branch of the project
2. Check GitLab project settings don't prevent the approval
3. Check logs for the actual GitLab error response

### Data from GitLab looks stale

Each replica checks where a repo's branch points at most every `DAY1_CACHE_TTL_SECONDS` (30 s)
or `DAY2_CACHE_TTL_SECONDS` (15 s), never over 60 s, and reads the repo again only when it
moved (ADR-0011, ADR-0035); merge requests and history are kept for the same TTL. Wingman's
own writes clear what they change, and day1's GitLab webhook (`GITLAB_WEBHOOK_SECRET`) clears
what a change made in GitLab directly touched; otherwise wait for the TTL.

### Frontend shows stale data

React Query caches data for 2 minutes. Hard refresh (Ctrl+Shift+R) clears the cache, or wait for `staleTime` to expire.

## License

Proprietary - Internal use only.
