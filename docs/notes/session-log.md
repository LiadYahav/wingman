# Session log

Newest first. Each entry is the "Where to continue right now" section of
`CLAUDE.md` as it stood when the next unit of work started. Together with
`git log` and the ADRs each entry names, this is the record of the work.

**2026-11-18 — 3.44.8 to 3.48.0: flavors, Scale, nodepools from several InfraEnvs, Server Scan at v6.6.0.**
- **Flavors** (3.44.8, 3.45.0): a flavor's Overview stacks Metadata over
  Cluster inputs, each the page's width; a flavor may carry the cluster's
  image mirrors, optional (`image_content_sources`, `disable_idms_merge` →
  `imageContentSources`, `disableIdmsMerge`; ADR-0063). The specs project's
  `cluster-template.j2` needs the lines in `docs/upgrade/3.44-to-3.45.md`
  before a flavor may set them.
- **Scale follows update-nodepool** (3.45.1, 3.46.0; ADR-0062's two
  2026-11-18 amendments): one NodePool a run, the by-kind mode is gone; a
  scale-down may pick the servers that leave (`server_names`). The
  workflows branch is not merged; its inventory follow-ups are in the
  session log's Scale entry.
- **A nodepool may draw from several InfraEnvs** (3.47.0, ADR-0064, off:
  `DAY1_MULTI_INFRAENV_NODEPOOLS`): `infraEnvName` stays first and names
  the NodePool, the others in `additionalInfraEnvNames`; the chart renders
  `matchExpressions: In`. Needs the hostedclusters-setup chart change (a
  patch is drafted, not proposed yet) and the template lines in
  `docs/upgrade/3.46-to-3.47.md`. herzi skips such a NodePool's demand.
- **Server Scan at server-scan v6.6.0** (3.48.0, ADR-0048's 2026-11-18
  amendment, map `synced_at: v6.6.0`): server types, maintenance apart from
  health, server-scan's own colours on the Servers table, a server's page
  and the Sites cards; Fetch now behind `DAY1_SERVER_SCAN_REFRESH` (off).
  Tried once on the sandbox: Wingman's call reached server-scan, which
  refused it (409) because no vendor manager is connected there.

**Next:**
- The hostedclusters-setup chart change for `additionalInfraEnvNames`, and
  a herzi rule for such NodePools; then turn the setting on.
- When the workflows branch merges: the inventory follow-ups in the session
  log's Scale entry.
