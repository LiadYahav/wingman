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
│   │   │                          #   clusters, specs, addons, lints, quick-links,
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
│   │   │   ├── ports/             # day1's own ports (server-scan's in server_scan.py)
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
| **Aggregated approvals** | Approvals page aggregates open MRs from the day1, specs and every Day2 team repo in one view. The `provision-cluster` workflow's day1 MRs are listed too, with a badge, and open in GitLab, where they are reviewed and merged (ADR-0042's amendment). |
| **Reserved template inputs** | `cluster_name`, `site`, `mce` and `openshift_release_version` are set by the create form itself — they are not part of the dynamic variable form and always override spec presets in Jinja2 rendering. |
| **Cluster nodes by NodePool** | The cluster page's Nodes tab shows each NodePool's nodes from the cluster's MCE: what is there, what a short pool is missing and why (no free Agent, and why each matching one is not free), and which node an update is working on, traced Machine → AgentMachine → Agent → server. server-scan adds each server's health and link, and the servers it places in the cluster that no Machine leads to. An admin can start the platform's `uninstall-server-from-hc` workflow on one node and follow its run; the workflow owns the procedure and its checks (ADR-0038). Needs `CLUSTER_STATUS_ENABLED`; `SERVER_SCAN_URL` and `WORKFLOWS_API_URL` add the rest. |
| **A cluster's network from Git** | The cluster page's **HostedCluster & network** card shows the VLAN and the /24 segment from the cluster file, which the allocate-segment workflow writes (Git is the source of truth). With `SEGMENTS_MANAGER_URL`, segments-manager adds the segment's EPG and is checked against the file: a VLAN, cluster or status that disagrees is a warning, and segments-manager down never hides the file's values (ADR-0039). Nothing is written to segments-manager. |
| **InfraEnv smart dropdown** | When a spec template contains an `infra_env` variable, the cluster creation form fetches available InfraEnv CRDs from the selected MCE hosting cluster and presents them as a dropdown. day1 keeps each hub's list for `MCE_INFRAENV_CACHE_SECONDS` (10 minutes). Falls back to plain text input when `CLUSTER_STATUS_ENABLED=false`. |
| **A suggested cluster name** | Creating from a flavor, the form fills in `ocp4-<env>-<flavor>-<site>-<letter>`: the MCE's env and the first letter no cluster or open create MR has. The name stays editable. A new cluster's sequence is one letter, `a` to `z`, never a number (ADR-0040). |
| **Nodepools sized by a ratio** | A flavor may give its nodepools a ratio (`nodepool_ratio: [1, 2, 1]`): the create form asks for one size and sets each nodepool's replicas to its ratio times that size; create refuses replicas off the ratio (ADR-0040). |
| **Wingman picks the MCE** | The create form asks for the site, prod or prep and the OpenShift version (the owner and the flavor's nodepools refine it), never for the MCE, and Wingman picks it: of the MCEs at the site whose name says the env, those that host the version, have at least `PLACEMENT_MIN_FREE_PODS` free pods on their workers (allocatable pods less pods in use; masters, infra and tainted nodes left out), have enough healthy free servers of each node type the nodepools need (free Agents in that InfraEnv, healthy in server-scan) and can be read, the one with the fewest clusters of this owner, then the fewest clusters, then the most usable spare servers in server-scan. The form shows every candidate's numbers in one row each, the pick's row marked, with each row's reasons and why the pick won in tooltips; an admin may choose another MCE that passes every check, with a reason, and the MR description records it all (ADR-0050). With live status off it decides on the day1 repo and server-scan, and the free pods and servers are "not checked", shown as such. |
| **Add-ons: catalog, defaults and overrides** | The **Addons** page lists each team's add-ons (its catalog, `operators/<chart>/` in the team repo) and their fleet defaults. A team admin creates an add-on and edits it there (Edit add-on: its deploy config and its Sig values, `operators/<chart>/values.yaml`; values go chart values → Sig values → cluster values); an add-on's page (`/addons/<team>/<add-on>`) has its deploy config and values, its OCP-version pins, and per fleet scope (hosted clusters, MCEs, the hub, UPI) whether it is a default there and that default's values. Each env (`values-<env>.yaml`) and each MCE, hosted cluster or UPI cluster (`values-<name>.yaml`) can get values of its own, and an add-on wanted on some MCEs only is deployed on those MCEs, one install merge request each. Which add-ons a hosted cluster has of its own comes from its flavor and the create form. Every change is previewed and confirmed against that preview (ADR-0053). One cluster's add-ons stay on that cluster's page. |
| **Create through the provision-cluster workflow** | With `DAY1_PROVISIONER=workflow` (off by default), Create renders and checks the file as before and then starts the platform's `provision-cluster` workflow, which reserves the segment, opens the merge request and waits for it; the page shows the run's phase, its merge request and its error (ADR-0042). Modify, delete, sync and import still open Wingman's merge requests. In either mode, the workflow's open merge request (branch `provision-cluster/<stem>`) holds its cluster's name, refuses a second create of it and counts on its MCE for placement (ADR-0042's amendment). |
| **Segments** | segments-manager's page, rebuilt in Wingman for its admins (`/segments`, from the top bar's area switch, with its own sidebar and brand): a card per site (allocated out of total, by type), then every segment with the original's columns (Type, Site, VLAN ID, EPG Name, Network Segment, DHCP, Cluster, Status), sorting, status tabs, the site filter, an Excel-style filter on every column, search, a column picker, copy on click and a CSV or Excel file of the rows shown, re-read every 30 seconds with a dot that turns red (showing the last good data) when segments-manager does not answer. Every filter lives in the URL, so the cluster page links to its own segments; a holder that is a hosted cluster links to its page, and a row where segments-manager disagrees with the cluster file (ADR-0039's checks, on data already read) is marked. Read only: nothing is written to segments-manager (ADR-0047). Needs `SEGMENTS_MANAGER_URL`. |
| **Server Scan** | server-scan's UI, rebuilt in Wingman for its admins one page at a time (`/server-scan`, from the top bar's area switch, with server-scan's own mark and a sidebar of the pages built; ADR-0048). Its first page, **Sites**, is server-scan's landing page: cards for the fleet, each installation type (UPI, hosted cluster, MCE), available and installed, then one per configured site (and Unassigned when a server's name carries no site), each with its critical, major, warning, maintenance and unknown counts, installed and available, and a bar per vendor, as server-scan counts them, read with the viewer token; every count opens the Servers page with its filter. Its second page, **Servers** (`/server-scan/servers`), is server-scan's fleet table: search (text, "exact", /regex/), its six dropdowns and five toggles with counts, the MCE, hosted-cluster and UPI-cluster sidebar, sort, 50 rows a page, every filter in the URL under server-scan's names, Excel and CSV export, read every 30 seconds from day1's one cached read of server-scan (a `304` when nothing changed); and its one write, a server's maintenance on (with server-scan's reason and an expected end) and off, logged with the person's name, with server-scan's admin token (`SERVER_SCAN_ADMIN_TOKEN`). Its third, a **server's page** (`/server-scan/servers/<id>`, from a name on Servers, in Inventory Management or on a cluster's Nodes tab), is the one record of a server: server-scan's five tabs, Overview (identity, OpenShift and the install lock, a VM's host, the health breakdown and why, maintenance with the same toggle), Hardware (CPU, memory, drives, GPUs, power), Network (BMC, NICs), Connectivity (fabric uplinks) and History (its audit trail, with server-scan's auditor token, `SERVER_SCAN_AUDITOR_TOKEN`), the tab in the URL. Its **Claude** page (`/server-scan/claude`) is server-scan's guide to its Claude Code skill: the skill's zip from server-scan with server-scan's address written in, the four setup steps, the MCP command and the skill's files, read from server-scan every minute; the personal token is made on server-scan's own Claude page, which it links to (server-scan makes one only for someone signed in to it). **Architecture** (`/server-scan/architecture`) shows server-scan's diagrams, one per collector plus the full flow, picked by tab (in the URL), each the page server-scan's UI serves, read by day1 from `SERVER_SCAN_UI_URL` with no token and shown in a sandboxed frame in Wingman's theme, never copied. **Confs** (`/server-scan/confs`), is server-scan's hardware catalog, read only: one row per server configuration (its part number, or Unmapped when no catalog entry matches; model, CPU, RAM, storage, GPUs, adapters), a row opened into the full spec, server-scan's search, and the stored confs it could not read named. **Rules & Policies** (`/server-scan/rules`) shows what server-scan runs, read only: its classification rules (the installation type each gives a server from its own fields) in the order it tries them, and its health policies by scope and severity, each condition in one line. **Events** (`/server-scan/events`) is server-scan's audit trail of the whole fleet, read only: newest first, 50 a page over its cursors, with its four filters in the URL under server-scan's names (event type, server name, user with each one's count, the last hour, day, week or month, or a custom range in Israel time), each server's name opening its page here, each event's details as on History; with the same auditor token as History. **Jobs** (`/server-scan/jobs`) is server-scan's Jobs page: a card per collector or prune CronJob it may start, with its schedule, its `values.yaml` flag and its recent runs (state, by hand and by whom, when), and each run's pod log (its last 500 lines, refreshed while the run goes on), read every 5 seconds while a run goes on, every 30 otherwise, with server-scan's admin token, which server-scan asks for on its Jobs reads too. |
| **Upgrade through the upgrade-cluster workflow** | With `DAY1_UPGRADES=true` (off by default), an admin's **Upgrade** on the cluster page's Mastertag row starts the platform's `upgrade-cluster` workflow toward a target the workflow offers; it plans and checks, then waits for approval with nothing committed. The cluster page shows the run (its phase, what it waits for, the plan, the log) and admins press its decisions; the workflow commits the versions to day1 `main` itself, and while it is on an edit may not change `mastertag` or a `workertag` (ADR-0055). In the clusters list each row shows its upgrade under its mastertag: **Upgrading** with the run's phase (what it waits for in a tooltip), or **Upgrade available → <version>** when its MCE offers a newer OpenShift (a suggestion; the workflow plans the path), with an admin's **Upgrade** opening the same dialog from the row; an **Upgrades** filter (kept in the URL) shows only those. A finished run's panel can be dismissed. Off, an admin sees Upgrade greyed out with why. |
| **Inventory Management** | A sidebar page (`/inventory`) for the orchestrator's server workflows, which everyone signed in reads: each MCE's available Agents by InfraEnv pool and hardware, as server-scan counts them; the add-server runs with their phase, server and error, herzi's included; a server's name opens its page in the Server Scan area for a person who has it (a named run is a person's, a pool draw "herzi or a person"); and, with `DAY1_ADD_SERVERS`, admins install servers (the header's **Install servers**, or a pool's row) into a pool they pick or an InfraEnv they type, by count or by name, never a server server-scan has locked; no live status needed (ADR-0057 and its amendment). Off, admins see the button disabled with the reason. Not a fleet view. |
| **Quick Links** | A launcher page for Wingman's admins (`/quick-links`): a card for the hub Wingman runs on and for every MCE of the day1 repo, by site, each opening the cluster's ArgoCD with its console beside it, then the team's own links from a ConfigMap the chart renders (`quickLinks.sections`), in the style of the team's homepage dashboard. Wingman only lists the links and never calls them, and icons ship with Wingman (ADR-0052). |

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
| `POST` | `/api/day1/clusters/preview` | Exactly the file a create would commit, after every check a create runs (with placement on, the MCE against the placement rule: an override of Wingman's pick needs `placement.reason`) |
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
| `GET` | `/api/day1/upgrades` | Every cluster's newest upgrade run, open ones first, from one cached read of the orchestrator's run list: status, phase, `waiting_for`, outcome, when it started, and where day1 has the file (any signed-in user; 501 unless `DAY1_UPGRADES`; ADR-0055's amendment) |
| `GET` | `/api/day1/clusters/{name}/upgrade-targets` | What the upgrade-cluster workflow offers to upgrade the cluster to, with its NodePools (admin; may take up to a minute; an empty list is an answer; 501 unless `DAY1_UPGRADES`; ADR-0055) |
| `POST` | `/api/day1/clusters/{name}/upgrade` | Start the upgrade-cluster workflow with one target (`target_version` or `target_minor`) and what the person chose; day1 adds who asked (admin; `202` with the run; `409 UPGRADE_ALREADY_RUNNING`; a lost answer is `504 AMBIGUOUS_WRITE`) |
| `GET` | `/api/day1/clusters/{name}/upgrade-run` | The cluster's newest upgrade run in the workflow's words: status, phase, what it waits for, plan, log, outcome (404 none) |
| `POST` | `/api/day1/clusters/{name}/upgrade-run/{decision}` | Send a decision (`approve`, `approve-admin-ack`, `continue`, `confirm-day2`, `pause`, `resume`, `abort`, `retry`), with `{"reason"?, "nodepool"?}`; the run's validator judges it (admin; `409 UPGRADE_DECISION_REFUSED` in its words) |
| `POST` | `/api/day1/clusters/{name}/upgrade-run/actions/{action_id}/{verdict}` | Approve or reject one of the upgrade agent's proposals (`verdict` is `approve` or `reject`; admin) |
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
| `GET` | `/api/day1/placement` | Where a new hosted cluster goes (`?site=&env=&version=&owner=&flavor=`, ADR-0050): every candidate MCE with its checks, clusters, this owner's clusters, spare servers and free pods, and Wingman's pick with why (with live status off, the checks that read the MCE are `not_checked`) |
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
| `POST` | `/api/day1/specs/{name}/import` | Link up to 50 existing clusters to the spec: one MR per cluster that writes only its file's flavor header, all checked before any opens (ADR-0044) |
| `GET` | `/api/day1/specs/{name}/rollout` | The rollout of the spec's newest version, one MR per cluster that follows it, from GitLab's state; reading it starts a run when work is pending (ADR-0044) |
| `POST` | `/api/day1/specs/{name}/rollout` | Reconcile now: open the cluster MRs that are missing, failed ones included (admins; 202) |

#### Approvals and audit

An MR is `(repo, iid)`: `?repo=day1` (the default) or `?repo=specs` (ADR-0007).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day1/approvals` | Open Wingman MRs in both projects, and the `provision-cluster` workflow's open day1 MRs (on `provision-cluster/<stem>`), marked `"opened_by_workflow": "provision-cluster"` (`null` on Wingman's): view only, they are reviewed and merged in GitLab (ADR-0042's amendment) |
| `GET` | `/api/day1/approvals/{iid}` | One MR and its diff; `mr.sha` is what an approval must name |
| `PUT` | `/api/day1/approvals/{iid}` | Commit edited files on top of the MR's branch (never a force-push) |
| `POST` | `/api/day1/approvals/{iid}/approve` | Approve and merge the reviewed commit (403 for the requester, 409 if the branch moved) |
| `POST` | `/api/day1/approvals/{iid}/reject` | Close the MR without merging |
| `GET` | `/api/day1/approvals/{iid}/rollout` | What merging a spec's MR will open: one MR per cluster, and the clusters that roll nodes, lose configs or need a decision (ADR-0044) |
| `GET` | `/api/day1/audit/commits` | Newest commits on both default branches (`?per_page=&page=`) |
| `GET` | `/api/day1/audit/merge-requests` | Newest Wingman MRs in both projects, any state |
| `GET` | `/api/day1/audit/commits/{repo}/{sha}/diff` | What one commit changed |
| `POST` | `/api/webhooks/gitlab` | Clear what a push or MR event in the day1 or specs project made stale (`X-Gitlab-Token`; 404 unless `GITLAB_WEBHOOK_SECRET` is set) |

#### Quick Links (admins only, ADR-0052)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day1/quick-links` | The launcher's sections and cards: the hub and every MCE's ArgoCD and console, by site, then the links file's sections, with the links file's problems ([API note](docs/notes/2026-11-12-quick-links-api.md)) |

#### Segments (admins only, ADR-0047)

Read only, from segments-manager's open GETs; `501 FEATURE_DISABLED` while `SEGMENTS_MANAGER_URL` is empty, `502 DEPENDENCY_UNAVAILABLE` when segments-manager fails ([API note](docs/notes/2026-11-13-segments-area-api.md)).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day1/segments/sites` | segments-manager's sites, in its order |
| `GET` | `/api/day1/segments/stats` | Each site's allocated and total segments, and the allocated count per type |
| `GET` | `/api/day1/segments` | Every segment (`site`, `status`, `type` filter), each holder joined to its cluster file in day1; `fresh=true` reads segments-manager's database, at most once per 5 seconds per replica |

#### Server Scan (admins only, ADR-0048)

server-scan's pages, read through day1 in server-scan's own shapes; `501 FEATURE_DISABLED` while `SERVER_SCAN_URL` is empty, `502 DEPENDENCY_UNAVAILABLE` when server-scan fails or refuses a token ([API note](docs/notes/2026-11-13-server-scan-area-api.md)).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day1/server-scan/sites` | server-scan's Sites: every configured site in its order, then `unassigned`, and the fleet, each counted per vendor, health, maintenance, installation type and OpenShift state, as server-scan counts them (cached 10 seconds per replica) |
| `GET` | `/api/day1/server-scan/classification-rules` | server-scan's enabled classification rules (what gives a server its installation type from its own fields), in its shape and the order it tries them; read now with the viewer token, not cached by day1 |
| `GET` | `/api/day1/server-scan/health-policies` | server-scan's enabled health policies (what judges a server's health), in its shape, every condition node whole; read now with the viewer token, not cached by day1 |
| `GET` | `/api/day1/server-scan/servers` | server-scan's fleet rows, every field, in its order, and `generated_at`, from the rows cache the Nodes tab and Inventory Management share; day1's own weak `ETag`, a bodiless `304` for a current `If-None-Match` |
| `PUT` | `/api/day1/server-scan/servers/{server_id}/maintenance` | Put a server into maintenance (`{reason?, expected_end?}`), as server-scan's toggle does, with its admin token; logged with the person's name. `501` without the admin token (unless server-scan runs with auth off), `504 AMBIGUOUS_WRITE` when unanswered, never retried |
| `GET` | `/api/day1/server-scan/servers/{server_id}` | One server whole, in server-scan's shape (the fields its server page reads; `reservation.held` judged by day1), with `maintenance_available`/`_detail` and `history_available`/`_detail`; read now, not cached by day1; 404 for an unknown server |
| `GET` | `/api/day1/server-scan/servers/{server_id}/vm-host` | The host a KubeVirt VM runs on, resolved now, in server-scan's shape; 404 for a server that is not a VM |
| `GET` | `/api/day1/server-scan/servers/{server_id}/events` | One page of the server's History, newest first (`cursor`, `page_size` 1-200, default 50), with server-scan's auditor token; `501` without it beside a viewer token (unless server-scan runs with auth off) |
| `DELETE` | `/api/day1/server-scan/servers/{server_id}/maintenance` | End a server's maintenance; the same rules |
| `GET` | `/api/day1/server-scan/events` | One page of the fleet's audit trail, newest first, in server-scan's shape, with its filters passed on (`event_type`, `server_name`, `actor_id`, `server_id`, `since` inclusive and `until` exclusive with their zone, `cursor`, `page_size` 1-200, default 50) and checked first; with server-scan's auditor token, as History; `501` without it beside a viewer token (`details.setting`), `422` for a cursor server-scan refuses; not cached by day1 |
| `GET` | `/api/day1/server-scan/events/actors` | Who wrote the audit trail, busiest first, each with its type, display and event count (the Events page's User filter); the auditor token and its `501`, as the list; not cached by day1 |
| `GET` | `/api/day1/server-scan/skill` | server-scan's Claude Code skill in its shape (name, description, `when_to_use`, `allowed_tools`, version, files), with `server_scan_url` (the address for people and Claude Code) and `token_line` (the placeholder the zip names); cached 60 seconds per replica; 404 when server-scan carries no skill |
| `GET` | `/api/day1/server-scan/skill/download` | server-scan's zip of the skill (`<name>.zip`), `server_scan_url` written into its `SKILL.md`; never cached |
| `GET` | `/api/day1/server-scan/architecture/{slug}` | One of server-scan's architecture diagrams, `{slug, html}`: the page its UI serves at `<SERVER_SCAN_UI_URL>/architecture/<slug>.html`, read with no token, taken only if archify made it, cached 5 minutes per replica. 404 for one its UI does not serve (or an address that is not its UI), 422 for a slug no diagram can have |
| `GET` | `/api/day1/server-scan/confs` | server-scan's hardware catalog, in its shape: every conf (server configuration) it can read, unpaged, in its natural `conf_id` order, and `unreadable`, the ids of the stored ones it could not read; read now with the viewer token, not cached by day1 |
| `GET` | `/api/day1/server-scan/jobs` | server-scan's triggerable CronJobs (its collectors and prunes), each with its schedule, warning, `values.yaml` flag and recent Jobs, newest first, and their pods, in its shape; `enabled: false` when server-scan has the feature off. With server-scan's **admin** token (it keeps Jobs for its admins, reads too), none when it runs with auth off; `501` with a viewer token alone; not cached by day1 |
| `GET` | `/api/day1/server-scan/jobs/{cronjob}/runs/{job}/pods/{pod}/logs?tail=` | A pod's last `tail` lines (default 500; server-scan caps them), only along CronJob → its Job → its pod (else `404`, server-scan's words); the admin token, as above |

#### Inventory Management (everyone reads, admins add; ADR-0057)

Each MCE's available Agents by InfraEnv pool, as server-scan counts them, the add-server runs, and installing servers through the platform's `add-server-to-mce` workflow. `501 FEATURE_DISABLED` while `SERVER_SCAN_URL` is empty (the runs: `WORKFLOWS_API_URL`; installing: `DAY1_ADD_SERVERS`). Live status is not needed: without it, an MCE's pools are the InfraEnvs its cluster files name, and any InfraEnv may be typed (ADR-0057's amendment) ([API note](docs/notes/2026-11-13-inventory-management-api.md)).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day1/inventory` | Every day1 MCE: its servers, those in clusters and the available Agents (`INSTALLED_TO_INVENTORY`), by InfraEnv pool and hardware, and how many a pool draw could pick; `infra_envs_from` says whether the pools are the MCE's InfraEnvs (`mce`) or those its day1 cluster files name (`day1`, live status off or unreadable) |
| `GET` | `/api/day1/inventory/runs` | The newest add-server runs, herzi's and people's: MCE, InfraEnv, slot or server, phase, error; `origin` `named` (a person) or `pool` (herzi or a person) |
| `GET` | `/api/day1/inventory/mces/{mce}/infra-envs/{infra_env}/candidates` | A pool's `AVAILABLE` servers for a named install: name, hardware, health, server-scan's lock, and why one is not offered (locked, in maintenance, contested). Any InfraEnv that is a DNS label (422 otherwise); 404 only for an MCE day1 lacks |
| `POST` | `/api/day1/inventory/mces/{mce}/infra-envs/{infra_env}/add-servers` | `{count}` or `{server_names}` (1-20): start one `add-server-to-mce` run per server (`202`, per run), with no MCE read: the workflow checks the InfraEnv (a DNS label, 422 otherwise; 404 only for an MCE day1 lacks). Never retried: sent again, it installs more. `409 ADD_SERVER_ALREADY_RUNNING`, `504 AMBIGUOUS_WRITE` (look at the runs first) |

### Day2 Service (Port 8002)

`{cluster}` is a cluster id (`hub`, `mce:<site>:<env>:<mce>`,
`hosted:<site>:<env>:<mce>:<cluster>`, `upi:<site>:<env>:<cluster>`) or a bare
name that names one destination (`?mce=` when it names more than one).

#### Catalog and lints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day2/build` | The `version` and `commit` the service runs |
| `GET` | `/api/day2/gitlab-info` | Where the sigs group lives, for links |
| `GET` | `/api/day2/teams` | Every team: each project directly in the sigs group, and whether Wingman may write there |
| `GET` | `/api/day2/teams/{team}` | One team, and whether Wingman may write there |
| `GET` | `/api/day2/addons` | Every catalog entry (`operators/<chart>/`), or one team's (`?team=`) |
| `GET` | `/api/day2/addons/{team}/{addon}` | One catalog entry |
| `GET` | `/api/day2/addons/{team}/{addon}/versions` | The chart repo's branches, default branch first |
| `GET` | `/api/day2/addons/{team}/{addon}/values` | The chart's own `values.yaml` at `?version=` |
| `GET` | `/api/day2/lints` | Every check on the team repos (`?team=`): render_chain.py's rules plus Wingman's own |

#### Authoring add-ons and fleet defaults

An add-on is a chart in a team's catalog (`operators/<chart>/` in the team
repo) and the fleet defaults built from it. A team is written
to only if it gave Wingman's GitLab account Developer on its own project: as a
member, from a group above the project, or through a group the project is
shared with (otherwise `403 TEAM_READ_ONLY`, ADR-0043). A team whose access
GitLab does not answer is read-only until it does. Every write takes
`?dry_run=true` (the plan, nothing opened): its `impact` lists every
destination whose app goes, comes or changes, and what goes or changes is
confirmed by id (`confirm_changes`) with the preview's `digest`
(`expected_digest`); a repo that moved since the preview is `409`
`plan-changed` (ADR-0053). The web-visible shapes:
`docs/notes/2026-11-12-operators-page-api.md`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/day2/teams/{team}/addon-template` | What a new add-on starts from: the team's usual sync options and chart repos, and each fleet scope's reach |
| `POST` | `/api/day2/addons/{team}` | Add an add-on to the team's catalog, optionally as a fleet default (opens an MR) |
| `PUT` | `/api/day2/addons/{team}/{addon}` | Edit the add-on (the API's team default): deploy config (edited in place), sync options, Sig values (opens an MR) |
| `GET` | `/api/day2/fleet-defaults` | Every `defaults/<scope>/<chart>/` (`?team=`), with its reach and sync options |
| `POST` | `/api/day2/addons/{team}/{addon}/defaults/{scope}` | Make it a fleet default; clusters that have it in their own folder move into it (opens an MR) |
| `PUT` | `/api/day2/addons/{team}/{addon}/defaults/{scope}` | Edit a fleet default's values and sync options (opens an MR) |
| `GET` | `/api/day2/teams/{team}/addons` | The team's add-ons: its catalog, plus fleet defaults of charts not in it |
| `GET` | `/api/day2/teams/{team}/addons/{addon}` | One add-on: its files, OCP-version pins, and per scope every destination and how the default stands there |
| `GET` | `/api/day2/teams/{team}/operators` | Deprecated: 3.12.0's path of `/teams/{team}/addons` |
| `GET` | `/api/day2/teams/{team}/operators/{operator}` | Deprecated: 3.12.0's path of `/teams/{team}/addons/{addon}` |
| `PUT` | `/api/day2/addons/{team}/{addon}/defaults/{scope}/destinations/{cluster}/values` | One MCE's, hosted cluster's or UPI cluster's `values-<name>.yaml` of a fleet default (opens an MR) |
| `PUT` | `/api/day2/addons/{team}/{addon}/defaults/{scope}/envs/{env}/values` | One env's `values-<env>.yaml` (prod, prep or test) of a fleet default (opens an MR) |
| `POST` | `/api/day2/addons/{team}/{addon}/mce-installs` | Deploy it on specific MCEs: one install MR per MCE, in each one's own `in-cluster/<chart>/` (an MCE default of it is refused, the XOR rule) |

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
| `GET` | `/api/day2/clusters/{cluster}/upgrade-check` | Version-pinned charts that would fall back to the add-on's revision at `?to=` |

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
| `GET` | `/health/ready` | Every readiness check passes; 503 otherwise (the readiness probe). The GitLab check runs only until it first passes: after that, a GitLab outage leaves the pod ready and requests report it (ADR-0054) |
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
MCE_TOKENS_FILE=/etc/wingman/mce-tokens/tokens  # YAML: <mce>: <token>, or <mce>: {token: <token>, url: https://<host>:<port>} (ADR-0045)
MCE_SSL_VERIFY=true                       # true, false, or a CA bundle path
MCE_TIMEOUT_SECONDS=10
MCE_INFRAENV_NAMESPACE=                   # empty = all namespaces (the chart does not set it yet)
MCE_INFRAENV_CACHE_SECONDS=600            # how long a hub's InfraEnv list is kept; 0 = read every time
DAY1_STATUS_POLL_SECONDS=30               # the live status stream (the chart does not set it yet)

# The nodes' servers from server-scan, uninstall through the workflows orchestrator (ADR-0038; off by default);
# the same server-scan feeds Inventory Management (ADR-0057) and the Server Scan area for admins (ADR-0048)
SERVER_SCAN_URL=                          # e.g. http://server-scan-api.<ns>.svc:8000; empty: nodes without servers, no uninstall, no Server Scan area
SERVER_SCAN_UI_URL=                       # server-scan's UI: node links for anyone without the Server Scan area, the Claude page's zip, MCP command and token link, and where day1 reads the Architecture page's diagrams; default SERVER_SCAN_URL
SERVER_SCAN_TOKEN=                        # a server-scan viewer token (Bearer), from a Secret, for every read (the Server Scan area too); empty: no header
SERVER_SCAN_ADMIN_TOKEN=                  # server-scan's admin token, for the maintenance toggle only (Servers, a server's page); empty with a viewer token: the toggle is off
SERVER_SCAN_AUDITOR_TOKEN=                # server-scan's auditor token, for a server's History only; empty with a viewer token: History is off
SERVER_SCAN_SSL_VERIFY=true               # true, false, or a CA bundle path
SERVER_SCAN_TIMEOUT_SECONDS=10
WORKFLOWS_API_URL=                        # e.g. http://workflows-orchestrator-api.<ns>.svc:8080; needs SERVER_SCAN_URL
WORKFLOWS_SSL_VERIFY=true                 # true, false, or a CA bundle path
WORKFLOWS_TIMEOUT_SECONDS=10
DAY1_FAKE_FLEET=false                     # development only: an MCE, server-scan, the orchestrator and segments-manager in memory, from dev/fleet-fixtures
DAY1_PROVISIONER=merge-request            # how a create is proposed (ADR-0042): merge-request, or workflow (start provision-cluster; needs WORKFLOWS_API_URL)
DAY1_UPGRADES=false                       # upgrades through the upgrade-cluster workflow (ADR-0055); needs WORKFLOWS_API_URL; on, an edit may not change versions
WORKFLOWS_TARGETS_TIMEOUT_SECONDS=65      # the upgrade targets read: the orchestrator waits up to 60 s for it
PLACEMENT_MIN_FREE_PODS=70                # MCE placement (ADR-0050; checked when CLUSTER_STATUS_ENABLED): the free pods on its workers an MCE needs, the cost of one hosted control plane
DAY1_ADD_SERVERS=false                    # Inventory Management (ADR-0057): admins install servers into an MCE's InfraEnv pool through add-server-to-mce; needs WORKFLOWS_API_URL, not live status

# segments-manager: the cluster's EPG, checked against the file (ADR-0039), and the Segments area (ADR-0047); off by default; read only
SEGMENTS_MANAGER_URL=                     # its API, e.g. http://segments-manager.<ns>.svc:8000; empty: no EPG, no Segments area
SEGMENTS_MANAGER_UI_URL=                  # where the cluster page's links point (its UI); default SEGMENTS_MANAGER_URL; both empty: no link
SEGMENTS_MANAGER_SSL_VERIFY=true          # true, false, or a CA bundle path
SEGMENTS_MANAGER_TIMEOUT_SECONDS=5

# Quick Links: the launcher page (ADR-0052; admins only)
QUICK_LINKS_FILE=/etc/wingman/quick-links/links.yaml   # the team's links (the chart's ConfigMap); re-read on every page load; missing: none
QUICK_LINKS_HUB_NAME=                     # the hub Wingman runs on, as in apps.<name>.<domain>; empty: no hub card
QUICK_LINKS_HUB_DOMAIN=                   # the hub's domain; default QUICK_LINKS_DOMAIN
QUICK_LINKS_DOMAIN=                       # the MCEs' domain; default MCE_API_DOMAIN
QUICK_LINKS_ARGOCD_URL_TEMPLATE=https://openshift-gitops-server-openshift-gitops.apps.{cluster}.{domain}
QUICK_LINKS_CONSOLE_URL_TEMPLATE=https://console-openshift-console.apps.{cluster}.{domain}
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
├── operators/<chart>/{<chart>.yaml, values.yaml}         # the add-on: deploy config, Sig values (+ ocp-versions/<v>/ pins)
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
layers for a hosted cluster (Sig values, OCP-version pin, site, site+env,
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

- Day1: `GET /healthz` (`/health/live`), `GET /health/ready` (GitLab answered once since the pod started), `GET /metrics`
- Day2: `GET /healthz` (`/health/live`), `GET /health/ready` (GitLab answered once since the pod started), `GET /metrics`

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
   `ports.py`, day1's `ports/`), `infrastructure/` (adapters and fakes), `api/v1/` (routers); `uv run lint-imports` holds the
   layers. GitLab only through `GitLabPort` (ADR-0002). DEVELOPMENT.md walks through a new endpoint.
2. Shared code goes in `packages/wingman-core`
3. Frontend routes go in `app/(app)/` and stay thin; the feature they render goes in `components/<area>/`
   (ADR-0056 says where its state and pure helpers go). Files stay within 500 lines and functions small:
   CI checks both (ADR-0056)
4. Add API types to the section's file in `types/day1/` or `types/day2/`, or to `types/problem.ts`
   (`types/index.ts` re-exports them; import from `@/types`)

### Testing Locally

```bash
scripts/gate.sh python   # file sizes, ruff, ty, import-linter, pytest, pip-audit, deptry
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
