# One place for the platform: the plan

**Status:** decided 2026-11-12 (the architect's vision, confirmed by the
user). This file is the plan and the record of the choices. Each workstream
gets its ADR when it is built. Its decisions change two rules in
[architecture-fit.md](architecture-fit.md); the section "What this changes"
says which.

## The vision

Wingman becomes the platform team's one place to work from:

- **Clusters, as today**: create, edit, delete and import hosted clusters
  (day1), and add-ons on every kind of cluster (day2), by merge request.
- **Servers and Segments inside Wingman.** server-scan's UI and
  segments-manager's UI are rebuilt in Wingman. **Their APIs do not change
  at all.** An administrator switches between Wingman, Servers and Segments
  from the top bar.
- **What cluster-navigator collects, on Wingman's pages**, for hosted
  clusters and MCEs only, **never UPI clusters**.
- **Wingman picks the MCE** for a new hosted cluster from the site, prod or
  prep, and the OpenShift version.
- **Teams author their own add-ons**: new applications, their ArgoCD sync
  options, and defaults across a whole fleet.
- **One merge request per cluster**, for every change, import included.

## The decisions (user, 2026-11-12)

| # | Decision | Details |
|---|---|---|
| 1 | A team creates a new add-on, or changes one, from Wingman, sync options included | The add-on's `operators/<chart>/<chart>.yaml` and `values.yaml` in `sigs/<team>`; ArgoCD's `syncPolicy`: auto-sync, prune, self-heal and the `syncOptions` list |
| 2 | A team makes a new or existing add-on a default across a fleet | Every hosted cluster, every MCE, the hub, or every UPI cluster (`defaults/<scope>/<chart>/`) |
| 3 | A team that has not given Wingman write access has Wingman's writes off | The team opts in by giving Wingman's GitLab account Developer on `sigs/<team>`. Wingman checks per team and says why a team is read-only |
| 4 | Every change is one MR per cluster; import too | Import opened one MR for all its clusters (ADR-0037); now one each. Decision 21 says why |
| 5 | Wingman picks the MCE for a new hosted cluster | From the site, the environment (prod/prep) and the OpenShift version; rules below |
| 6 | "Customer" in placement is the cluster's owner, its mador | The owner numbers of ADR-0028 |
| 7 | An MCE's spare servers come from server-scan | The MCE keeps spare servers for auto-repair; more spare is better, not a requirement to fit the new cluster |
| 8 | Fewer clusters on an MCE is better, with no hard cap | |
| 9 | Placement order: the checks, then fewest of this owner, then fewest overall, then most spare; a person may choose another MCE that passes the checks | Document everything |
| 10 | server-scan's and segments-manager's UIs move into Wingman; their APIs stay as they are | An administrator switches area from the top bar |
| 11 | cluster-navigator's data for hosted clusters and MCEs, never UPI | |
| 12 | Wingman runs on the team's sandbox, in namespace `wingman`, with its own GitLab, the orchestrator on | Whether that GitLab becomes the sandbox's Git store for the platform too is the team's call (workstream 1) |
| 13 | Servers, Segments and server-scan's event history are for Wingman's admins, for now | Until the RBAC of decision 17 exists |
| 14 | The Servers area does exactly what server-scan's UI does, every button included | Maintenance on/off with its reason and "run a job now" too: admin only, the same confirmations, recorded in Wingman's audit with the person's name |
| 15 | A person may choose another MCE than Wingman's pick, if it passes the checks | Admins only, with a reason, written into the MR next to the numbers |
| 16 | Free pods are counted on every Ready, schedulable node of the MCE | Control-plane (master) nodes excluded |
| 17 | Fine-grained RBAC: groups with their own permissions, such as seeing every server or only your own | Identities and groups from **Keycloak, federating LDAP** (OIDC). There is no Keycloak in the air-gap: Wingman brings one (Red Hat build of Keycloak) |
| 18 | Wingman may reuse whatever it needs from server-scan, segments-manager and cluster-navigator | Their repositories are public, as Wingman's is |
| 19 | MCE placement is built first, after the day2 and import PRs | With the per-MCE API address it needs |
| 21 | **Small blast radius: a change reaches each cluster through its own MR, and the customer takes it when ready.** One concept, not two features | A new flavor version opens one MR per linked cluster, **automatically**, and each customer merges theirs when comfortable. A cluster is measured against its own flavor version, so a newer version is "update available", never "out of sync". Import uses the same engine |
| 20 | A **Quick Links** page in the sidebar: a launcher in the style of the team's homepage dashboard | Every ArgoCD (the hub's, each MCE's at `openshift-gitops-server-openshift-gitops.apps.<cluster>.<domain>`), each cluster's console, and the team's other links, with their status (the status: dropped 2026-11-13, ADR-0052's amendment) |

