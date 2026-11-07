# Wingman today — precise map (as of branch roiblum/feat-web-modern-ui, HEAD 47b0e02)

Repo: /Users/roiblum/Downloads/scripts/wingman. Paths below are relative to it.
Last real feature work: May 2026 (PR #1 infraenv dropdown merged ~2026-05-22). Nov 2026 commits are UI-theme + e2e only.

Architecture in one line: Next.js UI → nginx → two FastAPI services (day1, day2) → GitLab (only state store, no DB).
Wingman never talks to ArgoCD; ArgoCD (configured outside this repo) watches the GitLab repos and applies merged changes.
The only non-GitLab runtime integrations are OpenShift OAuth (login) and, optionally, MCE kube-APIs (live status + InfraEnv list).

---------------------------------------------------------------------------------------------------
## 1. Day1 — cluster provisioning

### 1.1 Repos / where things live
Two GitLab projects (both accessed with ONE token `GITLAB_ACCESS_TOKEN`):
- **Day1 project** (`DAY1_GITLAB_PROJECT_ID`, e.g. `wingman-dev/day1-config`): cluster files.
  Path template `DAY1_CLUSTERS_PATH_TEMPLATE="sites/{site}/mces/{mce}/hostedClusters"` (apps/day1-service/src/config.py:42),
  file = `{dir}/{cluster}.yaml` (packages/shared-python/src/wingman_shared/path_resolver.py:42-44).
  → **`sites/{site}/mces/{mce}/hostedClusters/{cluster}.yaml`** (one file per cluster, multi-doc or values-style YAML — whatever the template renders).
  NB: README.md:337-346 shows an outdated layout (`mces/{mce}/{cluster}.yaml`, specs in same repo) — wrong; code is authoritative.
- **Specs project** (`SPECS_GITLAB_PROJECT_ID`, e.g. `wingman-dev/cluster-specs`):
  - `specs/{spec}.yaml` (`SPECS_ROOT_PATH="specs"`, config.py:47; path_resolver.py:92-94)
  - `cluster-template.j2` at repo ROOT — single shared Jinja2 template for ALL specs, hard-coded name (path_resolver.py:100-103)
  - `openshift-versions.txt` at repo root, hard-coded (spec_service.py:296-307), one version per line, `#` comments allowed
  - legacy `specs/{spec}.j2` per-spec templates — deleted on spec update/delete (spec_service.py:216-219, 266-269)
- Neither `cluster-template.j2` nor `openshift-versions.txt` are in this code repo; scripts/seed-test-data.py seeds an OLD format (per-spec inline templates, `.wingman.yaml` sidecars) that the current code no longer reads.

### 1.2 What a "spec" is (schema)
Pydantic `ClusterSpec` (packages/shared-python/src/wingman_shared/models.py:24-79):
```yaml
apiVersion: wingman.io/v1
kind: ClusterSpec
metadata: {name, description, version: "1.0.0", labels: {}}
spec:
  day1:
    variables: []          # legacy SpecVariable list (name,type,required,default,pattern,enum,min,max) — new UI sends []
    structure: {}          # "shape" tree: list counts + empty leaves, e.g. {nodepool: [{}, {}]}
    immutable_paths: []    # dot/bracket paths flagged "immutable after create" (UI hint only, not enforced)
    template: ""           # ALWAYS stripped on write; injected from cluster-template.j2 on read (spec_service.py:88-97,132-138)
  day2:
    addons:
      - {team, name, version, overrideable: [{path, type, default, description}]}
```
- Spec "version" is just a string in metadata; there is no multi-version storage — only latest in Git (+ git history: `/specs/{name}/history`, `/specs/{name}/at/{sha}`).
- Create-cluster requires `spec_version == current spec version` else 400 (routers/clusters.py:296-300).
- Spec CRUD: POST `/api/day1/specs`, PUT `/api/day1/specs/{name}`, DELETE `/api/day1/specs/{name}` → each opens an MR in the specs project (spec_service.py:123-292). Labels `["wingman","specs",create|update|delete]`.
- Spec form (web): apps/web/app/(app)/specs/new/page.tsx:432-451 `buildFinalSpec()` – `variables: []`, `structure` (identity vars stripped), `immutable_paths`, `day2.addons` from a marketplace picker; per-addon "overrideable" fields chosen in components/specs/configure-overrideable-dialog.tsx using chart+team values (`/api/day2/addons/{team}/{addon}/values?version=`).

### 1.3 Template schema endpoint (cluster-template.j2 → dynamic form)
- `GET /api/day1/specs/template` → raw template text (routers/specs.py:46-52).
- `GET /api/day1/specs/template/schema[?include_reserved=true]` (routers/specs.py:55-67 → spec_service.py:311-325 → services/template_analyzer.py:324-355).
  The analyzer walks the Jinja2 AST:
  - `{{ var }}` → required string; `{{ var | default(x) }}` → optional with default; `default([])`/`default({})` → list/object.
  - `{% for item in list_var %}` → `list_var` is a list; `item.field` → sub-fields (list-of-objects); nested `for x in item.sub` supported.
  - `# Example: foo` comment on a line before `{{ … }}` → `example` hint (template_analyzer.py:278-310).
  - Output: `[{name, type: string|list|object, required, default?, example?, fields?[]}]` (types integer/boolean are never inferred).
  - Excludes `IDENTITY_VARS = {cluster_name, site_name, site, mce_name, mce}` and `RESERVED_VARS = +{openshift_release_version}` unless include_reserved (template_analyzer.py:313-321).
- The template’s output per docs (apps/web/app/(app)/docs/page.tsx:599-659) is a **values-style file** (`clusterName`, `platform: agent`, `hostInventory`, `masterTag`, `nodepool: [{name, replicas, labels{min/maxReplicas}, nodeLabels, agentLabelSelector{nodeLabelKey: infraenvs.agent-install.openshift.io, nodeLabelValue}, configs[], tuningConfig, workerTag}]`, `mcFiles: […]`) — i.e. input for some downstream HostedCluster Helm chart/ArgoCD app, not raw CRs. Docs line 276 calls Day1 repo "cluster manifests (AgentCluster, NodePool, MachineConfig)". The seed data instead renders raw `HostedCluster`/`NodePool` CRs with `platform.type: Agent`. Either way: **agent-based HyperShift hosted clusters**.

### 1.4 Create-cluster flow end-to-end
UI: apps/web/app/(app)/clusters/new/page.tsx (admin-only, L507-515). Two steps:
1. **Pick spec** (`GET /api/day1/specs`, L371-375). On select (L517-544): seed the dynamic form from `spec.day1.structure` × template schema (`seedFromStructure`, components/clusters/dynamic-variable-form.tsx:45-70 — list counts locked by spec, leaves blank); initialise addon override fields from spec addon `overrideable` defaults.
2. **Configure**:
   - Identity: Cluster name (free text), **Site** dropdown (`GET /api/day1/sites`), **MCE** dropdown (`GET /api/day1/sites/{site}/mces`), each with "Create new…" which immediately opens a separate MR (`POST /api/day1/sites`, `POST /api/day1/sites/{site}/mces`, L453-470). Site/MCE auto-detected by substring match against the cluster name, longest match wins (L419-451).
   - **OpenShift version**: dropdown from `GET /api/day1/specs/versions/openshift` (openshift-versions.txt) or free text if empty (L784-809).
   - **Cluster Configuration**: `DynamicVariableForm` over the template schema minus identity vars (L813-832). Field named exactly `infra_env` (top level only) becomes a dropdown from `GET /api/day1/mces/{mce}/infraenvs` (L411-417; dynamic-variable-form.tsx:489-513); falls back to text input on 501/error/empty. Nested fields (e.g. per-nodepool infra env) do NOT get the dropdown (only top-level FieldEditor gets options, dynamic-variable-form.tsx:579-589 vs 308).
   - **Addon Configuration**: per spec addon, form for its overrideable fields or "Full Values" YAML (L834-988).
   - Validation: required template fields non-empty (L552-561).
3. **Review**: `POST /api/day1/clusters/preview` renders exactly what will be committed (routers/clusters.py:260-283); dialog lists target files: `sites/{site}/mces/{mce}/hostedClusters/{name}.yaml` and the Day2 files "created when addons are deployed" (L1097-1131).
4. **Confirm**: `POST /api/day1/clusters` with `{name, site, mce, spec_name, spec_version, variables}` (L472-481) where `variables = {...dynamicValues, openshift_release_version, cluster_name, site_name, site, mce_name, mce}` (L497-505).
   **Addon overrides are NOT sent** (and `CreateClusterRequest.addon_overrides`, routers/clusters.py:49, is ignored server-side). Spec addons are NOT installed at create time; they show up later as "addon drift: missing" and are installed via "Fix" buttons on the cluster page (clusters/[name]/page.tsx:236-286) with `override_values: {}`.

Backend (routers/clusters.py:286-318 → services/cluster_service.py:228-310):
- load spec (+ shared template), check version, `apply_variable_defaults` (from legacy `variables` list only), `render_spec` = Jinja2 `StrictUndefined`, trim/lstrip blocks, numeric-string coercion (services/yaml_renderer.py:22-80). Validation `_validate_variables` only checks the legacy `variables` list (effectively a no-op for new specs).
- 409 if file exists (`file_exists`, sync call).
- Prepend metadata comments `# specName: "<spec>"\n# specVersion: "<ver>"` (cluster_service.py:56-58, 265). **These comments are the ONLY cluster→spec link** (no `.wingman.yaml` any more; `_get_cluster_metadata` L158-194 reads the comments + last commit author/date).
- One commit (action `create`) on new branch, then MR:
  - branch `platform/{user}/create-cluster-{name}-{YYYYMMDDTHHMMSS}` (mr_conventions.py:57-72)
  - title `[Wingman/Day1] Create cluster {name} from spec {spec}`
  - description human text + machine footer `---\nAuthor:\nAction:\nResource: cluster/{name}\nRepo: Day1`
  - labels `["wingman","day1","create"]`, `remove_source_branch: True`, target = default branch
  - commit author_name = username, author_email `{username}@openshift.local` (gitlab_client.py:166-169); commit message lists ALL variables (cluster_service.py:278-282).
- Returns `MRDetail`; UI toasts and routes to /clusters. Cluster then appears in list (list is a recursive tree scan, so it only appears after merge to main).

Cluster listing: recursive `repository_tree` of whole Day1 repo, filter blobs containing `/hostedClusters/` ending `.yaml` not `.wingman.yaml`; site = path[1], mce = path[3] (cluster_service.py:92-156). Per cluster an extra file read + `get_commit` → N+1 to GitLab, cached 30s. `phase` always "Unknown" here.

### 1.5 Edit / delete / sync
- **Edit**: raw YAML editor on cluster detail page → `PATCH /api/day1/clusters/{name}?site=&mce=` `{updated_yaml, change_summary}` (clusters/[name]/page.tsx:309-322; routers/clusters.py:321-337; cluster_service.py:314-374). Optimistic lock via `last_commit_id`. Branch `…/modify-cluster-{name}-…`, title `[Wingman/Day1] Modify cluster {name}`, labels `wingman,day1,modify`. No re-render, no immutability enforcement (immutable_paths are not checked; `cluster-edit` form mode exists in dynamic-variable-form.tsx but no page uses it).
- **Delete**: `DELETE /api/day1/clusters/{name}?site=&mce=` → MR deleting the single YAML (cluster_service.py:378-434). Day2 override dirs for that cluster are NOT removed.
- **Sync to spec**: `POST /api/day1/clusters/{name}/sync-yaml` re-renders using `metadata.variables` (routers/clusters.py:356-387). Since metadata now comes only from comments, `variables` is always `{}` → render fails (StrictUndefined) → 422 for any template with required vars. Effectively broken.
- Sites/MCEs: create = MR adding `sites/{site}/.gitkeep` or `sites/{site}/mces/{mce}/hostedClusters/.gitkeep` (cluster_service.py:491-566), titles `[Wingman/Day1] Create site|mce …`.

### 1.6 MCE list, sites, InfraEnv dropdown (PR #1)
- **Sites** = sub-directories of `sites/` in Day1 repo (`list_sites`, cluster_service.py:461-474; hard-coded "sites", ignores the path template).
- **MCEs** = sub-directories of `sites/{site}/mces` (cluster_service.py:476-489). No global MCE registry; an MCE "exists" iff a folder exists.
- **InfraEnvs** (PR #1, commits 6535c83/e391c90/2f4772f): `GET /api/day1/mces/{mce}/infraenvs` (routers/mces.py:17-33) → `ClusterStatusService.list_infraenvs` (services/cluster_status_service.py:273-309): kube CustomObjects list of `agent-install.openshift.io/v1beta1 infraenvs` on the MCE hub, namespaced (`MCE_INFRAENV_NAMESPACE`) or cluster-wide; returns sorted **names only** (no filtering by site/cluster/free agents). 501 when `CLUSTER_STATUS_ENABLED=false`; 422 if no token for MCE; 502 on API error.

### 1.7 Cluster status (live) and drift
Live status (only if `CLUSTER_STATUS_ENABLED=true`; `ClusterStatusServiceDep` → 501 otherwise; dependencies.py:197-232):
- Tokens: YAML file `MCE_TOKENS_FILE` (default `/etc/wingman/mce-tokens/tokens`, mounted from secret `clusterStatus.tokensSecretName`, chart/templates/day1-deployment.yaml:52-83), format `{mce-name: SA-token}`, loaded once.
- API server: `https://api.{mce}.{MCE_API_DOMAIN}:6443` (cluster_status_service.py:127-129) → MCE folder name must equal the hub’s DNS label and token key.
- Reads `hypershift.openshift.io/v1beta1` HostedCluster `{cluster_name}` in ns `hcp-{cluster_name minus MCE_CLUSTER_NAME_PREFIX("ocp4-")}` plus all NodePools in that ns (L97-103, 181-253). Health = conditions: HC `Available` must be True, `Degraded`/`Progressing` must not be True; NP `Ready` True, `UpdatingVersion`/`UpdatingConfig` not True; replicas spec vs status. Returns `ClusterLiveStatus{hc_phase, ocp_version (status.version.history[0]), hc_problems, node_pools[], error}`.
- Endpoints: `GET /clusters/{name}/status?mce=`, `POST /clusters/bulk-status`, SSE `GET /clusters/{name}/status/stream?mce=` polling every 30s (routers/clusters.py:135-222). Sync kubernetes client in `asyncio.to_thread`.
- UI: cluster list bulk-status every 2 min (clusters/page.tsx:149-166), detail page query + SSE (clusters/[name]/page.tsx:114-210), dashboard does per-cluster N+1 status calls (app/(app)/page.tsx:100).

Drift (Git-only, no live data; services/drift_detector.py):
- YAML drift: re-render spec with `metadata.variables` and diff normalized YAML vs committed file (L104-206). Because variables are never stored now, render fails → treated as NOT drifted (L144-161). So YAML drift is effectively dead; only addon drift works.
- Addon drift: each spec addon must be installed (by name) at spec version (L67-102). Installed list fetched by calling Day2 `GET {DAY2_SERVICE_URL}/api/day2/clusters/{name}/addons?mce=` forwarding the user’s Authorization header (routers/clusters.py:87-101, 415-436).
- `GET /clusters/drift-summary` (all clusters, cached 60s, used by list + dashboard), `GET /clusters/{name}/drift`, `GET /specs/{name}/clusters` (uses drift-summary cache if warm), `GET /specs/{name}/drift` (reads `.wingman.yaml` sidecars that no longer exist → always empty, drift_detector.py:222-229).

### 1.8 Approvals (Day1 + Specs)
services/approval_service.py (day1) + routers/approvals.py:
- `GET /api/day1/approvals` = all open MRs targeting "main" (hard-coded default in gitlab_client.py:289, not GITLAB_DEFAULT_BRANCH) in Day1 + Specs projects, no label filter, cached 120s as `approvals:combined:list`.
- `GET /approvals/{iid}?repo=day1|specs` → MR + file diffs; `PUT /approvals/{iid}?repo=` pushes edited file contents onto the MR branch (`commit_to_branch`); `POST /approve` = check **approver != author** (author = `Author:` line in MR description, fallback GitLab author), state must be opened, then `approve()` (failure ignored) + `merge()` with the service token; `POST /reject` = close MR.
- There is no N-approvals rule, no GitLab approval-rule integration (service token is both author and approver at GitLab level), no CODEOWNERS/per-team approver mapping. Any admin may approve anything not authored by themselves.
- Bug: cluster/spec writes invalidate `approvals:day1:list` (cluster_service.py:308 etc.) but the real key is `approvals:combined:list` → new MRs appear only after TTL/stale refresh. Webhook MR handler invalidates prefix `approvals:day1` → same miss (webhooks.py:107-109).

---------------------------------------------------------------------------------------------------
## 2. Day2 — addons

### 2.1 Catalog source (`DAY2_SIGS_GROUP_PATH`)
- `DAY2_SIGS_GROUP_PATH` (e.g. `wingman-dev/sigs`) is a GitLab **group**; every **project in it is a "team"** (gitlab_client.py:597-662; `list_project_paths` = `group.projects.list`, non-recursive). Per-team client = project `{group}/{team}` (L652-662).
- Inside each team project (apps/day2-service/src/config.py:35-37, path_resolver.py:53-81):
  - `operators/{addon}/` — one dir per addon (`DAY2_ADDON_DEFS_PATH_TEMPLATE="operators/{addon}"`)
    - `operators/{addon}/values.yaml` — team default values; top-level `dependencies:` key is popped out as the addon’s dependency list (addon_service.py:136-142)
    - `operators/{addon}/{addon}.yaml` — "ArgoCD metadata" `AddonArgoMetadata{projectNamespace, repourl, targetRevision(default main), syncPolicy}` (models.py:212-220)
  - `mces/{mce}/{cluster}/{addon}/` — per-cluster install (`DAY2_ADDON_OVERRIDES_PATH_TEMPLATE="mces/{mce}/{cluster}/{addon}"`)
    - `values.yaml` — cluster override values (layer 3)
    - `{addon}.yaml` — metadata override, normally only `targetRevision` if it differs from team default
- **Versions** = git **branches** of the Helm chart repo pointed to by `repourl` (must be a project on the SAME GitLab; path derived by stripping GITLAB_URL, helm_values_fetcher.py:21-39), excluding `master, HEAD, develop, dev`; "main" first then reverse-sorted (L70-98). **Chart default values** = `values.yaml` at repo root on that branch (L100-126). No Helm repo/OCI/chart index support.
- `current_version` = team `targetRevision` or first branch or "main" (addon_service.py:154-162).
- `AddonCatalogEntry{team, name, available_versions, current_version, default_values, argocd_metadata, dependencies}`. Dependencies are displayed but not enforced anywhere.
- Three-layer merge with provenance: chart < team < cluster, dicts deep-merge, lists replaced, `null` deletes key (yaml_utils.py:210-298; addon_service.py:370-424).

### 2.2 Installed addons per cluster
- "Installed" == directory `mces/{mce}/{cluster}/{addon}` exists in any team project (addon_service.py:251-352). Cluster identity in Day2 = **(mce, cluster)** — no site. Version = override `{addon}.yaml` `targetRevision` or "" (NB: empty means team default, but drift compares "" vs spec version → shows version_mismatch).
- Response shape `{cluster, mce, installed: [{team, name, version, override_values, parse_errors?, gitlab_url?}]}`.
- Who turns these dirs into ArgoCD Applications is outside Wingman (an ApplicationSet/git generator presumably in the team repos or a central argo config). Nothing in Wingman creates `Application` CRs.

### 2.3 Writes / MR conventions (addon_service.py)
| Op | Endpoint | Files | Branch | Title | Labels |
|---|---|---|---|---|---|
| install | `POST /api/day2/clusters/{name}/addons/{team}/{addon}?mce=` `{version, override_values}` | create values.yaml + {addon}.yaml (targetRevision only if ≠ team default) | `platform/{u}/install-{addon}-{cluster}-{ts}` | `[Wingman/Day2] Install addon {team}/{addon} v{ver} on {cluster}` | wingman,day2,install |
| bulk | `POST …/addons/bulk?mce=` `{addons:[{team,addon,version,override_values}], custom_message}` | create/update per addon; **single team only** (400 otherwise; UI loops per team) | `…/bulk-install-{n}-addons-{cluster}-{ts}` | `[Day2] Install … on {cluster}` (**breaks** the `[Wingman/…]` convention, L617-620) | wingman,day2,bulk-install |
| update | `PUT …/addons/{team}/{addon}?mce=` | update/create values.yaml; create/update/delete {addon}.yaml | `…/update-{addon}-{cluster}-{ts}` | `[Wingman/Day2] Update addon {team}/{addon} to v{ver} on {cluster}` | wingman,day2,update |
| remove | `DELETE …/addons/{team}/{addon}?mce=` | delete both files | `…/remove-{addon}-{cluster}-{ts}` | `[Wingman/Day2] Remove addon {team}/{addon} from {cluster}` | wingman,day2,remove |
All commits go to the team’s project; MR in that project. Values editing UI: apps/web/app/(app)/clusters/[name]/addons/page.tsx (2313 lines; install L1127-1141, bulk L1660-1675, merged values `GET /clusters/{name}/addons/{team}/{addon}?mce=&version=`, merge-preview `POST /api/day2/merge-preview`). Spec "overrideable" fields are NOT used on this page (any key editable).

### 2.4 Day2 approvals / audit
- `GET /api/day2/approvals` = open MRs from every team project (apps/day2-service/src/services/approval_service.py:62-77).
- `GET|PUT /approvals/{iid}`, `POST /approve|reject`: MR located by **IID only**, searching team projects in order (L46-60). IIDs are per-project → **collisions across teams** (team A !5 vs team B !5) → may act on the wrong MR. Same approve logic as Day1.
- Audit: commits/MRs (label `wingman`) across all team projects; commit diff searches all team projects for SHA.
- Day2 has no webhook receiver; cache only via TTL + write-through.

---------------------------------------------------------------------------------------------------
## 3. Shared package (packages/shared-python/src/wingman_shared)
- **gitlab_client.py** — python-gitlab wrapper; sync methods + `a*` `asyncio.to_thread` wrappers (L450-568). File read returns `(content, last_commit_id)`; atomic multi-file commit to new branch with `start_branch` (L134-185); MR create/get/list/diff/approve/merge/close; tree listing; branches; commits via raw `http_get` (older GitLab compat, L389-420). `GitLabGroupClient` (L597-662) for team projects. Many services still call the sync variants on the event loop (create/modify/delete cluster, all day2 writes, all approvals) despite CLAUDE.md rule.
- **cache.py** — in-process dict cache, stale-while-revalidate + per-key lock, crude LRU (max 1000) (L40-172). Per-pod; no shared cache → replicas >1 diverge. Both services pre-warm in a background loop (day1 main.py:40-90, day2 main.py:38-100).
- **mr_conventions.py** — branch `platform/{user}/{action}-{resource}-{ts}` (L57-72), title `[Wingman/{Day1|Day2|Specs}] {Verb} {type} {name}{extra}` (L78-96), description footer `Author/Action/Resource/Repo` (L102-121), `parse_mr_description` (L136-158) used to recover the real user (GitLab author is the service token) in `parse_mr_to_detail` (L189-235). `parse_mr_title` (L169-183) is defined but **unused**. The "audit service" does NOT parse conventions: it lists commits + `wingman`-labelled MRs and shows raw GitLab author (`extract_platform_author=False`). Conventions are consumed only for (a) display author in approvals and (b) the self-approval check.
- **auth/** — `openshift_oauth.py`: discovers endpoints from `https://{OPENSHIFT_API_HOST}/.well-known/oauth-authorization-server` (fallback `https://{OPENSHIFT_OAUTH_HOST}/oauth/authorize|token`), scope `user:info`, code exchange, `GET /apis/user.openshift.io/v1/users/~` for username/groups/uid/fullName (L61-167). `jwt.py`: HS256, payload `{sub, groups, uid, role, iat, exp}`, default 8h (L27-60). `rbac.py`: admin if in any `WINGMAN_ADMIN_GROUPS`, else viewer if in `WINGMAN_VIEWER_GROUPS`, else login denied (L29-55). `middleware.py:make_auth_dependency` is unused (each service re-implements `get_current_user` in dependencies.py). Role is frozen into the JWT until expiry.
- Auth endpoints live in day1 only: `GET /api/auth/config`, `POST /api/auth/callback {code}`, `GET /api/auth/me`, `POST /api/auth/dev-login` (routers/auth.py). Redirect URI = `https://{route.host}/login` (chart/_helpers.tpl:62-70); the web /login page posts the code (apps/web/app/login/page.tsx:40-60). JWT stored in a **non-httpOnly** cookie `wingman-token` (lib/api-client.ts:15-29) + zustand localStorage; any 401 → redirect /login.
- **yaml_utils.py** — ruamel round-trip, multi-doc parse with structured errors, deep merge/provenance.
- **path_resolver.py** — the env-templated path builder (but see §6: several callers bypass it).
- **models.py** — all DTOs.

---------------------------------------------------------------------------------------------------
## 4. External systems & config
| System | Used by | How | Config |
|---|---|---|---|
| GitLab (single instance, single token) | day1, day2 | REST via python-gitlab | `GITLAB_URL`, `GITLAB_ACCESS_TOKEN` (secret), `GITLAB_DEFAULT_BRANCH`, `GITLAB_SSL_VERIFY` |
| ↳ Day1 project | day1 | clusters, sites/MCEs | `DAY1_GITLAB_PROJECT_ID`, `DAY1_CLUSTERS_PATH_TEMPLATE`, `DAY1_CLUSTER_FILE_SUFFIX` |
| ↳ Specs project | day1 | specs, cluster-template.j2, openshift-versions.txt | `SPECS_GITLAB_PROJECT_ID`, `SPECS_ROOT_PATH` |
| ↳ SIGs group (team projects) | day2 | addon defs + per-cluster installs | `DAY2_SIGS_GROUP_PATH`, `DAY2_ADDON_DEFS_PATH_TEMPLATE`, `DAY2_ADDON_OVERRIDES_PATH_TEMPLATE` |
| ↳ Helm chart repos (GitLab projects referenced by `repourl`) | day2 | branches = versions, values.yaml | (derived from addon metadata) |
| ↳ GitLab webhooks → Wingman | day1 only | `POST /api/webhooks/gitlab` cache invalidation | `GITLAB_WEBHOOK_SECRET` |
| OpenShift OAuth + API (management cluster) | day1 | login, user/groups | `OPENSHIFT_OAUTH_HOST`, `OPENSHIFT_API_HOST`, `OPENSHIFT_OAUTH_CLIENT_ID`, `OPENSHIFT_OAUTH_CLIENT_SECRET`, `OPENSHIFT_OAUTH_REDIRECT_URI`, `OPENSHIFT_SSL_VERIFY`; chart creates `OAuthClient` CR (chart/templates/oauth-client.yaml) |
| MCE hub kube-APIs (one per MCE) | day1 (optional) | HostedCluster/NodePool status, InfraEnv list | `CLUSTER_STATUS_ENABLED`, `MCE_API_DOMAIN`, `MCE_TOKENS_FILE`, `MCE_CLUSTER_NAME_PREFIX`, `MCE_SSL_VERIFY`, `MCE_INFRAENV_NAMESPACE`; secret `mce-sa-tokens` |
| Day2 service (from day1) | day1 | drift addon list | `DAY2_SERVICE_URL` (default `http://wingman-day2:8002`) |
| ArgoCD | — | **no direct integration**; consumes Git | none |
Other env: `JWT_SECRET_KEY` (both, must match), `JWT_EXPIRY_HOURS`, `WINGMAN_ADMIN_GROUPS`, `WINGMAN_VIEWER_GROUPS` (both), `DEV_AUTH_ENABLED`, `DEV_AUTH_SECRET` (day1; UI dev-login never sends the secret, so it only works with an empty secret), `SERVICE_PORT`, `LOG_LEVEL`, `CACHE_*` (many day1 CACHE_* TTLs and `CACHE_ADDON_VALUES_TTL` are **unused** — TTLs are hard-coded in services; `DAY1_SERVICE_URL` in configmap unused), `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` (when `tls.caBundle`).
Deployment: chart/ = nginx (8080; routes `/api/auth/`, `/api/day1/`, `/api/webhooks/` → day1; `/api/day2/` → day2; `/` → web; chart/templates/nginx-configmap.yaml:57-83), day1, day2, web (Next standalone), OpenShift Route or Ingress, configmap/secret, SA (no RBAC bindings — Wingman doesn’t use in-cluster kube API).

---------------------------------------------------------------------------------------------------
## 5. API surface → web pages
Day1 (`/api/day1`, apps/day1-service/src/routers):
- clusters: `GET /clusters` | `GET /clusters/drift-summary` | `POST /clusters/bulk-status` | `GET /clusters/{n}/status?mce` | `GET /clusters/{n}/status/stream?mce` (SSE) | `GET /clusters/{n}/history?site&mce` | `GET /clusters/{n}/current-yaml?site&mce` | `GET /clusters/{n}?site&mce` | `POST /clusters/preview` | `POST /clusters` | `PATCH /clusters/{n}?site&mce` | `DELETE /clusters/{n}?site&mce` | `POST /clusters/{n}/sync-yaml?site&mce` | `GET /clusters/{n}/drift?site&mce`
- sites: `GET /sites` | `GET /sites/{s}/mces` | `POST /sites` | `POST /sites/{s}/mces`
- mces: `GET /mces/{mce}/infraenvs`
- specs: `GET /specs` | `GET /specs/versions/openshift` | `GET /specs/template` | `GET /specs/template/schema` | `GET /specs/{n}/history` | `GET /specs/{n}/at/{sha}` | `GET /specs/{n}` | `POST /specs` | `PUT /specs/{n}` | `DELETE /specs/{n}` | `GET /specs/{n}/clusters` | `GET /specs/{n}/drift`
- approvals: `GET /approvals` | `GET /approvals/{iid}?repo` | `PUT /approvals/{iid}?repo` | `POST /approvals/{iid}/approve?repo` | `POST /approvals/{iid}/reject?repo`
- audit: `GET /audit/commits` | `GET /audit/merge-requests` | `GET /audit/commits/{repo}/{sha}/diff`
- misc: `GET /cache/stats`, `GET /healthz`; `/api/auth/{config,callback,me,dev-login}`; `POST /api/webhooks/gitlab`
(README’s API table is partly stale: e.g. it lists `POST/PUT /clusters/{name}`, `/sync`, `/audit/mrs`.)
Day2 (`/api/day2`): `GET /gitlab-info` | `GET /addons[?team]` | `GET /addons/{t}/{a}` | `GET /addons/{t}/{a}/versions` | `GET /addons/{t}/{a}/values?version` | `GET /clusters/{n}/history?mce` | `GET /clusters/{n}/addons?mce[&team]` | `GET /clusters/{n}/addons/{t}/{a}?mce[&version]` | `POST /clusters/{n}/addons/{t}/{a}?mce` | `POST /clusters/{n}/addons/bulk?mce` | `PUT /clusters/{n}/addons/{t}/{a}?mce` | `DELETE /clusters/{n}/addons/{t}/{a}?mce` | `POST /merge-preview` | approvals (same 5 as day1, no `repo`) | audit (`/audit/commits`, `/audit/merge-requests`, `/audit/commits/{sha}/diff`) | `/cache/stats`.

Pages (apps/web/app/(app)/…):
- `/` dashboard: day1 clusters, specs, day1+day2 approvals, per-cluster status (N+1), drift-summary.
- `/clusters`: clusters, bulk-status, drift-summary; hover prefetch of detail/drift/day2 addons/catalog.
- `/clusters/new`: specs, template/schema, day2 addons catalog, sites, sites/{s}/mces, specs/versions/openshift, mces/{mce}/infraenvs, POST sites, POST sites/{s}/mces, POST clusters/preview, POST clusters.
- `/clusters/[name]`: cluster detail, status + SSE stream, current-yaml, drift, day2 cluster addons + catalog, day1 + day2 history, PATCH/DELETE cluster, sync-yaml, day2 POST/PUT addon (drift "fix").
- `/clusters/[name]/addons`: day1 clusters (to resolve mce/site), day2 cluster addons, catalog, gitlab-info, merged values, addon values at version, install/bulk/update/remove.
- `/specs`: specs. `/specs/new`: day2 addons, template, template/schema?include_reserved, addon values at version, POST specs. `/specs/[name]`: spec, clusters, drift, history, at/{sha}, DELETE. `/specs/[name]/edit`: spec, addons, schema, values, PUT spec.
- `/addons`: day2 addons catalog (read-only browse).
- `/approvals`: day1 + day2 approvals. `/approvals/[id]` (`id = day1-123|specs-123|day2-123`): get/approve/reject/PUT edit.
- `/audit`: day1+day2 commits & MRs, commit diffs; MR expand calls `/api/{repo}/approvals/{iid}` without `repo` → 422 for day1 (bug).
- `/docs` static guide, `/settings` local prefs, `/login`.

---------------------------------------------------------------------------------------------------
## 6. Hard-coded infrastructure model (what breaks if servers/segments/InfraEnvs come from other systems and provisioning = Temporal + Helm chart)
1. **Hierarchy site → MCE → cluster encoded as Git folder names**, partly bypassing the "configurable" template: tree scan requires `/hostedClusters/` and takes site=parts[1], mce=parts[3] (cluster_service.py:102-111,135-142); `list_sites` hard-codes `sites`, `list_mces` hard-codes `sites/{site}/mces` (L466,481); site/MCE creation writes `.gitkeep`s at fixed paths (L493,531-533); webhook comment assumes same (webhooks.py:119-127); UI hard-codes the path in the review dialog (clusters/new/page.tsx:1104) and Day2 paths (L1120-1124). Sites/MCEs have no data beyond their name.
2. **Cluster identity = name (+site/mce query params)**; some caches keyed by name only (`day1:clusters:detail:{name}`, cluster_service.py:221) → same name in two MCEs collides. Day2 identity = (mce, cluster) — no site.
3. **Spec↔cluster link = `# specName/# specVersion` comment header** in the cluster file (cluster_service.py:37-58). No stored variables → no re-render, no YAML drift, no "edit values" UI.
4. **One shared Jinja2 template** `cluster-template.j2` at specs repo root (path_resolver.py:100-103) + `openshift-versions.txt` (spec_service.py:299). Form is derived from Jinja AST, not from a JSON schema / Helm values.schema.json.
5. **Magic variable names**: `cluster_name`, `site`/`site_name`, `mce`/`mce_name`, `openshift_release_version` (template_analyzer.py:314-321; clusters/new/page.tsx:338-340, 497-505; specs/new/page.tsx:274-276) and `infra_env` (dynamic-variable-form.tsx:490). Legacy `worker_count` in MR description (cluster_service.py:271).
6. **HyperShift + Agent platform**: HostedCluster/NodePool `hypershift.openshift.io/v1beta1`, InfraEnv `agent-install.openshift.io/v1beta1` (cluster_status_service.py:24-31); HC ns `hcp-{name without "ocp4-"}` (L97-103); hub API URL `https://api.{mce}.{domain}:6443` (L127-129); per-MCE long-lived SA tokens in a YAML file; condition semantics (L33-41). Template/docs assume `platform: agent`, nodepool `agentLabelSelector` on label `infraenvs.agent-install.openshift.io`, `mcFiles`/MachineConfig names (docs/page.tsx:561-658).
7. **InfraEnv list = raw CR names from the hub**, not tied to servers/segments; user picks one manually; nothing validates host count vs replicas, segment, or site. Herzi-filled InfraEnvs would show up, but Wingman has no idea which servers/segments they represent.
8. **No server, network segment, IP, VLAN, BMC or inventory concept anywhere** in Day1 (only free-text template fields). Network-ish data appears only as free-form Helm values (seed metallb `networkSegments`, seed-test-data.py:629-642).
9. **Provisioning = "merge YAML to Git, ArgoCD applies"**. No workflow engine, no async job/status object, no callbacks; "status" is only read from HostedCluster conditions. Delete = remove file (relies on ArgoCD prune). Create doesn’t install spec addons; delete doesn’t remove Day2 dirs.
10. **Day2 model**: team = GitLab project in one group; addon = `operators/{addon}/{values.yaml,{addon}.yaml}`; install = `mces/{mce}/{cluster}/{addon}/`; versions = branches of a chart repo on the same GitLab; chart defaults = root `values.yaml` on that branch; ArgoCD metadata fields `projectNamespace/repourl/targetRevision/syncPolicy`.
11. **GitLab-specific approvals**: target branch "main" hard-coded in `list_open_mrs` (gitlab_client.py:289); single service token merges; self-approval check via description footer.
12. **OpenShift-only auth**: OAuthClient CR, `users/~` API, groups → roles.

---------------------------------------------------------------------------------------------------
## 7. Assessment: reusable vs coupled
**Generic / reusable (keep, maybe extract):**
- UI shell & design system: app-shell, sidebar, user menu, providers, shadcn/@base-ui primitives, slate theme, review dialog, YAML diff viewer, GitLab file list, MR progress, `/docs` pattern. React Query + api-client pattern.
- Auth: OpenShift OAuth → app JWT → admin/viewer RBAC by group (wingman_shared/auth). Solid and generic for anything on OpenShift. Weak spots: non-httpOnly cookie, CORS `*` w/ credentials, role frozen in JWT.
- GitLab MR engine: `GitLabClient.commit_files` + `create_mr` + optimistic locking + branch/title/footer conventions (mr_conventions.py) + approve/reject/edit-MR flows + aggregated approvals page + diff viewer. Reusable as a "propose change → review → merge" engine for ANY GitOps repo (e.g. the reworked gitops-day2 repo or hosted-cluster Helm values). Needs: fix IID-collision in day2, fix cache-key mismatch, configurable target branch, real approval policy.
- Audit page (commits + wingman-labelled MRs across repos) — generic but shallow (no parsing of conventions, raw service-account authors).
- Cache (SWR in-memory) — fine for 1 replica; not for HA.
- Day2 value layering + provenance + values editor (chart < team < cluster) — generic Helm-values UX, reusable if the new gitops-day2 repo keeps a layered values model.
- Jinja-AST → form generator & structure/immutability spec builder — clever but tied to the Jinja approach; would be superseded by a values.schema.json-driven form for the new hosted-cluster Helm chart.

**Tightly coupled to the old model (rewrite/replace):**
- Day1 cluster model: folder-encoded site/MCE, single `.yaml` per cluster, comment-header spec link, shared `cluster-template.j2`, `openshift-versions.txt`, render-and-commit provisioning, drift-by-re-render (already broken), sync-yaml (broken), raw-YAML edit.
- Sites/MCE management via `.gitkeep` MRs (should come from an inventory/source of truth).
- ClusterStatusService: per-MCE SA token file, API URL convention, `hcp-`/`ocp4-` naming, direct kube calls — should be replaced by status from the orchestrator/Temporal workflow and/or herzi/hub controllers.
- InfraEnv dropdown: a direct hub query returning names; in the new world InfraEnvs are filled by herzi from server-scan/segments-manager data, so the form should select servers/segments (or a server pool) and let the workflow/herzi handle InfraEnvs.
- Day2 layout (`sigs` group, `operators/`, `mces/{mce}/{cluster}/{addon}`, branches-as-versions, chart repos on GitLab) — must be remapped to whatever the reworked gitops-day2 repo looks like.
- Day1↔Day2 coupling via HTTP drift calls and spec `day2.addons` (spec addons not auto-installed, overrides dropped at create).

**Known bugs worth knowing before reuse:** create drops addon overrides; sync-yaml/YAML drift/spec-drift dead (no stored variables, `.wingman.yaml` gone); immutable_paths unenforced; day2 MR IID collision across team projects; approvals cache key mismatch (`approvals:day1:list` vs `approvals:combined:list`); webhook metadata invalidation keys don’t match (`day1:clusters:metadata:{site}:{mce}:{cluster}` vs prefix `day1:clusters:metadata:{name}`); audit MR-expand 422 for day1; bulk-install MR title breaks convention; many sync GitLab calls on the event loop; CI pytest failures never fail CI and there are no Python tests; dev-login UI never sends DEV_AUTH_SECRET; many CACHE_* env vars unused.
