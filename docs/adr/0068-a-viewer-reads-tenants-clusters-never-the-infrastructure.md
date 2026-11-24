# ADR-0068: A viewer reads the tenants' clusters and never the infrastructure: no MCE, no infrastructure name, no infrastructure file

Date: 2026-11-24
Status: Accepted

## Context

ADR-0067 (3.57.0) made seeds and KV clusters kinds of their own and closed the
main routes to a viewer: the MCE lists, placement and Inventory Management
are an admin's, and a KV cluster is a missing one. It listed what it did not
filter: the audit's commits and diffs, the lints, day2's approvals and audit,
an add-on's per-MCE values, day2's hub and UPI destinations, and the MCE on a
tenant cluster's own page and in `?mce=` reads.

The user (2026-11-23/24): a viewer is a customer, and must never learn about
the infrastructure (the MCEs and their names, seeds and KV clusters, sites as
infrastructure, Inventory, servers and nodes, the hub). "KV cluster and MCE
seed and MCEs they are for admins only no viewer should know." Good RBAC is
what lets Wingman use the platform while customers do not see it. "It's more
than that": the list above was not complete.

An audit of every route a non-admin may call (day1, day2, the SSE stream,
the webhooks and health) and of every page a viewer reaches found the MCE in
more places than ADR-0067 listed. The audit, route by route, is in the pull
request that made this change, in its description. In short:

- day1 answered `mce`, `path` (`sites/<site>/mces/<mce>/...`), `gitlab_url`
  and `mce_default_mastertag` on every cluster read, in the drift rows, a
  flavor's clusters, drift and rollout, the approval rollout, the fleet's
  upgrades, an upgrade run and Scale's options; a viewer could send
  `?site=&mce=` and try MCE names against a cluster's (`locate` takes both as
  given), and `name-suggestion` answered a viewer for any MCE;
- free text named the MCE: Wingman's own delete description ("site `s`, MCE
  `m`"), provision-cluster's merge request title ("… on `<mce>`"), the naming
  problems, commit messages, the hub's errors in live status
  ("MCE 'x' hub API answered …"), the workflows' words;