## What this changes in Wingman's rules

[architecture-fit.md](architecture-fit.md) listed rules from the architect's
division of the work. Two of them change, and its first question is answered:

- **Question 1, "who picks the hub": Wingman does** (decision 5). Wingman
  still reserves nothing: two people creating at once can both be offered the
  same MCE, which is acceptable because "fewer is better" is a preference and
  not a cap. If the create workflow's admission step is built, it has the
  last word, and Wingman shows its answer.
- **Rule 2, "Wingman never checks or reserves capacity"**, now reads: Wingman
  ranks MCEs by what they hold and what they have free, and checks the free
  pods a control plane needs. It never reserves capacity and never names a
  server for a cluster (rule 5 stands).
- **"segments-manager: never called by Wingman"** was already out of date
  (ADR-0039 reads one segment). Now Wingman shows segments-manager's read UI.
  Allocation and release stay inside the workflows (rule 6 stands).
- **server-scan: "read-only"** stays true for the first version of the
  Servers area. server-scan's own UI has two writes, maintenance on/off and
  "run a collector job now"; whether Wingman offers them is an open question
  (below).
- Convention 14 (site and MCE are read-only in Wingman) is unchanged.

## Workstreams

Each workstream is a branch and a PR, built in its own worktree, with its ADR
number fixed in advance so parallel work never collides. Every merge to main
is a release (ADR-0031), so PRs merge one at a time, each after the previous
tag exists.

| # | Workstream | ADR | Size | Waits on |
|---|---|---|---|---|
| 0a | Day2: create add-ons, sync options, fleet defaults, per-team opt-in | 0043 | L | In progress |
| 0b | Changes reach each cluster through its own MR: import, and every flavor version rolled out per cluster | 0044 | L | In progress (PR #32) |
| 1 | Wingman on the sandbox; a per-MCE API address | 0045 | S, plus ops | In progress |
| 2 | The single pane: areas, the top-bar switch, the design pass, shared table and states | 0046 | M | 1 for a place to show it |
| 3 | Segments area | 0047 | M + M | Built as an alpha (3.15.0): the user decides what stays |
| 4 | Servers area | 0048 | L–XL | 2; the team's tokens and an OK on code reuse |
| 5 | Hosted clusters and MCEs from cluster-navigator | 0049 | M–L | The team: collectors and a token |
| 6 | MCE placement | 0050 | M + M | 1 (per-MCE address), MCE read rights |
| 7 | Docs, upgrade guides, ecosystem notes | — | S each | Every workstream |
| 8 | RBAC with Keycloak: permissions per group, scoped visibility | 0051 | L | Its design before code; 2 for the areas it guards |
| 9 | Quick Links page | 0052 | M | Nothing; built alongside 6 |

### 0a. Day2: teams author add-ons (ADR-0043, in progress)

- **New add-on** on `sigs/<team>`: `operators/<chart>/<chart>.yaml`
  (`repourl` in lowercase only, `targetRevision`, `path`, `projectNamespace`,
  `syncPolicy`, `ignoreDifferences`) and `values.yaml`, by one MR. The sync
  options form starts from what the team's files use today (manual sync,
  `CreateNamespace=true`).