- Scale's scale-down policy per NodePool (the user): a flavor and
  create-form choice that `cluster-template.j2` writes as the entry's
  annotation (the specs project's template needs it too); more in
  `CLAUDE.local.md`. Then, when the workflow is deployed: turn Scale on and
  a first live run.
- cluster-navigator's data on the cluster page and per MCE
  (`docs/ideas/single-pane.md` workstream 5).
- Flavors v2's "Left for later": missing add-ons in one MR per team, the
  cluster-name prefix in the web, a preview of an unsaved flavor.
- Tuning: a lock per pool.
- Code organisation, later (the user): 28 files left in the size baseline.
- The team's questions: herzi, provision-cluster's 24 characters, RBAC, a
  shared Git store.

**2026-11-18 — 3.48.0: Server Scan at server-scan v6.6.0.**
- **The sync** (ADR-0048's 2026-11-18 amendment; `scripts/upstream_diff.py
  server-scan v6.6.0`, the map's `synced_at: v6.6.0`): a ticked severity
  leaves out servers in maintenance and the sites count them apart (v6.3.0);
  `server_type` and the Type filter, Physical, VM and vendor bars on the
  Sites cards (v6.3.0); the BMC copy button and a health bar per card
  (v6.2.0); the Servers and Events tables scroll in their own box (v6.4.0,
  v6.6.0).
- **Fetch now** (v6.5.0, v6.6.0), the area's third write: `POST
  /api/day1/server-scan/servers/{id}/refresh`, `AdminUser` as server-scan
  keeps it, the admin token, sent once, a 120-second wait under nginx's new
  130-second location, `409 SERVER_REFRESH_REFUSED` in server-scan's words;
  on a server's page and first on every Servers row. Off by default
  (`DAY1_SERVER_SCAN_REFRESH`, the chart's `day1.serverScanRefresh.enabled`;
  needs server-scan v6.5.0 or later): no button until it is on. Not yet
  tried against the sandbox's server-scan.
- **server-scan's own colours** (the user's request): the Servers table, a
  server's page and the Sites cards wear its palette
  (`features/server-scan/palette.css`, its dark values, light equivalents),
  its cells, icons and filter bar.

**Next:**
- When the workflows branch merges: the inventory follow-ups above.
- Scale's scale-down policy per NodePool (the user): a flavor and
  create-form choice that `cluster-template.j2` writes as the entry's
  annotation (the specs project's template needs it too); more in
  `CLAUDE.local.md`. Then, when the workflow is deployed: turn Scale on and
  a first live run.
- cluster-navigator's data on the cluster page and per MCE
  (`docs/ideas/single-pane.md` workstream 5).
- Flavors v2's "Left for later": missing add-ons in one MR per team, the
  cluster-name prefix in the web, a preview of an unsaved flavor.
- Tuning: a lock per pool.
- Code organisation, later (the user): 28 files left in the size baseline.
- The team's questions: herzi, provision-cluster's 24 characters, RBAC, a
  shared Git store.

**2026-11-18 — Scale sets one NodePool a run (PR #101), and a scale-down may pick its servers (the PR after it).**
- **The workflow changed** (team-redbull/workflows `feat/update-nodepool`,
  b1976f4 and aab8949, not merged): `update-nodepool` takes `nodepool` only,
  `infra_env_kind` is a 422; a scale-down may name the servers that leave
  (`server_names`); the result has `ignored`; a new failure,
  `ScaleDownServersInvalidError`.
- **Wingman follows** (ADR-0062's 2026-11-18 amendment): day1 sends exactly
  `{mce_cluster, cluster, nodepool, replicas}`; the by-kind mode and the
  hardware type total are gone (domain, schemas, fake, web, docs); day1
  refuses `infra_env_kind` and a NodePool the file does not name (or names
  twice) before anything is sent; a run recorded by kind still shows; the
  run card lists `ignored` and explains `ScaleDownServersInvalidError`.
- **Picking the servers that leave** (the user's decision, ADR-0062's later
  2026-11-18 amendment): optional, in the scale-down's confirmation, from
  the Nodes tab's read of the MCE (needs live status); exactly as many as
  leave, sent as `server_names`, each named by the workflow's own rule
  (`machines.machine_server`, `GET .../nodes`' `machine_server`); never on a
  scale-up. Needs the workflows release with `server_names` on the
  orchestrator and every MCE's worker (`docs/upgrade/3.39-to-3.40.md`
  step 3.5).
- **The branch's other changes** (add-server-to-mce one server per run from
  server-scan, ADR-0063 there; uninstall and remove-server-from-mce) break
  nothing Wingman sends today. When it merges: `domain/inventory.py`'s
  `named_for` should match `ocp-<infraEnv>-` with the dash, the
  orchestrator OpenAPI snapshot test treats `namespace` as hidden, and the
  inventory docs describe the allocation, maintenance on a no-Agent timeout
  and the early lock release.

**2026-11-17 — 3.44.0 to 3.44.3: credits per area, the docs refresh, a layout for the integrations.**
- **Credits** (3.44.0, 3.44.1): five quick clicks on an area's brand show who
  built it, each person with their years (`lib/areas.ts`).
- **Docs** (3.44.2, 3.44.3): the in-app Documentation page covers the
  Overview, Cluster Workflows, Inventory Management, Quick Links, Segments and
  Server Scan (a test opens every Contents entry); `docs/README.md` indexes the
  docs, `docs/architecture.md` is the overview to read first; this file was
  shortened (its CI pass is `docs/ops/ci-maintenance.md`, its status history
  is at the end of `docs/notes/session-log.md`).
- **One place per mirrored system** (3.44.4 to 3.44.6, the owner's
  decision): server-scan's and segments-manager's day1 code is in
  `integrations/server_scan/` and `integrations/segments_manager/` (ADR-0001's
  layers inside, enforced by import-linter; ADR-0001's 2026-11-17 amendment),
  their web code in `apps/web/features/server-scan/` and
  `apps/web/features/segments/` (`api`, `types`, `lib`, `components`;
  ADR-0056's note). Checked live on the sandbox after the move.
- **Syncing with a new upstream release:** `docs/integrations/<system>.yaml`
  maps each Wingman file to the upstream files it follows and records the
  version it matches (server-scan v6.1.0, segments-manager `a4edc12`);
  `scripts/upstream_diff.py <system> [<ref>]` lists what changed upstream for
  each; `docs/integrations/<system>.md` is the checklist. A test fails when a
  ported file is missing from its map. Unreleased on server-scan (2026-11-17):
  maintenance no longer counts as Available, and a server refresh write.

**Next:**
- Scale's scale-down policy per NodePool (the user): a flavor and
  create-form choice that `cluster-template.j2` writes as the entry's
  annotation (the specs project's template needs it too); more in
  `CLAUDE.local.md`. Then, when the workflow is deployed: turn Scale on and
  a first live run.
- cluster-navigator's data on the cluster page and per MCE
  (`docs/ideas/single-pane.md` workstream 5).
- Flavors v2's "Left for later": missing add-ons in one MR per team, the
  cluster-name prefix in the web, a preview of an unsaved flavor.
- Tuning: a lock per pool.
- Code organisation, later (the user): 28 files left in the size baseline.
- The team's questions: herzi, provision-cluster's 24 characters, RBAC, a
  shared Git store.

**2026-11-16 — 3.38.0 to 3.43.0: Inventory Ready/Needs fix, tuning in the every-nodepool rule, Scale through update-nodepool, Server Scan at server-scan v6.1.0.**
- **Inventory Management** (3.38.0, ADR-0057's amendment): a pool's free
  servers split into Ready and Needs fix, a Total per pool and MCE,
  collapsible MCEs; an admin may install a Needs-fix server by name with
  `allow_unhealthy`, after a confirmation.
- **Tuning in the flavor's "same on every nodepool"** (3.39.0, ADR-0061's
  amendment): a switch beside the configs rule locks the same profiles on
  every nodepool, on by default unless the nodepools differ.
- **Scale through the platform's update-nodepool workflow** (3.40.0, 3.41.0;
  ADR-0062 and its amendment), behind `day1.scaleNodepools.enabled`, off by
  default and off on the sandbox: a − N + on each NodePool card of the Nodes
  tab (one NodePool, exact), a hardware type's total in a small dialog (kinds
  with 2+ NodePools), one change at a time, the run in place. While on, a
  NodePool's replicas change only through the workflow: an edit that changes
  them is refused, a flavor's sync or rollout leaves them out and offers
  "Restore to N". A flavor-locked NodePool is not scaled; the lock is
  Wingman's rule, not the platform's (a direct GitLab edit or a direct
  workflow call can still move it, shown as drift).
- **3.42.0**: a short confirmation before every scale, both ways, saying on a
  scale-down which nodes leave by the NodePool's `redbull.io/scale-down-policy`
  (read from the nodepool entry's `annotations` in the day1 file); the cluster
  page's first render matches the server's (no hydration error). Turning Scale
  on: `docs/upgrade/3.39-to-3.40.md`.
- **Server Scan at parity with server-scan v6.1.0** (3.43.0, ADR-0048's
  2026-11-16 amendment): Collection error with its cause, an event's serial
  and BMC (details and the Server box), Healthy without servers in
  maintenance; an older server-scan still works.
- The workflow is on team-redbull/workflows' branch `feat/update-nodepool`
  (not merged when this was written): Wingman follows its contract and has
  not run against it live. The day1 CI tuning patch went to the user as a zip
  for the air-gap; workflows PR #23 (provision-cluster sets
  `tuningConfigmap` aside) is merged.

**Next:**
- Scale's scale-down policy per NodePool (the user): a flavor and
  create-form choice that `cluster-template.j2` writes as the entry's
  annotation (the specs project's template needs it too); more in
  `CLAUDE.local.md`. Then, when the workflow is deployed: turn Scale on and
  a first live run.
- cluster-navigator's data on the cluster page and per MCE
  (`docs/ideas/single-pane.md` workstream 5).
- Flavors v2's "Left for later": missing add-ons in one MR per team, the
  cluster-name prefix in the web, a preview of an unsaved flavor.
- Tuning: a lock per pool.
- Code organisation, later (the user): 28 files left in the size baseline.
- The team's questions: herzi, provision-cluster's 24 characters, RBAC, a
  shared Git store.

**2026-11-16 — 3.35.0 to 3.37.0: team chart groups, the Grafana dashboard, tuning profiles.**
- **A team's charts sit in `<team>/helm-charts/<chart>`** (3.35.0,
  ADR-0060): the New add-on form suggests that address; only a suggestion.
- **The Server Scan Servers page starts higher** (3.35.1): heading, count,
  search and exports on one row.
- **The Grafana dashboard** (3.36.0): Overview (MRs opened and merged,
  approvals, workflow runs, server-scan writes, systems failing), Activity,
  API, External systems (a `dependency` variable), GitLab write safety; a test
  ties every label value a panel matches to what the code exports. Checked in
  Grafana 13 against OpenShift user-workload monitoring (Thanos' tenancy port).
- **Tuning profiles** (3.37.0, ADR-0061): `tuning/` in the day1 repo holds
  Tuned and PerformanceProfile manifests; a flavor and the create form pick
  them per nodepool (`tuningConfig`), lockable as a rule for every nodepool,
  at most one PerformanceProfile per pool, a Tuned's PerformanceProfile
  suggested; drift and sync write only the names. The day1 CI injects
  `tuningConfigmap` (an automation key, ADR-0012's amendment) from the
  catalogue, keeping a cluster's differing copy and reporting it; that CI
  patch and the chart's single `tuningConfig` render ship to the air-gap
  separately. provision-cluster must set `tuningConfigmap` aside like
  `mcConfigMap` (team-redbull/workflows PR #23).
- Production creates clusters through provision-cluster now
  (`day1.provisioner: workflow`, still a switch). Argo CD is synced by a person
  today, auto-sync later: show "merged" and "applied" for both.

**Next:**
- cluster-navigator's data on the cluster page and per MCE (running version,
  status, Git against what runs; `docs/ideas/single-pane.md` workstream 5):
  the team adds a Wingman entry to its `SERVICE_TOKENS`.
- Flavors v2's "Left for later": missing add-ons in one MR per team, the
  cluster-name prefix in the web, a preview of an unsaved flavor.
- Tuning: a lock per pool (a flavor with GPU pools needing different
  PerformanceProfiles can preset them but not lock them today).
- Code organisation, later (the user): helpers out of `.tsx`, a typed day2
  call layer, the design splits; 30 files left in the size baseline.
- The team's questions: herzi, provision-cluster's 24 characters, RBAC, a
  shared Git store.

**2026-11-14 — 3.25.0 to 3.34.0: Server Scan complete (option C), chart hardening, a fuller Overview.**
- **The Server Scan area at parity with server-scan's UI** (ADR-0048's
  amendments; contract `docs/notes/2026-11-13-server-scan-area-api.md`), one
  PR per page:
  - the server's page, its History on server-scan's auditor token (a third
    optional Secret key; 3.25.0), linked from the cluster's Nodes tab for
    admins (3.26.0);
  - Claude (3.27.0), Architecture (3.28.0: server-scan's diagrams read by
    day1, shown in a sandboxed frame), Confs (3.29.0), Rules & Policies
    (3.30.0);
  - Events (3.31.0): the fleet's audit trail, auditor token; Jobs (3.32.0):
    server-scan's CronJobs, runs and logs, and **Run job**, the area's second
    write. server-scan's jobs router is admin-only, so every Jobs route uses
    the admin token, reads included; a start is never retried and is logged
    with the person.
  - One token rule (`domain/server_scan_tokens.py`), one write sender, one
    guard per token; the area's routers mount from `api/v1/server_scan_area.py`.
- **Chart hardening** (3.33.0, ADR-0058, ADR-0059): nginx stays the one
  entry point, now Red Hat's UBI nginx-124 pinned by digest, answering an
  RFC 9457 problem when day1 or day2 does not; every pod restricted
  (non-root, seccomp, no capabilities, read-only root, no service-account
  token); `values.schema.json` refuses unknown keys; the Wingman image tags
  have no default; every `sslVerify` takes a boolean. Operators follow
  `docs/upgrade/3.32-to-3.33.md`.
- **Overview** (3.34.0): its buttons beside the title in one style; where
  clusters run, OpenShift versions with upgrades available and running, free
  servers per MCE pool, and, for admins with those areas, free segments and
  the server fleet's health.
- The sandbox runs 3.34.0; its nginx moved to the UBI image with 3.33.0.

**Next:**
- Code organisation, later (the user): helpers out of `.tsx`, a typed day2
  call layer, the design splits; 33 files left in the size baseline.
- Small: herzi's InfraEnv notes per MCE pool in Inventory Management; the
  cache-key oddities; base-ui 1.4.0's searchable dropdown keeps its old
  search when reopened within its close animation (check a newer base-ui at
  the next dependency pass).
- The team's questions: the upgrade workflow on the sandbox and its direct
  pushes, herzi, provision-cluster's 24 characters, RBAC, a shared Git store.

**2026-11-14 — 3.18.5 to 3.24.0: Install servers, upgrades in the list, option C started.**
- **Web code** (3.18.5): the web calls day1 through `lib/api/day1/`
  (`day1Api`, `day1Keys`; 56 cases pin the keys), plus a readability pass on
  the code written last year (the user's ask; memory: refactors include
  readability, in separate commits).
- **Inventory Management** (3.19.0, ADR-0057 amendment): an **Install
  servers** button in the page header; install works without live MCE
  status (pools from the cluster files' `infraEnvName`).
- **Cluster upgrade** (ADR-0055 amendments): the fleet's runs live **in the
  clusters list** (3.20.0): "Upgrade available → <version>" from the MCE's
  offered versions (ADR-0034, a hint only; the workflow plans) and
  "Upgrading · <phase>", an Upgrade button on the row for admins, a filter.
  Starting stays admin-only until RBAC (workstream 8) gives it to owners.
- **Sig values everywhere**: day2's MR titles (3.19.1; old titles still
  parse) and its error and lint messages (3.20.1, with a guard test).
- **Option C** (decision 22), the user's go: Segments Manager at full parity
  (3.21.0: an Excel-style filter on every column in the shared table,
  Excel export with `write-excel-file`, a connection dot); **Server Scan**
  in the top bar, page by page (ADR-0048): Sites (3.22.0), Servers with
  maintenance on/off and server-scan's admin token as an optional Secret key
  (3.23.0).
- `fix(core)` (3.23.0): Wingman's INFO records (who started an uninstall, an
  install, a maintenance) now reach the pod log.
- The sidebar collapses to an icon rail, Ctrl/⌘+B (3.24.0).
- The sandbox runs 3.24.0 with `DAY1_ADD_SERVERS` and `DAY1_UPGRADES` on
  (the user's OK: "this is a lab cluster"). The upgrade workflow writes to
  its own day1 repo, not Wingman's GitLab copy.

**Next:**
- Server Scan's next pages, one PR each: Server detail (in progress; the
  auditor token as a third optional key), Confs, Rules & Policies, Events,
  Jobs, Architecture, Claude.
- Code organisation, later (the user): helpers out of `.tsx`, a typed day2
  call layer, the design splits; 33 files left in the size baseline.
- The team's questions: the upgrade workflow on the sandbox and its direct
  pushes, herzi, provision-cluster's 24 characters, RBAC.

**2026-11-13 — 3.14.1 to 3.18.x: code organisation, Segments, cluster upgrade, Inventory Management.**
- **Code organisation** (ADR-0056, convention 16): file-size and complexity
  guards whose baselines only shrink (3.14.2). Mechanical splits so far, no
  behaviour change:
  - day2's and day1's API schemas, one module per router; the OpenAPI
    document is byte-identical (3.14.1, 3.18.1);
  - the web's type files by section (3.18.2);
  - the docs page, one file per section (3.18.3);
  - the web calls day1 through `lib/api/day1/` (`day1Api`, `day1Keys`,
    3.18.5).

  34 files are left in `scripts/file-size-baseline.txt`.
- **Segments area** (ADR-0047, 3.15.0): segments-manager's page in Wingman,
  read-only, admins only, from the top bar's area switch, on a shared
  TanStack table (`components/data-table/`) with Vitest for pure logic. In
  3.17.0 each area got its own sidebar and brand ("Segments Manager").
- **Option C** (single-pane decision 22, 3.15.1): segments-manager and
  server-scan fully integrated, every feature and their look, each a top-bar
  platform. **Planned only: build it on the user's go.**
- **Cluster upgrade** (ADR-0055, 3.16.0): start, show and decide the
  platform's `upgrade-cluster` workflow on the cluster page, behind
  `DAY1_UPGRADES`. While it is on, `mastertag`/`workertag` change only through
  it. It is off on the sandbox, which has no upgrade workflow deployed.
- **Inventory Management** (ADR-0057, 3.18.0): a Wingman sidebar page for the
  orchestrator's server workflows:
  - available Agents per MCE pool, from server-scan;
  - the `add-server-to-mce` runs, herzi's (fake data) and people's;
  - adding servers by count or by name, with server-scan's locks respected
    (admins, `DAY1_ADD_SERVERS`, off on the sandbox).

  Everyone signed in reads it. It is not a fleet view: a server's record
  belongs to the future Server Scan area. The cluster page and MCE placement
  are unchanged ("the cluster page is perfect").
- In production, server-scan's MCE and site names equal day1's (the user).

**Next:**
- option C on the user's go;
- the next code-organisation steps (the audit is the plan):
  - a typed day1 API module for the web;
  - helpers out of `.tsx` files;
  - then the design splits: the new-cluster page, the big services, day1's
    infrastructure by system;
- the team's questions in the upgrade and provision notes, and herzi's
  InfraEnv annotations (one more MCE read).

**2026-11-13 — 3.13.2 to 3.14.0: Sig values, speed, cleanup, CI, the cache fix, the workflow's MR seen.**
- 3.13.2 (#41, ADR-0043's amendment): the UI says **Sig values** (chart
  values → Sig values → cluster values) and Edit add-on; the create form's MCE
  section is one row per MCE with its reasons in tooltips.
- 3.13.3 (#43, ADR-0041's amendment): day2's chart lookups answer stale while
  one read refreshes them, so `/addons` stops waiting on GitLab; list links
  prefetch on hover, not on render (`IntentLink`).
- 3.13.4 (#42): a cleanup with no behaviour change; knip in the web lint.
  3.13.5 (#44, ADR-0032's amendment): the mocked E2E suite on two runners.
- 3.13.6 (#45, ADR-0011's amendment): `TtlCache` runs each fetch in its own
  task that every reader awaits shielded, so a dropped request never cancels
  the read the others share.
- 3.14.0 (ADR-0042's amendment): Wingman sees the provision-cluster
  workflow's day1 MR by its branch `provision-cluster/<stem>`: counted as an
  open create (taken names, duplicate creates, placement) and listed on
  Approvals as the workflow's (`opened_by_workflow`), reviewed and merged in
  GitLab, never in Wingman (the workflow records no requester).

The user's decisions today, for the work in flight on their own branches:
- **Cluster upgrade** through the platform's `upgrade-cluster` workflow
  (ADR-0055): start, show and decide on the cluster page, behind
  `DAY1_UPGRADES`; while on, `mastertag`/`workertag` change only through it.
- **Code organisation** (ADR-0056): file-size and complexity guards with
  allowlists that only shrink, then the mechanical splits (schemas per
  router, web types, a typed day1 API module), then the design splits one PR
  at a time. The audit is the plan.
- **Segments area** (ADR-0047): planned, waiting for the user's OK on the plan.
- **Install server** (`add-server-to-mce`, MCE-wide, not per cluster): where
  it lives is still being decided with the user.

**Next:** merge and deploy each branch in turn (one release at a time); the
open questions for the team in the upgrade note and ADR-0042.

**2026-11-13 — 3.12.2 to 3.13.1: Wingman always picks the MCE, add-ons in one place, Wingman made lighter.**
- 3.12.2 (#39, ADR-0050's amendment): the create form asks the site, prod or
  prep and the version, never the MCE; placement always runs, and with live
  MCE reads off it decides on Git and server-scan and says what it did not check.
- 3.13.0 (#38, ADR-0053's amendments): the Operators pages are folded into
  Addons (the user: "operators is addons"; `operators/` is only the folder);
  no exclusions (production has none, only per-env and per-cluster values);
  values per env and per MCE, hosted or UPI cluster; Deploy on specific MCEs,
  one install MR per MCE.
- 3.13.1 (#40; the user: "we have put many many loads into the wingman"):
  Quick Links lists links and never calls them, no status dots or ArgoCD
  counts (ADR-0052's amendment, ~2,250 lines fewer); the Destinations page is
  removed, a destination's name on an add-on's page opens its charts
  (ADR-0020's amendment); `/health/ready` asks GitLab only until it has
  answered once (ADR-0054; it made hundreds of calls an hour on the sandbox).
  **Side features stay thin from now on**: config and links, no live calls,
  no new adapter or Secret, unless the user asks for more.

The team's sandbox runs Wingman in namespace `wingman` with its own GitLab
(addresses and Secrets in the git-ignored `CLAUDE.local.md`). Its GitLab now
also has four real charts for trying New add-on: `helm-charts/cert-manager`,
`external-secrets`, `reloader`, `podinfo`, two version branches each.

**Next:** the user's report that New add-on is very slow on the sandbox
(retry on 3.13.x and read day2's and GitLab's logs for that request); a
flaky E2E in `addon-defaults.spec.ts` (the edit form can open before its
repo URL is filled: "Give the chart repo URL"). Then the plan's order in
`docs/ideas/single-pane.md`: the single pane proven on Segments (ADR-0047),
Servers (ADR-0048), RBAC with Keycloak federating LDAP (ADR-0051),
cluster-navigator's data (ADR-0049). Before building any of it, ask what the
thin version is. Waiting on the user and the team: the real pod cost of a
control plane, server-scan's MCE names in production, the shared Git store,
ADR-0042's open questions.

**2026-11-12 — 3.8.0 to 3.12.0: the one-place plan, teams author operators, per-cluster rollout, MCE placement, Quick Links.**
The architect's vision is the plan in `docs/ideas/single-pane.md` (#31,
3.9.1): decisions 1–21, workstreams with fixed ADR numbers, open questions.
Released today, each built by an agent and reviewed here:
- 3.8.0 (#33, ADR-0043): teams create add-ons and edit team and fleet
  defaults with ArgoCD sync options; per-team opt-in by the GitLab account's
  access (`TEAM_READ_ONLY`). Merged before its review finished, at the
  user's request; the review's 8 findings were fixed in 3.12.0.
- 3.9.0 (#34, ADR-0052): Quick Links, a launcher of every ArgoCD and console
  (hub and MCEs) plus the team's own links, with server-side status and
  optional ArgoCD counts.
- 3.10.0 (#32, ADR-0044): **a change reaches each cluster through its own MR**
  (the user's core principle: small blast radius, the customer takes it when
  ready). Import opens one MR per cluster; a new flavor version opens one sync
  MR per linked cluster automatically, restart-safe; a cluster is measured
  against its own flavor version, so a newer one is "update available".
- 3.11.0 (#35, ADR-0045, ADR-0050): Wingman picks the MCE: version, free pods
  on workers (allocatable − in use ≥ `PLACEMENT_MIN_FREE_PODS`, 70), healthy
  free servers per node type from the InfraEnv and server-scan; then fewest of
  this owner (mador), fewest overall, most spare; an admin may override with a
  reason. A per-MCE API address in the MCE tokens Secret.
- 3.12.0 (#36, ADR-0053): an Operators page per team: which destinations a
  fleet default reaches (`exclusions.yaml`, edited in place), per-destination
  values and deploy-config carve-outs, every write listing what it does to
  each destination, confirmed against the preview's digest.

Wingman 3.12.0 runs on the team's sandbox in namespace `wingman` with its own
GitLab seeded from `dev/gitlab-fixtures` (addresses and Secrets are in the
git-ignored `CLAUDE.local.md`; its workers are near the disk eviction line).

**Next** (the plan's order): the single pane (top-bar switch, the design
pass, a table component) proven on the Segments area (ADR-0047); the Servers
area with server-scan's exact behaviour, writes included (ADR-0048); the RBAC
design with Keycloak federating LDAP (ADR-0051); cluster-navigator's data once
the team rolls out collectors (ADR-0049). Waiting on the user and the team:
the real pod cost of a control plane, server-scan's MCE names in production,
the shared Git store on the sandbox, ADR-0042's open questions.

**2026-11-12 — 3.7.0: create can start the provision-cluster workflow (ADR-0042), off by default.**
Released today: 3.4.1 (#25), 3.5.0 (#26, the EPG from segments-manager,
ADR-0039), 3.6.0 (#27, create from a flavor: a nodepool ratio whose
replicas move together, a suggested name with the next free letter,
letters-only sequences, ADR-0040; the generic network template
`nm-conf-template.bu`, written as plain `nm-conf` and the default, ADR-0027's
amendment) and 3.6.1 (#28, ADR-0041: stale-while-refresh in the core cache,
a merge re-reads only the files it changed, warm-up, gzip; a review found
and fixed a read after a write joining a pre-write refresh). The upgrade
index lists every release, with a generic upgrade for those without a guide.

3.7.0 (#29, with this docs work folded in): create can start the platform's
`provision-cluster` workflow instead of opening Wingman's MR, behind
`DAY1_PROVISIONER` (chart `day1.provisioner`, default `merge-request`, so
nothing changes until the team turns it on; `docs/upgrade/3.6-to-3.7.md`).
Wingman still renders and checks the file, then starts the run and shows its
phase, MR and error. The API note's open questions
(`docs/notes/2026-11-12-provision-cluster-workflow-api.md`) wait on the team:
the 24-character `cluster` limit, the workflow's MR not in Wingman's format,
add-ons, who started a run.

**Next:**
- the team's answers to ADR-0042's open questions, before turning the workflow on;
- the user's decision: does a cluster name without a letter take `-a` for
  the suggestion (ADR-0040)?
- deploy 3.6.1 and check, on a real cluster, the Nodes tab, the EPG and
  `docs/ops/performance.md`'s numbers;
- ADR-0040's "Left for later"; flavors v2's; the architect's answers.

**2026-11-12 — create from a flavor: a sizing ratio, a suggested name, letter sequences (ADR-0040).**
PR #27 on `roiblum/feat-create-from-flavor` (built by a fork, reviewed here;
API: `docs/notes/2026-11-12-create-from-flavor-api.md`). A flavor may size
its nodepools by `spec.day1.nodepool_ratio` (`[1, 2, 1]`): the create form
asks for one size and the file gets plain `replicas`. Creating from a
flavor, the form fills in `ocp4-<env>-<flavor>-<site>-<letter>` from
`GET /clusters/name-suggestion` (the next letter no cluster file or open
create MR has; editable). A new cluster's sequence is one letter a-z; a
name without one is still accepted. The MCE's InfraEnv list is cached
(`MCE_INFRAENV_CACHE_SECONDS`, 600). Before it: 3.4.1 (#25, the add-on
catalog beside a long selection) and 3.5.0 (#26, the EPG from
segments-manager, ADR-0039; upgrade `docs/upgrade/3.4-to-3.5.md`).

**Next:**
- merge PR #27 (3.6.0; no operator steps);
- the speed fork (`roiblum/perf-shared-cache`) reports why loading is slow
  in production and what it fixed: review it and open its PR;
- left for later in ADR-0040: drift, import and sync of a ratio, resizing an
  existing cluster; whether a new cluster must have a letter;
- after deploying, check the Nodes tab and the EPG on a real cluster;
  flavors v2's "Left for later"; the architect's answers.

**2026-11-12 — the cluster's EPG from segments-manager (ADR-0039), 3.5.0.**
On `roiblum/feat-cluster-segment`. The cluster page's "HostedCluster &
network" card shows VLAN and Segment from the cluster file (`vlanId`,
`dhcp_values.network` as its /24: Git is the source of truth) and the EPG
segments-manager records for that segment (`GET /clusters/{name}/network`,
`docs/notes/2026-11-11-cluster-network-api.md`). Where segments-manager
disagrees with the file (VLAN, holder, status, no such segment), the card
warns; it never changes what is shown. `SEGMENTS_MANAGER_URL` (chart
`segmentsManager.url`) turns it on; `DAY1_FAKE_FLEET` fakes it from
`dev/fleet-fixtures/segments.yaml`. Upgrade: `docs/upgrade/3.4-to-3.5.md`.
3.4.0 and 3.3.1 are released; PR #25 (3.4.1, the flavor editor's add-on
catalog beside a long selection) is open.

**Next:**
- merge PR #25, then this one; two forks are working on their own branches
  and report for review: `roiblum/feat-create-from-flavor` (nodepool ratio
  in a flavor, InfraEnvs from the MCE, auto name with a letter seq) and
  `roiblum/perf-shared-cache` (why loading is slow; caches per replica);
- after deploying, check the Nodes tab and the EPG on a real cluster;
- flavors v2's "Left for later"; the architect's answers.

**2026-11-11 — 3.3.1 template fix; nodes by NodePool and node uninstall (ADR-0038).**
PR #23 (3.3.1): network templates are `nm-conf-template-<hw>.bu`, the CI's
name; 3.3.0 wanted `-hw-` and refused every network config (ADR-0027's
correction). Then, on `roiblum/feat-cluster-nodes` (a backend and a web agent
against `docs/notes/2026-11-11-cluster-nodes-api.md`, redesigned once by the
user):
- the cluster page's Nodes tab shows each NodePool from the MCE: its nodes
  (Machine → AgentMachine → Agent → BareMetalHost = server-scan's server),
  each missing piece and why, and which node an update is working on; servers
  server-scan lists that no Machine has sit apart. Nothing on the cluster list.
- Uninstall beside a node starts the platform's `uninstall-server-from-hc`
  and shows its run. Wingman only triggers and shows: the procedure and its
  checks are the workflow's.
- In-place updates: the MCE shows progress, the rebooting node and a failed
  one, never the drain before a reboot (`docs/ecosystem/notes/hypershift-node-state.md`).
  The guest Nodes would need each cluster's admin kubeconfig: not done.
- The MCE token needs more reads (the API note's §4, `docs/upgrade/3.3-to-3.4.md`).
  `DAY1_FAKE_FLEET=true` (development) fakes server-scan, the orchestrator and
  the MCE for demos.

**Next:**
- merge PR #23 (3.3.1), then the nodes PR (3.4.0); deploy with the 3.3→3.4 guide;
- check the workflow class name `UninstallServerFromHcWorkflow` (the runs list
  answers `[]` for any unknown type) and the MCE reads against a real hub;
- flavors v2's "Left for later"; the architect's answers.

**2026-11-08 — flavors v2, all stages, on `roiblum/feat-flavors-v2`.**
Main merged in (the branch's ADRs 0033/0034 became 0036/0037; the import asks
`changed_since`, ADR-0035). Day1: sync (`POST /clusters/{name}/sync[/preview]`,
removals confirmed, how each nodepool rolls), `owner` on cluster rows,
`enforced_locks` on flavors. Web (four parallel agents, then merged): the
flavor editor, the create form, the flavor page with import, value drift and
the sync dialog, owner filters; the UI says Flavor. Checked: the gate, 283
mocked E2E, the three live suites on the reseeded GitLab CE, and
`day1_live_e2e.py` (import and sync against real GitLab). Upgrade guide:
`docs/upgrade/3.2-to-3.3.md`.

**Next:**
- merge the PR (release 3.3) and deploy with the upgrade guide;
- flavors v2's "Left for later" (`docs/ideas/flavors-v2.md`);
- day1's first cluster list after a merge still costs one history lookup per
  cluster (ADR-0035, Consequences);
- the architect's answers (`docs/ideas/architecture-fit.md`).

**2026-11-08 — PR #20 released 3.1.0; repos read once per commit (ADR-0035).**
PR #20: a renamed chart repo no longer fails the catalog (`get_project` follows
GitLab's rename redirect, `chart-repo-unreadable`, `repourl-moved` on the Lints
page); the ladder is read without `schemaVersion`; CI retries tool downloads.
Then, on `roiblum/feat-repo-snapshots` (the user chose it):
- `GitLabPort.get_branch` and `read_archive`, with `RepoSnapshots` in core;
- day1 and day2 read files and trees through them;
- a read's `last_commit_id` is now the commit read at (see the key facts);
- day1's stale check asks `changed_since`, and "changed by" comes from
  `last_change`.
Old and new answers were compared on scaled local data and are identical.

**Next:**
- day1's first cluster list after a merge still costs one history lookup per
  cluster; carry unchanged files forward from a compare (ADR-0035,
  Consequences);
- flavors v2 on `roiblum/feat-flavors-v2`: stage 2's sync is half done in the
  worktree `agent-a35695ba357fd9bb2` as a WIP commit; then stage 3, the web
  pages and the flavor page redesign (apple-design skill); an upgrade guide
  for its operator steps. Merge main into it first: its ADRs 0033 and 0034
  collide with main's and become 0036 and 0037.

**2026-11-08 — releases 3.0.1 to 3.1.0: numbering, status, chart move, two
production bugs.** 3.0.1 versions every release from its commits (ADR-0031);
3.0.2 reads the HostedCluster `ocp4-<clusterName>` (ADR-0015 correction) and
moves the chart to `deploy/helm/wingman/`. PR #20 (3.1.0):
- a renamed chart repo no longer fails the whole catalog: `get_project`
  follows GitLab's rename redirect, an unreadable chart repo is that chart's
  `chart-repo-unreadable`, and the Lints page flags every `repourl-moved`;
- the upgrade ladder is read without `schemaVersion`, as production writes it
  (ADR-0034 correction).

**Next:**
- the user decides on reading each repo once per commit
  (`docs/ideas/repo-snapshots.md`);
- flavors v2 on `roiblum/feat-flavors-v2`: stage 2's sync is half done in the
  worktree `agent-a35695ba357fd9bb2` as a WIP commit; then stage 3, the web
  pages and the flavor page redesign (apple-design skill); an upgrade guide
  for its operator steps. Merge main into it first; watch ADR numbers.

**2026-11-08 — PR #17 finished and merged; flavors v2 started.** The web
followed both API notes; report-only drift (ADR-0025); the in-app docs
audited and guarded (`tests/repo/test_web_docs_contract.py`); UX basics; a
cleanup and review pass (legacy package gone, duplicates in core, the
agents' mistakes fixed); the delete-cluster workflow contract (ADR-0033);
versions from the upgrade ladder. The user's decisions are in
`docs/ideas/flavors-v2.md` and `architecture-fit.md`. **Next:** flavors v2 on
`roiblum/feat-flavors-v2`:
- stage 2's sync, half done in the worktree `agent-a35695ba357fd9bb2` as a
  WIP commit;
- stage 3, the web pages and the flavor page redesign (apple-design skill);
- an upgrade guide for its operator steps.

**2026-11-07 — integration of day1, day2 and CI.** Branch
`roiblum/feat-ecosystem-day1-day2`. Merged the three agent branches: day1
(`wingman_day1`, ADRs 0012-0019), day2 (`wingman_day2`, ADRs 0020-0024) and
CI (ADRs 0030-0032). Session tokens now expire by the injected clock. Every
Python package is on the strict bar (`scripts/python-packages.sh`). Run
locally: day1 `uv run uvicorn wingman_day1.main:app --port 8001`, day2 `uv run uvicorn
wingman_day2.main:app --port 8002` (env in each `settings.py`; both read
`GITLAB_TOKEN`; `WINGMAN_ENVIRONMENT=development WINGMAN_GIT_BACKEND=fake`
for the fixtures). **Next:** the web pages for both API change notes
(`docs/notes/2026-11-07-day{1,2}-api-changes.md`), the chart env, an
end-to-end run of the whole stack. **Deferred:** ArgoCD sync/status (no Argo
API access), `exclusions.yaml` edits, OCP-version pin MRs. **Open:** team
questions 2 (`clusterName`) and 3 (off-convention MCEs) in
`docs/ecosystem/README.md`.

**2026-11-07 — the day2 rewrite.** Branch `worktree-agent-a2d6d3b83dd18abaf`
(on `706935d`). `apps/day2-service/src/wingman_day2` replaces the legacy
service: four destination kinds discovered from team folders plus day1, the
platform's value stacks with per-key provenance, install/update/remove/bulk as
one MR per team (no per-cluster `targetRevision` unless an emergency pin is
asked for; removal orphans the workload, and says so), render_chain.py's lints
plus Wingman's, approvals by `(team, iid)` (ADRs 0020-0024). An oracle test
runs the team's own `render_chain.py` (vendored, with the platform charts,
through helm) against Wingman's discovery. Run it with
`uv run uvicorn wingman_day2.main:app --port 8002` from the repo root; env in
`wingman_day2/settings.py` (`GITLAB_TOKEN`, not `GITLAB_ACCESS_TOKEN`;
`DAY1_GITLAB_PROJECT_ID`; `WINGMAN_GIT_BACKEND=fake` for the fixtures).
**Next:** the web pages for the new API
(`docs/notes/2026-11-07-day2-api-changes.md`); the chart passes
`GITLAB_ACCESS_TOKEN` where wingman-core reads `GITLAB_TOKEN`. **Deferred:**
ArgoCD sync/status (no Argo API access), editing `exclusions.yaml` (needs
comment-preserving YAML), OCP-version pin edits as first-class MRs.

**2026-11-07 — day1 on `wingman-core`.** Branch
`worktree-agent-a8c8a548e56c6a474` (to merge into
`roiblum/feat-ecosystem-day1-day2`). `apps/day1-service/src/wingman_day1`
replaces the legacy `src/`: values file from the shared template in a
sandbox, naming rules, read-only sites/MCEs with default `mastertag` and hub
version, `ClusterProvisioner` (MR today), approvals on core `Approvals`
with the reviewed head, hub/OAuth/day2 over httpx behind ports (ADRs
0012-0019). Run locally: `WINGMAN_ENVIRONMENT=development
WINGMAN_GIT_BACKEND=fake JWT_SECRET_KEY=<32+ chars>
DAY1_GITLAB_PROJECT_ID=gitops-day1/platform-config
SPECS_GITLAB_PROJECT_ID=wingman/cluster-specs DEV_AUTH_ENABLED=true
DEV_AUTH_SECRET=<32+ chars> uv run uvicorn wingman_day1.main:app --port 8001`;
against local GitLab: `uv run python scripts/dev/day1_live_e2e.py --token
<local token> --sandbox-chart <chart dir>`. **Next:** the web changes in
`docs/notes/2026-11-07-day1-api-changes.md` and the chart's day1 env.
**Open:** the off-convention MCE rule (ADR-0014) waits on team question 3;
the default `clusterName` rule (ADR-0015) on question 2.

**2026-11-07 — the `wingman-core` foundation.** Branch
`roiblum/feat-ecosystem-day1-day2`. Shipped the core package (ADRs
0001-0010), CI and the gate, local GitLab scripts and the seeded fixtures.
**Next:** rewrite day1 on the core against `gitops-day1/platform-config`
(values file from the new template, naming rules, read-only sites/MCEs, read
`mastertag`/nodepools/VLAN, status names, MR branches that CI commits to), and
in parallel day2 against the gitops-day2 layout (four cluster kinds, defaults
and exclusions, the 10-layer values merge, version pins). **Open:**
production vs sandbox `clusterName`, canonical site codes and InfraEnv naming
(questions in `docs/ecosystem/README.md`).

**2026-11-07 — ecosystem map, the new day1 template, the UI refresh.**
`docs/ecosystem/` maps server-scan, segments-manager, the Temporal workflows,
herzi, the hostedclusters-setup chart, gitops-day2 and kubevirt-workflows,
and how Wingman fits them. The new `cluster-template.j2` renders the slim
values file and was checked with `helm template` against both chart copies.
Earlier the same day: the dark-first UI refresh (PR #16) and the legacy
Playwright specs fixed.

## Status as CLAUDE.md listed it until 2026-11-17

CLAUDE.md's "Current status" before it was shortened; the features since are in
README.md's feature table and the entries above.

- Done: ecosystem map (`docs/ecosystem/`); the new day1 template
  (`dev/gitlab-fixtures/wingman/cluster-specs/cluster-template.j2`, verified
  with `helm template` against both chart copies); fixtures; the
  `wingman-core` foundation (GitLab port, httpx adapter, in-memory fake,
  contract suite passing 30/30 on the fake and on GitLab CE 19.5.3, RFC 9457
  errors, metrics, settings, auth, cache, approvals); CI and
  `scripts/gate.sh`; ADRs 0001-0011; monitoring in the chart (ServiceMonitor,
  7 promtool-tested alerts with a runbook, a Grafana dashboard, all off by
  default) with a test tying alerts and dashboard to the metric catalogue.
- Done: day1 rewritten on `wingman-core` as `wingman_day1`
  (`apps/day1-service/src/wingman_day1`, ADRs 0012-0019), checked end to end
  against local GitLab with `scripts/dev/day1_live_e2e.py` and through both
  chart copies. Web-visible API changes:
  `docs/notes/2026-11-07-day1-api-changes.md`.
- Done: day2 rewritten as `wingman_day2` (four destination kinds, fleet
  defaults and exclusions, the platform's value stacks with provenance,
  lints, one MR per team; ADRs 0020-0024), held to the team's
  `render_chain.py` by an oracle test and run against GitLab CE 19.5.3.
  Web-visible API changes: `docs/notes/2026-11-07-day2-api-changes.md`.
- Done: CI's supply chain and releases (ADR-0030, ADR-0031, ADR-0032):
  hash-pinned per-service exports, the web image from the root lock, build on
  every PR, every merge to main a release versioned from its commits, a
  blocking npm audit, a nightly live-GitLab run.
- Done: both service images install only from the hash-pinned exports
  (`docs/ops/images.md`); the chart sets exactly the variables the services
  read (`tests/repo/test_chart_env_contract.py`) and probes
  `/health/live`/`/health/ready`.
- Done (2026-11-08): the web on both new APIs (shared dropdown, searchable
  combobox, empty, loading and error states); the whole stack checked live
  against the seeded local GitLab; report-only version drift (ADR-0025); the
  legacy `wingman-shared` removed; the delete dialog ready for the
  delete-cluster workflow (ADR-0033); OpenShift versions per MCE from the
  day1 repo's upgrade ladder; `docs/ideas/`, `docs/upgrade/`.
- Done (2026-11-08): the day1, specs and team repos are read once per commit
  from GitLab's archive (ADR-0035); the catalog on a production-sized repo went
  from 9 s and 357 GitLab calls per load to 0.03 s cached, 0.46 s after the TTL.
- Done (2026-11-08): flavors v2 (`docs/ideas/flavors-v2.md`, ADRs 0026-0029,
  0036, 0037): enforced locks, machine configs from `mc-files/` with nodepool
  defaults, numeric owners, drift on locked values, importing existing
  clusters into a flavor and syncing a cluster to it; the web pages for all of
  it; the UI says Flavor (the API keeps `/specs`).
- Done (2026-11-11): the cluster page's Nodes tab by NodePool from the MCE
  (missing pieces, the node an update works on), joined to server-scan, and
  node uninstall through the platform's workflow (ADR-0038); 3.3.1 reads
  network templates by the CI's name.
- Done (2026-11-12): the cluster's EPG from segments-manager, checked
  against the file's VLAN and segment (ADR-0039).
- Done (2026-11-12): create from a flavor with a nodepool ratio, a suggested
  name and one-letter sequences (ADR-0040).
- Done (2026-11-12): reads answer from cache while one fetch refreshes them;
  a merge re-reads only the files it changed (ADR-0041, `docs/ops/performance.md`).
- Done (2026-11-12): create can start the `provision-cluster` workflow,
  off by default (ADR-0042).
- Done (2026-11-14): chart hardening: nginx stays the one entry point, on
  UBI nginx by digest (ADR-0058); every pod restricted with a read-only root;
  `values.schema.json` and no default image tag (ADR-0059).
- Done (2026-11-16): tuning profiles per nodepool from the day1 repo's
  `tuning/` (ADR-0061); the Grafana dashboard's activity and external-systems
  rows (3.36.0).
- Done (2026-11-16): scaling NodePools through the platform's update-nodepool
  workflow, off by default; while on, it alone changes an existing
  NodePool's replicas (ADR-0062).
- **Not done yet, in order:** (1) the architect's
  answers (`docs/ideas/architecture-fit.md`); (2) flavors v2's "Left for
  later"; (3) ecosystem features (`docs/ideas/`).