- the audit listed every day1 commit (an MCE's values, the upgrade rules)
  with every file of its diff, and an approval's diff named every file by its
  path;
- the network card read segments-manager for a viewer: the EPG, the
  segment's record, the clusters a shared segment is allocated to;
- day2 answered the hub and the UPI clusters as destinations, a hosted
  cluster's `id` (`hosted:<site>:<env>:<mce>:<name>`), `mce` and `argo`, every
  value layer's and folder's path, and its approvals, audit, lints, fleet
  defaults and add-on pages unfiltered;
- the web put `?site=&mce=` in every cluster link, and kept one query cache
  for every user of a browser.

## Decision

### 1. The rules, the same in day1 and day2

Enforced in the services, before anything is read for the request where the
answer depends on it; the web only follows.

| What a viewer reads | The rule |
|---|---|
| A list | Leaves out every item about the infrastructure (a KV cluster, an MCE's or the hub's or a UPI cluster's destination, a merge request or a commit about no tenant cluster) |
| One item | An item a viewer may not know of looks missing: the missing thing's 404, in its words |
| A structured field that names the infrastructure | `null` for a viewer: every `mce`, every path through an MCE's folder, every link into the repo at one. The response models mark them `ADMIN_ONLY` (`wingman_core.web.viewer`); `for_viewer` answers the model with them `null`, at any depth |
| Free text | Not parsed, but every infrastructure name the service knows reads `[hidden]` (`wingman_core.domain.redaction.Redactor`, as whole tokens): each MCE folder's and seed's, each KV cluster's, and in day2 the hub's and each UPI cluster's. Titles, descriptions, commit messages, diffs, a workflow's words, a condition's message, a cluster file's text. A name the service does not know (a server's, an address) is not found |
| A file in a diff | A tenant cluster's file alone, named by its file name (`ocp4-prod-lark-site1.yaml`); one cluster's merge request shows that cluster's file alone. In day2, a tenant's own files from its folder on, and the team's files that are about no one destination (section 4) |
| A cluster named in a request | By its name alone: `site` and `mce` are an admin's to send, and a viewer's are ignored, so they test no MCE name; day2's destination id is an admin's too, and from a viewer an unknown name |

An admin reads everything as before: every rule passes their request through
unchanged.

### 2. A tenant cluster's page: its site, never its MCE

A customer needs to know which cluster is theirs, how it is, what it is made
of and what changes it. They do not need to know where it runs (the user's
framing), so:

- **The MCE is an admin's.** A viewer's cluster has `mce: null`, no file path,
  no GitLab link, no MCE default mastertag, no segments-manager link; its
  live status, history, drift, network, upgrade run and Scale are found by
  its name in the tree.
- **The site stays.** It is part of the cluster's own name
  (`ocp4-<env>-<name>-<site>`, ADR-0014), so hiding it hides nothing; it is
  the place the customer asked for, not a piece of the platform. The list's
  Site column and filter stay; the lists of sites (`GET /api/day1/sites`)
  stay an admin's (ADR-0067).
- **The cluster's own file stays**, its YAML, NodePools and InfraEnv names:
  it is the customer's cluster, the InfraEnv name is the NodePool's hardware
  as the flavor offers it, and the VLAN and segment are the cluster's own
  allocation. Its text goes through the redactor like any other.
- **Live status** reads the hub of the cluster's folder in the tree. A
  viewer's failed read says "the cluster's live status could not be read",
  never the hub's words, which name its address or its MCE; the HostedCluster's
  conditions are its own, redacted.
- **The network card** is the file's VLAN and segment: segments-manager is
  not asked for a viewer (its EPG, its record, the clusters a shared segment
  is allocated to and what disagrees are the platform's).

### 3. day1

| Route | A viewer (ADR-0068) |
|---|---|
| `GET /api/day1/clusters`, `/drift-summary`, `/{name}`, `/{name}/drift`, `/history`, `/current-yaml`, `/network`, `/provision-run`, `/delete-workflow`, `/scale`, `/scale-run`, `/excluded-agent-labels`, `/upgrade-run`, `GET /api/day1/upgrades`, `/specs/{name}/clusters`, `/drift`, `/rollout`, `/history` | Through `api/v1/visible.py`'s `shown`/`all_shown`: `mce`, `path`, `gitlab_url`, `metadata.mce`, `mce_default_mastertag`, `segments_manager` `null`, every text redacted |
| Every `/clusters/{name}…` read | `cluster_ref` locates a viewer's cluster by its name alone; a name two folders hold is ambiguous without naming them |
| `GET /{name}/status`, `/status/stream`, `POST /bulk-status` | `mce` is optional and an admin's: without it, and always for a viewer, the cluster's folder in the tree; a cluster the tree does not hold (not merged yet) is a viewer's 404, or left out of the bulk answer |
| `GET /{name}/network` | No segments-manager read (`NetworkService.network(ledger=False)`) |
| `GET /clusters/name-suggestion` | `AdminUser`: it takes an MCE (the create form is an admin's) |
| `GET /api/day1/approvals`, `/audit/merge-requests` | The specs project's merge requests and the day1 ones about a tenant's cluster; a day1 merge request about no cluster (a hand-made one, an MCE's) is an admin's |
| `GET /approvals/{iid}` | 404 for one a viewer may not know of; of a day1 one, the cluster's own file alone, by its file name |
| `GET /approvals/{iid}/rollout` | The same 404; no KV cluster listed, no MCE. The counts stay the flavor's |
| `GET /api/day1/audit/commits` | The specs project's commits and the day1 commits that changed a file in a Customer MCE's `hostedClusters/` (one history read per folder, `Day1Tree.tenant_folders`), each once |
| `GET /audit/commits/{repo}/{sha}/diff` | A day1 commit's tenant cluster files alone, by file name; a commit that changed none is one that does not exist (404) |

The redactor's names are `Day1Tree.infrastructure`: every MCE-level folder
(Customer MCEs and seeds) and every KV cluster, from the one tree read.
`tests/api/test_viewer_reads_api.py` reads every route a viewer may call, in
a world with every feature on and a merge request of each kind open, and
fails on any MCE's, seed's or KV cluster's name or `mces/<folder>` path; a new
viewer route must join its list, or its coverage test fails.

### 4. day2

A viewer's destinations are the tenants' hosted clusters alone
(`domain/visibility.py`, `sees_destination`): the hub, the UPI clusters,
every MCE hub (a seed's too) and every KV cluster are an admin's, and of the
fleet scopes the hosted clusters' alone (`sees_scope`). Each route finds and
answers through `api/v1/visible.py`'s `View`, from one topology read:

| Route | A viewer (ADR-0068) |
|---|---|
| `GET /api/day2/clusters` | The tenants' clusters: `id` is the bare name, `mce` and `argo` `null` (`ADMIN_ONLY`), the warnings theirs |
| `GET /clusters/{cluster}`, `/addons`, `/addons/{team}/{addon}`, `/history`, `/upgrade-check`, `POST /merge-preview` | `View.destination`: the bare name among the tenants' clusters; an id, `hub`, a hidden destination's name are the unknown name's 404, `?mce=` and the body's `mce` are ignored, a name two tenants share is ambiguous without their ids. The service is then asked by the destination's id, an admin's too, so nothing resolves the name again against what the viewer may not know. `gitlab_url` and `deploy.argo` `null`; a path in the tenant's folder reads from the cluster on (`<cluster>/<chart>/values.yaml`); every value layer stays with its role, its MCE layer `sites/<s>/<e>/mces/[hidden]/values.yaml`; `merge-preview` takes a layer by the path the viewer read |
| `GET /approvals`, `/audit/merge-requests` | Those whose title or description names a tenant (name or id) or the hosted clusters' scope, and nothing hidden: no other destination's id or name, no other scope ("every MCE", "the hub", "every UPI cluster", `defaults/<scope>`), no MCE folder but those of the tenants named (a tenant's id, folder and Argo CD carry its MCE). Whole tokens, as the redactor matches (`Sight.about`) |
| `GET /approvals/{team}/{iid}`, `/audit/commits/{sha}/diff` | Of the diff, a tenant's own files (from the cluster on) and the team's `operators/…` and `defaults/hosted-clusters/<chart>/…` (a `values-<name>.yaml` there of a tenant or an env), `Sight.file`; a merge request not a viewer's, or one or a commit with no such file, is the missing one's 404 |
| `GET /audit/commits` | Those whose message is about a tenant, by the same rule |
| `GET /lints`, and every `warnings` list | The findings about a tenant (by id) or no destination, at no path or one `Sight.file` reads |
| `GET /addons`, `/addons/{team}/{addon}` | `fleet_defaults` names the hosted clusters' scope alone |
| `GET /fleet-defaults` | The hosted clusters' defaults, their `reach` and `excluded` the tenants' names, their `tweaks` a tenant's or an env's |
| `GET /teams/{team}/addons`, `/{addon}` (and the deprecated `operators` paths) | Counted and listed from the tenants' destinations alone (`Topology.visible_to` keeps each team's plan to them): the hosted clusters' scope, no unregistered destination, `exclusions.yaml`'s tenants' names; a chart that is only another scope's default is the unknown chart's 404 |
| `GET /teams/{team}/addon-template` | `AdminUser`: each scope's destinations by id, for an admin's new add-on form |
| Every day2 error a viewer's read raises | Its words and details through the same view; a refused `override_path` lists no layer |

The redactor's names are `Topology.infrastructure`: every MCE-level folder,
the hub's name and its two Argo CDs' (`prod-hub`, `prod-hub-upi`), each UPI
cluster's and each KV cluster's. Day1's drift reads a tenant's add-ons as a
viewer (`system:wingman-day1`) by its name; its `?mce=` is ignored.
`tests/api/test_viewer_reads_api.py` reads every route a viewer may call,
with an install open on a tenant, an MCE hub, the hub, a UPI and a KV
cluster, a default of the hosted clusters and of the MCEs open, and a
tenant's and an MCE's install merged; it fails on any hidden name, `mce:` or
`upi:` id or `mces/<folder>` path, and its coverage test on a viewer route
not in its list.

### 5. The web follows

The web hides nothing the services send: it draws what a viewer's answer
holds, and sends nothing a viewer's answer does not give it.

- **Links and reads carry no MCE for a viewer.** `clusterHref` and
  `clusterQuery` (`lib/clusters.ts`) pin a cluster by `?site=&mce=` only when
  it has an MCE, so a viewer's links are `/clusters/<name>`; the cluster page
  sends a link's `?site=&mce=` for an admin only, so a viewer's old bookmark
  sends neither; live status, its stream and the bulk status go by name
  (`useClusterLiveStatus(name, mce, found)`, `BulkStatusItem`); day2's reads
  get no `?mce=` when the cluster has none.
- **What is `null` is not drawn**: the cluster card's MCE, MCE default and
  File rows, the header's GitLab button, the list's MCE line, the upgrade
  panel's MCE; where a list says where a cluster is, `placeOf` is the site
  alone. The network card's EPG, its problems and its read are an admin's
  (`useClusterNetwork(..., enabled)`): a viewer's card is the file's VLAN
  and segment. The Dashboard's words name no MCE ("Live status could not be
  read", "offered a newer OpenShift release").
- **The Documentation** leaves out, for a viewer, the sections about the
  infrastructure (Workspaces, Cluster Workflows, Inventory Management, Quick
  Links, Special Features, File Locations), and its Core Concepts explains a
  cluster by its name and site, without the MCE and the destinations.
- **The query cache is one user's** (`lib/query-cache.ts`): it lives in
  localStorage for ten minutes, and an admin's reads hold the MCEs, the KV
  clusters and Inventory. Signing out, a sign-in as someone else or in
  another role, and an expired session (the 401) empty it, in memory and in
  storage; the store's own hydration is the same user coming back.

## Alternatives rejected

- **Hide them in the web only**: a viewer's token reads the API (ADR-0067).
- **Answer `[hidden]` in the structured fields** (`mce: "[hidden]"`): the
  web would send it back as `?mce=[hidden]`, and the field would still say
  that there is an MCE where a `null` says the viewer is not told.
- **Hide the site too**: it is in the cluster's name.
- **Hide the cluster's own file, or its InfraEnv names**: the customer's
  cluster is what the file says; the InfraEnv name is the hardware the flavor
  offered them. The file names no MCE.
- **Parse free text for infrastructure** (an IP, a server name): Wingman
  does not parse the workflows' words (ADR-0038's amendment). Replacing the
  names it knows is a rule; guessing at sentences is not.
- **A viewer's commit list from each commit's diff**: a page of 50 commits
  would be 50 diff reads; one history read per Customer MCE folder gives the
  same commits.
- **403 for a viewer's `?mce=`**: day1's drift asks day2 with one, and a 403
  for a wrong guess and a 200 for a right one is the oracle; ignoring it says
  nothing.

## Consequences

- A viewer's cluster page names no MCE; links to it carry no `?mce=`.
- A viewer's audit is shorter: the commits and merge requests about the
  infrastructure are an admin's. A paged read is filtered after it is read,
  so a viewer's page may be shorter than `per_page`.
- A viewer may read that a value or a sentence came from something hidden
  (`[hidden]`); never its name.
- An approval rollout's counts (`following`, `opens`) still count a KV
  cluster that follows the flavor; no list names one.
- A merge request or commit text that names an MCE Wingman's tree does not
  hold (a deleted one) is not redacted.
- day2: a viewer's merge requests and commits are those whose words name a
  tenant or the hosted clusters' scope; a Sig values edit names neither, so
  it is an admin's, as is a GitLab merge commit whose message names no
  tenant. Of a tenant's text a viewer reads its MCE as `[hidden]`, its id
  `hosted:<site>:<env>:[hidden]:<name>`.
- day2: a viewer's `id` is a bare name, so the web addresses their clusters
  by name; a viewer cannot reach a tenant's cluster whose name a second
  tenant's shares (an admin's id is the way).
- day2: a viewer may preview a diff of the team's Sig values or a hosted
  clusters' default whose merge request or commit is an admin's; those files
  name no destination.
- The Documentation's general sections (the platform overview, clusters,
  add-ons, roles, troubleshooting) still say what an MCE or the hub is, as
  the public repo's docs do; they name no deployment's MCE. The sections
  about the infrastructure are an admin's.

## Verification

- `packages/wingman-core/tests/unit/domain/test_redaction.py` (whole
  tokens, the longest name first, case) and `tests/unit/web/test_viewer.py`
  (admin-only fields `null` at any depth, every text redacted, the original
  untouched).
- `apps/day1-service/tests/unit/domain/test_visibility.py` (a tenant's file,
  a viewer's diffs by file name, one cluster's alone).
- `apps/day1-service/tests/api/test_viewer_reads_api.py`: the crawl and its
  coverage, a tenant's page (site, no MCE, path or link), `?site=&mce=`
  ignored, the network without segments-manager, the name suggestion's 403,
  the bulk status by name, a merge request's file and words, a day1 merge
  request about no cluster, the commits and a commit's diff, the status by
  name; `test_status_api.py` (a viewer's stream by name, the hub's words
  hidden) and `test_upgrades_api.py` (a viewer's run without its MCE).
- `apps/day2-service/tests/unit/domain/test_visibility.py` (the tenants and
  the hosted clusters' scope, the redactor's names, a tenant's id and paths,
  the files of a diff, a finding, a merge request's or commit's words).
- `apps/day2-service/tests/api/test_viewer_reads_api.py`: the crawl and its
  coverage, the hub, a UPI, an MCE, a seed and a KV cluster answered as
  unknown names, a tenant's `id`, `mce`, `argo` and links, `?mce=` ignored
  (day1's drift session too), a name a UPI shares resolved once to the
  tenant, a name two tenants share ambiguous without ids, the value stack's
  paths and a preview by them, a refused preview with no path, the merge
  requests, commits and diffs, the lints, fleet defaults and add-on pages,
  and the add-on template's 403; `test_visibility_api.py` (ADR-0067's).
- `apps/web/lib/clusters.test.ts` (a viewer's link and reads by name,
  `placeOf`) and `lib/query-cache.test.ts` (the cache is one user's); the
  Playwright spec `viewer-no-infrastructure.spec.ts`: the clusters list and a
  cluster's page as a viewer (no MCE, path, EPG, Segments Manager or GitLab
  link; no request that names an MCE, from an old link either; status by
  name), a cluster's add-ons as a viewer (no MCE, Argo CD, id or folder
  link; no `?mce=` sent, from an old link either), the Documentation for a
  viewer and an admin, and signing out emptying the stored reads.