- **Edit** an add-on's team default, its sync options included.
- **Make it a default** across hosted clusters, MCEs, the hub or UPI
  clusters (`defaults/<scope>/<chart>/`). The platform's rules apply: a chart
  that is a fleet default and also sits in a cluster's folder generates the
  application twice, and deleting an application orphans its workload
  (ADR-0022). Clusters that already have the add-on in their own folder are
  listed; the ADR says whether Wingman moves them or refuses.
- **Per-team opt-in**: Wingman reads its own access level on each team's
  project (a new `GitLabPort` read, with its adapter, fake and contract test).
  Below Developer, every day2 write for that team is refused with the reason,
  and the web shows the team read-only. Group membership on the whole `sigs`
  group would give every team access at once, so opt-in needs membership per
  project. The chart README and the runbook change with it.
- Left for later, unless the PR includes it: "stop being a default", which
  orphans workloads and must say so.

### 0b. A change reaches each cluster through its own MR (ADR-0044, PR #32)

Decision 21. The goal is a small blast radius: no change rolls 1,000 clusters
at once, and no cluster shows "out of sync" because of a change it has not
been offered yet. Each customer takes a change when they are ready.

- **Measured against its own version.** A linked cluster is compared with
  the flavor as it was at the version in its header, read from the flavors
  repo's history. A newer version is "update available", with its MR, never
  drift.
- **A new flavor version opens one MR per linked cluster, automatically**,
  once it lands on the flavors repo's main:
  - each MR is that cluster's sync to the new version;
  - the day2 MRs for add-ons the new version adds are linked from it;
  - nothing changes on a cluster until its MR merges.

  Before the flavor MR merges, its review says how many cluster MRs will
  open, and which clusters will roll nodes. The opening runs in the
  background and is safe to restart, with one branch per flavor, version and
  cluster. Clusters that need a person (a hardware choice, for instance) are
  listed with the reason instead of guessed.
- **Import** uses the same engine. Every picked cluster is checked first;
  then one MR per cluster, each changing only that cluster's file. A failure
  is that cluster's own, never retried (ADR-0006).

### 1. Wingman on the sandbox (ADR-0045)

Done so far: namespace `wingman`; GitLab CE 19.5.3 (the version the contract
runs against), with storage on volumes and an edge-TLS route, pinned to the
worker with the most free disk.

Still to do:

- **Seed GitLab** with the sandbox platform's repos, in production's layout:
  the day1 values repo as `gitops-day1/platform-config`, one project per sig
  under `redbull/gitops-day2-prod/sigs/`, and Wingman's flavors project from
  the fixtures.
- **Install Wingman 3.7.0** from its chart:
  - OpenShift OAuth, with the cluster's admin group as Wingman's admins;
  - server-scan and segments-manager reads on;
  - the orchestrator on (node uninstall);
  - `day1.provisioner: merge-request` until the store is shared.
- **Chart fixes found on the way** go in their own PR: an nginx that runs
  under OpenShift's restricted SCC, pinned (chart hardening, "Not done yet"
  item 2).
- **A per-MCE API address.** Wingman builds `https://api.<mce>.<domain>:6443`,
  and the sandbox's hub does not follow that pattern. Add an optional address
  per MCE in the tokens Secret. Live status, the nodes view and placement's
  free pods all need it.
- **The shared Git store (the team decides).** In the sandbox the platform
  keeps its files on GitHub, while Wingman works only with GitLab. Until they
  share one store:
  - a cluster created by the provision workflow is not seen by Wingman;
  - Wingman's MRs are not seen by the platform.

  The cluster-lifecycle worker already supports GitLab (`day1GitProvider:
  gitlab`, `day2SigRepoUrlTemplate` with `{sig}`). Switching it, and the
  platform's ArgoCD, to Wingman's GitLab makes the sandbox match production.
  Once switched, set `day1.provisioner: workflow`.
- **Disk**: the sandbox workers sit close to the kubelet's eviction line.
  Large images must go to the roomiest worker, with an ephemeral-storage
  request, while someone watches free disk.

### 2. The single pane (ADR-0046)

The groundwork every area needs, built once:

- **Areas and the top-bar switch.**
  - Three areas: Wingman (today's pages), Servers and Segments, at `/`,
    `/servers/…` and `/segments/…`.
  - The switch sits in the top bar and is a link to each area, so each area
    has its own address and a deep link works.
  - Each area has its own sidebar; today's sidebar becomes Wingman's.
  - Who sees which area is open question 1.
- **The design pass**, with the design skills (Apple's interface guidelines
  for the web, Emil Kowalski's design engineering):
  - one set of colour tokens for light and dark (server-scan, segments-manager
    and cluster-navigator are each dark-only, with their own palette);
  - one type scale, and one density for data-heavy tables;
  - loading, empty and error states that look the same everywhere;
  - restrained motion that respects reduced-motion;
  - full keyboard use.

  Each area keeps what people know from the old UI: its columns, filters and
  words.
- **A table component.** Wingman has none: the clusters page sorts, filters
  and pages by hand. The Servers area needs a large table and Segments an
  Excel-style one (per-column filters, a column picker, copy on click,
  export). It is built once, on TanStack Table, pinned exactly (ADR-0003).
- **Filters live in the URL** (Next's `useSearchParams` and `router.replace`
  inside a Suspense boundary), so a filtered view can be shared and linked
  from other pages.
- **Unit tests for pure logic.** server-scan's filtering and sorting
  functions come with unit tests, and Wingman's web has no unit test runner.
  Decide between adding Vitest (pinned, ADR-0003) and porting those tests to
  Playwright.
- **Backend calls only.** The browser never calls server-scan,
  segments-manager or cluster-navigator directly:
  - their logins don't extend to Wingman's domain, and their tokens can't go
    to a browser;
  - every system gets a port, an adapter and a fake (ADR-0001);
  - errors are RFC 9457 problems (ADR-0004), and metrics follow the contract
    (ADR-0010).

### 3. Segments area (ADR-0047)

**Status (2026-11-13): built as an alpha** (3.15.0), for the user to look
at and decide what stays: the API below, the page at `/segments` from the
top bar's area switch, the shared table and Vitest from workstream 2's
groundwork (only what this page needs). Its cuts (no Excel, no connection
dot, no `/api/logs`, a Type filter row instead of column filters) are
listed in `docs/notes/2026-11-13-segments-area-api.md` §7.

segments-manager's UI is one read-only page today (it lost its writes in
July); its reads need no token.

- **Backend** (day1): extend the `SegmentLedger` port with sites, statistics
  and the segment list, plus the forced refresh its Refresh button uses. Then:
  - the adapter, and a fake from `dev/fleet-fixtures/segments.yaml`;
  - a short cache;
  - new metric operations;
  - routes under `/api/day1/segments`.

  segments-manager's GET responses carry no schema, so Wingman types them
  itself (`SegmentRecord` already exists).
- **Web**:
  - site cards (allocated out of total, by type);
  - the segments table: type, site, VLAN, EPG, CIDR, DHCP, cluster, status;
    status tabs, site filter, search, column filters, column picker, copy
    on click, and a CSV export of what is shown;
  - a refresh every 30 seconds.
- **Better than the original**: filters in the URL, so the cluster page's
  link opens Wingman's own view of that segment. Each row also marks where
  segments-manager disagrees with the cluster file (ADR-0039's checks).
- **No writes.** Allocation and release stay with the workflows.

### 4. Servers area (ADR-0048)

server-scan's UI is about 9,700 lines over eight pages.

**Backend.** Extend the server-scan port and adapter for every read the pages
use:
- sites, the fleet rows, one server, its VM host, its events, confs,
  classification rules, health policies, jobs and job logs.

How it calls server-scan:
- **The fleet rows** are about 2.2 MB, or 250 KB gzipped, and polled every 30
  seconds. day1 already caches them with the ETag: serve every open page from
  that cache and pass the `304` through.
- **Tokens**: server-scan accepts three shared tokens, viewer, auditor and
  admin. Wingman keeps them in a Secret:
  - viewer for reads;
  - auditor for the event history;
  - admin only behind Wingman's admin check, if writes are offered.
- **Audit**: server-scan records a token's write as the token, not as the
  person. Wingman's own audit names the person, as it does for node
  uninstall.

**Pages, in this order:**

| Page | Size | Notes |
|---|---|---|
| Sites | S | Cards per site; every count links into Servers with that filter |
| Servers | L | The fleet, filtered, faceted, searched and paged in the browser; filters in the URL; a sidebar of MCEs, hosted clusters and UPI clusters; export |
| Server detail | M–L | Overview, Hardware, Network, Connectivity, History (History needs the auditor token) |
| Confs | S | The hardware catalog, read-only |
| Rules & Policies | S | Classification rules and health policies, read-only |
| Events | M | The audit trail with filters and cursor pages; auditor token |
| Jobs | M | Collector jobs, runs and logs; admin; "run now" starts a real collector |
| Architecture | S | Iframe server-scan's diagrams; copying them would go stale |
| Claude | S | Link out: its token and MCP flow belong to server-scan's own login |

**Parity (decision 14).** Every page and every button behaves as in
server-scan's UI, writes included: maintenance on/off (with its reason and
expected end) and "run a job now", behind Wingman's admin check and the same
confirmations, recorded in Wingman's audit with the person's name (server-scan
records only the token). The one place exact parity is impossible is the
Claude page's personal token: server-scan mints it only for someone logged
in to server-scan itself, never for a token caller. The page keeps the skill
download and the MCP command, and links to server-scan for the token.

**Reuse (decision 18).** server-scan's repository is public, as Wingman's is.
Its pure TypeScript (row filtering and facets, sorting, event descriptions,
date formatting, its types) is reused as it is, with its unit tests.

**Watch for names.** server-scan's MCE and site names must equal day1's MCE
folders and site names, or the joins fail. They differ on the sandbox; check
production (ecosystem question 7).

### 5. Hosted clusters and MCEs from cluster-navigator (ADR-0049)

What cluster-navigator has, and what it does not:

- **Collectors push.** A collector inside each cluster reports every 30
  minutes. An MCE reports its hosted clusters (name, version, nodepools,
  replicas). A hosted cluster appears with its own data **only if a
  collector runs inside it**.
- **Today only the platform cluster runs one**: no MCE and no hosted cluster
  reports.
- **It has no free-pod data.** Its pod figure is allocatable pods summed over
  all nodes, and it lists no pods.
- **Its API serves display sections**, not the typed report.

Steps:

1. **The team** rolls the collector out to every MCE and every hosted
   cluster. Once 0a exists, that rollout can itself be a day2 add-on made a
   default on MCEs and on hosted clusters. The team also gives Wingman a
   service token whose role sees hosted clusters and MCEs, and never UPI.
   Optional but better: a typed, admin-only endpoint for one cluster's report.
2. **Wingman**: a port, an adapter and a fake. The data is read and cached for
   minutes; it is at most 30 minutes old anyway.
   - **Joins.** A hosted cluster is joined by its file name (the HostedCluster
     name), and an MCE by its day1 folder name. Both must be checked against
     production.
   - **Filter.** Cluster types `generic`, and KubeVirt clusters that are not
     hosted, are UPI or standalone, and are dropped.
3. **Pages** (redesigned in the design pass):
   - the cluster page gains capacity, nodes, versions, console and router
     addresses, storage classes and DNS, with cluster-navigator's status
     (available, down, not reporting);
   - a new MCE page shows its hosted clusters, its capacity, and, from
     workstream 6, its placement numbers.

### 6. MCE placement (ADR-0050)

**The inputs** are the site, the environment (prod/prep), the OpenShift
version, the flavor and the owner.

**The candidates** are the MCEs at that site whose name says that
environment.

**The required checks** (an MCE that fails one is not offered, and says why):

| Check | From | Rule |
|---|---|---|
| Supports the version | `upgrade/mces/<mce>.yaml` in the day1 repo (ADR-0034) | Required |
| Free pods for a control plane | The MCE itself: allocatable pods minus running pods, on every Ready, schedulable node, control-plane nodes excluded (decision 16) | At least `PLACEMENT_MIN_FREE_PODS` (default 70) |
| Readable | Every read above answered | An MCE Wingman cannot read is "unknown" and never picked |

**The ranking** among those that pass:

1. fewest clusters of **this owner** (the mador) on the MCE, to spread each
   customer and keep the blast radius small;
2. fewest clusters overall;
3. most spare servers.

| Count | From |
|---|---|
| Clusters per MCE | The day1 repo's files, plus open create MRs (the name suggestion already counts them, ADR-0040) |
| This owner's clusters per MCE | The `owner` in each cluster file |
| Spare servers | server-scan's fleet rows: `openshift_state == INSTALLED_TO_INVENTORY` with that `mce_name` (registered to the MCE, in no cluster) |

A "usable" spare server is also not in maintenance, reachable, not stale,
its health not critical or unknown, and not contested. An MCE server-scan has
never seen is "unknown", not zero.

**Free pods** need two things:
- the per-MCE address (workstream 1);
- a token that may list nodes and pods across the cluster on each MCE. Its
  reads are namespaced today, so the upgrade guide says what to grant.

It is read fresh at create time: two creates within the 30 minutes
cluster-navigator would need must not see the same number.

**The create form**:
- Wingman picks the MCE and shows every candidate's numbers and why it won;
- an admin may choose another MCE that passes the checks, giving a reason
  (decision 15);
- the MR description records the numbers and the choice;
- with `day1.provisioner: workflow`, the chosen MCE goes to the
  provision-cluster workflow;
- the InfraEnv list follows the chosen MCE, as today.

**Settings**: the minimum free pods.

**Names.** server-scan's `mce_name` must equal the day1 MCE folder for the
spare count; production is being checked. Until then an MCE server-scan does
not know shows "spare: unknown" and placement still works on the rest.

### 8. RBAC with Keycloak (ADR-0051)

Today Wingman has two roles, admin and viewer, from OpenShift groups (ADR-0009,
`WINGMAN_ADMIN_GROUPS` / `WINGMAN_VIEWER_GROUPS`). Decision 17 replaces that
with permissions per group:

- **Identity**: Wingman logs in through Keycloak (OIDC, authorization code
  with PKCE), which federates the LDAP/AD users and groups. There is none in
  the air-gap, so Wingman's chart can install the Red Hat build of Keycloak
  (its operator, a realm, the LDAP federation, Wingman's client) or point at
  an existing one. OpenShift OAuth stays as an option, for installs that have
  no Keycloak.
- **Permissions, not roles**: each action and each view has a permission
  (`clusters.create`, `servers.maintenance`, `segments.read`, `events.read`,
  …), and a group gets a set of them. Admin and viewer become two such sets,
  so today's installs keep working.
- **Scope**: a permission applies to everything or only to what is the
  person's own: their owner (mador) for clusters, and the servers under
  those clusters ([owners-and-tenants.md](owners-and-tenants.md)). "See all
  servers" and "see only my own" are the same permission with two scopes.
- **Enforced on the server**, in day1 and day2, on every route, and on the
  lists themselves (a scoped person gets only their rows). The web hides
  what a person may not do, but never decides it.
- **The JWT** carries the person's permissions and scopes (or the services
  look them up and cache them), and every audit entry names the person.

Its design (the permission list, the scopes, how groups map, the Keycloak
install) is written and agreed before any code, because every area depends
on it.

### 9. Quick Links (ADR-0052)

Decision 20, modelled on the team's homepage dashboard (gethomepage): cards
in sections, each with an icon, a description, a status dot and, where it
has one, a live widget. (2026-11-13: the dots and the widgets are dropped,
ADR-0052's amendment: Wingman lists the links and never calls them.)

- **Generated from what Wingman knows:**
  - the hub Wingman runs on: its ArgoCD and console;
  - every MCE in the day1 repo, grouped by site: its ArgoCD at
    `https://openshift-gitops-server-openshift-gitops.apps.<mce>.<domain>` and
    its console.

  The URL patterns are settings, and an MCE whose address differs gets its
  own, like the per-MCE API address of workstream 1.
- **The team's own links**: further sections (GitLab, DevOps, internal
  tools, DC systems, …) from a config file the chart renders, so operators
  edit links without a release. Each link has a name, a URL, a description
  and an icon.
- **Icons ship with Wingman** (no CDN in the air gap). Brand icons come from
  a permissive set, and the rest from the icon library Wingman already uses.
- *Dropped 2026-11-13 (ADR-0052's amendment).* **Status**: Wingman's backend checks each URL on a timer with a short
  timeout and caches the answer: up, down or unknown. The browser never pings
  them, because of CORS and the many origins.
- *Dropped 2026-11-13 (ADR-0052's amendment).* **Widgets**: where an ArgoCD instance has a read-only token configured
  (a Secret map of instance to token), its card shows the applications'
  sync and health counts (synced, out of sync, healthy, degraded). Without a
  token the card is a link with a status dot.
- **The page**: a search box that filters cards as you type; sections in a
  grid with columns per section; the design pass of workstream 2 (light and
  dark, not a copy of the dashboard's background image).
- **Who sees it**: admins, like the other new areas (decision 13), until
  RBAC.

### 7. Docs and upgrade guides

For every release:
- a `docs/upgrade/` row, and a guide when operators must act;
- the settings in the chart README;
- the metrics in `docs/ops/metrics.md`;
- the API notes in `docs/notes/`.

The operator steps this plan brings:
- **GitLab**: the per-team membership.
- **server-scan**: its viewer, auditor and admin tokens.
- **cluster-navigator**: its service token.
- **MCE tokens**: the wider rights, and the per-MCE addresses.

Also:
- refresh `docs/ecosystem/notes/server-scan.md`, which predates Confs, VM
  hosts and KubeVirt servers;
- update `architecture-fit.md` and `CLAUDE.md`'s status.

## Order

1. **Now**: review and merge 0a and 0b. Workstream 1 is deployed
   (Wingman 3.7.0 and its GitLab on the sandbox); its per-MCE address is
   built with 6.
2. **Next (decision 19)**: 6, MCE placement, with the per-MCE address, and
   9, the Quick Links page, alongside it. In parallel, write the designs of 2
   (the single pane) and 8 (RBAC).
3. **Then**:
   - build 2;
   - build 3 (Segments): the smallest area, it proves the pattern;
   - build 8 once its design is agreed.
4. **After**: build 4 (Servers), page by page in the order above.
5. **When the team is ready**: build 5 (cluster-navigator), once collectors
   report and Wingman has a token.

Parallel work runs in separate worktrees and branches, with ADR numbers fixed
as above. I rotate CLAUDE.md's "Where to continue" when merging, so parallel
PRs never conflict there.

## Open questions

Answered on 2026-11-12 (decisions 13 to 19): who sees Servers and Segments,
server-scan's writes, the auditor role, reusing server-scan's code, which
nodes count for free pods, and the placement override.

Still open:

1. **The shared Git store on the sandbox** (workstream 1): does the team move
   the platform to Wingman's GitLab? (The user is talking to the other
   developers.)
2. **cluster-navigator**: does the team roll out the collectors, issue
   Wingman a token, and add a typed report endpoint?
3. **Names**: do server-scan's `mce_name` and site names equal day1's in
   production? (The user is checking.)
4. **RBAC** (workstream 8): the permission list, the scopes, and which LDAP
   groups map to which permissions; written as its design.

## Risks

- **Size**: Servers alone is close to ten thousand lines in the original.
  Building it page by page, in the order above, keeps each PR reviewable.
- **Two UIs for a while**: server-scan's and segments-manager's own UIs keep
  running; behaviour can drift until the team retires them.
- **Wingman holds more power**: with server-scan's admin token, Wingman
  becomes a privileged caller. Writes stay behind the admin check (later, the
  permission of workstream 8), a confirmation and Wingman's audit.
- **Keycloak is a new stateful service** in a disconnected install: its
  database, backups and upgrades become part of running Wingman.
- **Load**: the fleet rows are large and polled. One cache in day1 and the
  ETag keep this to one download per change.
- **The public repo**: no sandbox addresses, tokens or findings about private
  systems in any commit (convention 3).
