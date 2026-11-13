# segments-manager — notes for the Wingman modernization

Repo: `team-redbull/segments-manager` (team-redbull/segments-manager, HEAD `a4edc12`, 2026-10-11).
Live: `<sandbox URL, see CLAUDE.local.md>`
(probed with GET only on 2026-11-07; Swagger at `/docs`, schema at `/openapi.json`, title "Segments Manager API" 0.1.0).
Raw live captures: `a local scratch folder: live-sm/*.json`.

> `.planning/**` is STALE: it describes the NetBox/pynetbox + VRF era (March 2026). The current code is MongoDB,
> no NetBox, no VRF, no IPAM. Trust `CLAUDE.md`, `README.md`, `ARCHITECTURE.md` and `src/`.

---

## 1. Purpose / what it is the source of truth for

- A **per-site VLAN segment pool + allocation ledger**. Each record = one L2/L3 segment: `(site, vlan_id, epg_name, CIDR, dhcp)`,
  plus allocation state `(status, type, cluster_name, allocated_at)`. (`CLAUDE.md` §Project Overview, §MongoDB Data Model)
- Source of truth for: **which VLAN/CIDR segments exist at each site, and which cluster holds which one, as what type**.
- Also the authority on the **site list** (`GET /api/sites`), derived from the `SITE_NETWORKS` env JSON keys
  (`src/config/settings.py:80-347`). The workflows' allocate-segment cross-checks the day1 path's site against it.
- **NOT** a source of truth for: gateway, DNS, base domain, API/ingress VIPs, per-host IPs, MACs, DHCP ranges. None of those
  fields exist (grep of `src/` for gateway/vip/dns/base_domain finds only the CIDR-size validator
  `validate_network_broadcast_gateway`, which just checks ≥2 addresses — `src/utils/validators/network_validators.py`).
  No per-IP allocation at all — the unit is a whole segment (in practice a /24).

### Where data lives
- **MongoDB** via Motor (`src/database/mongo_client.py`, `mongo_segments.py`), DB `MONGODB_DB_NAME` (default `segments-manager`;
  the live sandbox log shows `segments_manager`), collection `MONGODB_COLLECTION` (default `segments`).
- Indexes (`src/database/mongo_storage.py:init_storage`): unique `{site, vlan_id}`, unique `{segment}`, `{cluster_name}`, `{site}`,
  `{site, status}`. Startup also runs one-time migrations (null `type` on non-Allocated, listify UPI `cluster_name`, drop `released*`).
- Site pools: `SITE_NETWORKS` env (ConfigMap), e.g. `{"site1":{"pool":"192.10.0.0/16","pool-exceptions":[...]}, ...}`.
  In prod it comes from the chart value `siteNetworks`, held in redbull-platform `defaults/hub/values.yaml` so that
  segments-manager and the segment-lifecycle-worker agree on the site list
  (`gitops-day2-prod/argocd-day2-platform/deploy/templates/deployApp.yaml:52-56`). **Pools are not exposed by the API** —
  only site names.
- 60 s in-memory cache of the whole collection (`src/database/cache.py`); `GET /api/segments?fresh=true` busts it.
- Chart: `team-redbull/redbull-platform` → `gitops/charts/segments-manager/values.yaml` (CI bumps it — `.github/workflows/build.yml`).
  Image built to GHCR by the org reusable workflow.

### How it's populated
- Segments are **pre-created by operators** (network team carves VLAN + CIDR + EPG), never invented by the service.
- Canonical path: operator → orchestrator `POST /workflows/segment-lifecycle/initialize-segment` (or `/bulk`) → Temporal workflow →
  `POST /api/segments` here as a retried activity (`workflows/README.md:31-36,144-162`; SM `CLAUDE.md:55`).
  Direct `POST /api/segments` / `/bulk` (CSV in the UI) still work.
- SM is the **validator of record**: site configured, CIDR strict + inside the site pool (or exact `pool-exceptions` match),
  mask /16–/31, no reserved ranges, no global overlap, VLAN unique per site, EPG unique per site.
- **No outbound calls** — talks to MongoDB only (`CLAUDE.md` §Key decisions #7). It used to POST
  `/workflows/segment-connectivity` to the workflows API on create (firewall flow); removed in `f8b6953` (2026-08-02).

---

## 2. Data model

`src/models/schemas.py`, `CLAUDE.md` §MongoDB Data Model.

| field | type | notes |
|---|---|---|
| `_id` | str (ObjectId) | internal; returned but never accepted |
| `site` | str | must be in `SITE_NETWORKS`; lookup case-insensitive |
| `vlan_id` | int 1–4094 | unique per site |
| `epg_name` | str ≤64, `[A-Za-z0-9_\-./]` | ACI EPG name; unique per site |
| `segment` | str CIDR | **the natural key** — globally unique, immutable. API addresses segments by it (`?segment=` / body) |
| `dhcp` | bool | default true; the ONLY editable field (`PATCH /api/segments`) |
| `status` | `"Available"` \| `"Allocated"` | two-state lifecycle; born Available (the old `Locked` state is gone) |
| `type` | `MCE`\|`INVENTORY`\|`HC`\|`PXE`\|`UPI`\|`HUB` \| null | **allocation state**, null ⇔ Available. Not set at creation (422 if sent) |
| `cluster_name` | str \| list[str] \| null | single string for every type, **a list for `UPI`** (shared segment) |
| `allocated_at` | datetime \| null | set on allocate; NOT cleared on release (live Available rows still carry it) |

Legacy extra keys may still appear on live docs (`segment_connectivity_requests`, `..._failure`, etc., all null) — tolerate unknown keys.

### Segment types (what each is for — from SM + workflows docs)
- **HC** — a hosted cluster's (HyperShift) node network. The one allocate-segment/release-segment workflows support today.
  The HC's VLAN → day1 `vlanId` + `dhcp_values.network` (DHCP scope on Windows DHCP via Crossplane).
- **MCE** — an MCE hub's own cluster network.
- **INVENTORY** — an MCE's inventory/provisioning network that BareMetalHosts boot into (NMStateConfig VLAN sub-interface on DHCP).
  One per MCE, looked up by `(cluster_name == <MCE name>, type=INVENTORY)` (`CLAUDE.md:198`; `workflows/README.md:341-347`;
  `kubevirt-workflows/docs/procedures/00-interfaces.md` §2).
- **PXE** — PXE network (PXE VM per site serves iPXE map).
- **HUB** — hub cluster network (added 2026-10-03, `32cc7b9`).
- **UPI** — a UPI (non-hosted, standalone OCP — e.g. seed clusters / customer MCEs installed UPI on KubeVirt/baremetal) network.
  **Only type that may be shared by several clusters**: `cluster_name` is a JSON list like `["ocp4-upi-a","ocp4-upi-b"]`.
  UPI allocations are mostly "entered by hand" via `PUT /api/segments/clusters` (list REPLACES the current list);
  `POST /allocate` with UPI always takes a FRESH segment and stores `[cluster_name]`, never joins an existing one;
  `POST /release {segment, cluster_name}` pulls one cluster, and the segment returns to Available when the list empties
  (`a4edc12`; `src/services/allocation_service.py:_release_cluster`; `src/database/mongo_segments.py:release_cluster`).
- No "kubevirt" type; KubeVirt hosted clusters use HC.

### Allocation semantics (`src/database/mongo_segments.py:allocate_segment`, `src/services/allocation_service.py`)
- One shared Available pool per site — type does NOT narrow the search. Atomic `find_one_and_update({site, status:Available})`
  sorted by **lowest `vlan_id`**, `$set {status:Allocated, type, cluster_name, allocated_at}`. Caller cannot pick which segment.
- **Idempotent per (cluster_name, site, type)**: a repeat returns the existing allocation. One cluster can hold one segment per type per site.
- Pool exhausted → **503** `No available segments for site: X`.
- Release keyed by CIDR only; Allocated→Available clears type + cluster; already-Available is 200 no-op. **No owner check**
  (workflows re-reads owner before release; an `expected_cluster_name` is a wished-for SM change — `workflows/CLAUDE.md:1101-1105`).
- Delete refuses an Allocated segment.

### Live example (trimmed, 2026-11-07)
```
GET /api/sites  -> {"sites":["site1","site2","site3"]}
GET /api/stats  -> [{"site":"site1","total_segments":20,"allocated":1,
                     "by_type":[{"type":"HC","allocated":0},{"type":"MCE","allocated":0},
                                {"type":"INVENTORY","allocated":1},{"type":"PXE","allocated":0},
                                {"type":"UPI","allocated":0},{"type":"HUB","allocated":0}]}, ...]
GET /api/segments?status=Allocated ->
  [{"_id":"6a9d93c703f08940d2766802","type":"INVENTORY","site":"site1","vlan_id":1011,
    "epg_name":"EPG_site1_MCE_11","segment":"192.10.11.0/24","dhcp":true,
    "cluster_name":"ocp4-mce-workflow-test","allocated_at":"2026-09-27T14:51:12.313000+00:00",
    "status":"Allocated"}]
an Available one ->
   {"_id":"6a9d93c703f08940d2766801","type":null,"site":"site1","vlan_id":1010,
    "epg_name":"EPG_site1_MCE_10","segment":"192.10.10.0/24","dhcp":true,
    "cluster_name":null,"allocated_at":"2026-09-26T12:36:17.869000+00:00","status":"Available"}
```
50 segments total: site1 20 (19 Available), site2 18, site3 12. All /24s. Pools (inferred from data, = `.env.example`):
site1 `192.10.0.0/16`, site2 `193.51.0.0/16`, site3 `194.52.0.0/16`. Sandbox VLANs 1010–1042, 3900–3921;
CIDR third octet = VLAN mod 100 (e.g. VLAN 1023 → x.x.23.0/24) — a sandbox seeding convention, not enforced.
EPG names `EPG_<site>_<LEGACYTYPE>_<n>` (the type in the name is from the old per-type pools; it no longer constrains allocation).

---

## 3. API surface (all under `/api`, `src/api/routes.py`; confirmed identical in live `/openapi.json`)

| method | path | use for a portal |
|---|---|---|
| GET | `/api/sites` | site dropdown (authoritative list) |
| GET | `/api/stats` | per-site `total_segments`, `allocated`, `by_type[]` (free = total − allocated) |
| GET | `/api/health` | also has per-site `{total, allocated, available, utilization}` |
| GET | `/api/segments?site=&status=Available\|Allocated&type=&fresh=` | **free segments per site**: `?site=X&status=Available`. **No `cluster_name` filter** — filter client-side, exact match, and handle list for UPI |
| GET | `/api/segments/search?q=&site=&status=` | substring match over cluster names, EPG, CIDR, exact VLAN |
| GET | `/api/segments/by-segment?segment=<cidr>` | one segment (404 if unknown) |
| GET | `/api/export/segments/{csv,excel}`, `/api/export/stats/csv` | exports |
| GET | `/api/logs?lines=N`, `/api/logs/info` | app log (open, unauthenticated) |
| POST | `/api/segments` | create (body `{site, vlan_id, epg_name, segment, dhcp}`; `type` → 422) *(auth)* |
| POST | `/api/segments/bulk` | bulk create, per-row errors *(auth)* |
| PATCH | `/api/segments` | `{segment, dhcp}` *(auth)* |
| PUT | `/api/segments/clusters` | manual assign `{segment, cluster_name, type}` (type required with a cluster; UPI list replaces); empty cluster releases *(auth)* |
| DELETE | `/api/segments?segment=` | delete (not if Allocated) *(auth)* |
| POST | `/api/segments/allocate` | `{cluster_name, site, type}` → `{vlan_id, cluster_name, site, type, segment, epg_name, allocated_at}`; 503 when pool empty *(auth)* |
| POST | `/api/segments/release` | `{segment, cluster_name?}` (cluster_name only for UPI, else 400) *(auth)* |

No reserve/hold step separate from allocate; no IP-level allocation; no VIP endpoints.

### Auth (`src/app.py:64-90`, `src/auth/auth.py`)
- GET/HEAD/OPTIONS open (UI needs no auth). Every POST/PUT/PATCH/DELETE under `/api/*` needs
  `Authorization: Bearer <API_TOKEN>` (single static shared token, constant-time compare, centrally enforced middleware, fail-closed).
  No users, roles, sessions, OIDC. CORS `*`.
- Token: `API_TOKEN` env (Secret). In workflows it is `SEGMENTS_MANAGER_API_TOKEN`, held **only** by the segment-lifecycle worker
  (`kubevirt-workflows/docs/procedures/00-interfaces.md:33`). No secret values seen in the repo (`.env.example` has `API_TOKEN=` empty;
  `.claude/settings.local.json` contains only `test-token` dev strings).

### How VIPs / base domain / DNS / gateway are decided (NOT here)
- **Gateway**: derived `.254` of the /24 by the hostedclusters-setup chart's DHCP template (`helm-charts-hostedclusters-setup/README.md:201-207`);
  range `.1–.253`, exclusions per type from the worker's `DHCP_EXCLUSION_OCTET_RANGES`
  (`workflows/activities/segment_lifecycle/dhcp_values.py`). Workflows enforce **/24 only**.
- **DNS servers, lease, failover**: day1 values layers `sites/configValues.yaml` (`dhcp_values.dns.servers`) + `sites/<site>/values.yaml`
  (`dns.extraServers`) (chart README §Values).
- **baseDomain**: chart value `baseDomain` (default `example.internal`; lab `""` → HyperShift derives from MCE apps domain).
- **API VIP / ingress**: HyperShift services — kube-apiserver is a LoadBalancer Service (MetalLB → AKO), Routes for ingress
  (chart `services` key; `segments-manager/script.sh` is a stray MetalLB→AKO endpoint-fix workaround). Nothing in SM.
- **Node IPs**: DHCP on the HC segment (Windows DHCP scope created by Crossplane `Request` from `dhcp_values`).

---

## 4. Role in creating a hosted cluster / UPI cluster; connections

### Hosted cluster (HC) — today's real flow
1. Human (→ Wingman) pushes a **temp branch** in the day1 values repo (`team-redbull/day1` GitHub / `gitops-day1/platform-config` GitLab)
   with `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml`.
2. The day1 repo's **GitLab CI pipeline** (non-main branches) calls orchestrator
   `POST /workflows/segment-lifecycle/allocate-segment` `{"cluster":"<file stem>","values_branch":"$CI_COMMIT_BRANCH","type":"HC"}`
   → 202 `{workflow_id:"allocate-segment-HC-<cluster>"}`; pipeline polls `GET /workflows/runs/{id}` until COMPLETED.
   (This replaced the day1 repo's old in-house VLAN allocator.) `workflows/CLAUDE.md:818-830`, `README.md:719-740`.
3. The workflow: finds exactly one `sites/<site>/**/<cluster>.yaml` on that branch (site = first path segment), checks site ∈ `GET /api/sites`,
   `POST /api/segments/allocate {cluster_name:<cluster>, site, type:"HC"}`, reads it back via `by-segment` (status/cluster/vlan/type),
   appends to the file and pushes `[skip ci]`:
   ```yaml
   # === Added By Segment-Allocation Workflow ===
   vlanId: 1023
   dhcp_values:
     network: "192.10.23.0"
     exclusions: [...]   # only if the type's policy defines any
   ```
   (`workflows/activities/segment_lifecycle/values_repo.py:76-100`). Pipeline then generates MachineConfig files from `vlanId`.
4. Human merges to main → Argo CD (`hcAppset`) renders hostedclusters-setup → DHCP scope `Request` (Crossplane → DHCP API),
   HostedCluster `openshift-<clusterName>` in `hcp-<clusterName>` (when `hostedCluster.enabled`), day2 registration Job.
5. Nodes come from herzi/add-server-to-mce (InfraEnv filled from server-scan); those hosts boot on the **MCE's INVENTORY** VLAN
   (looked up in SM by MCE name) before joining.
6. **Delete**: remove the values file on main → Application deleted → PostDelete hook Job `release-segment-<cluster>` POSTs
   `{"cluster","type":"HC"}` to `http://workflows-orchestrator-api.redbull-workflows.svc:8080` release-segment → deletes surviving DHCP scope,
   re-reads owner, `POST /api/segments/release {segment}`, verifies Available.
   (`helm-charts-hostedclusters-setup/templates/release-segment-hook.yaml`, README §Releasing.)

Planned (design-only): `create-hosted-cluster` workflow (`kubevirt-workflows/docs/procedures/03-create-hosted-cluster.md`):
validate → allocate HC segment at hub's site → verify → compose HC + NodePools → commit on `values_branch` → human merge → wait CP.
Delete: `05-delete-hosted-cluster.md`. Version-band migration allocates a NEW segment at the target hub's site (`18-...`).

### UPI cluster
- No workflow allocates UPI today (allocate-segment is HC-only; other types → `UnsupportedSegmentType`).
  UPI segments are set by hand via `PUT /api/segments/clusters {segment, type:"UPI", cluster_name:[...]}`; several UPI clusters may share one.
  Consumer named in SM docs: **cluster-navigator** (compares `cluster_name` list to its own name) — not in the eco clones.
  gitops-day2-prod has a UPI values branch (`defaults/upi/<operator>/...`), seed/customer-MCE procedures install UPI.

### Connections (grep results)
- **workflows** (only real API client): `activities/segment_lifecycle/activities.py` — create (`POST /api/segments`, then `by-segment` for idempotency),
  `GET /api/sites`, `POST /allocate`, `GET by-segment` read-back, `GET /api/segments?type=INVENTORY` + client-side cluster match (add-server-to-mce
  `resolving-vlan`, publish-infraenv-to-pxe-server `resolving-site`), `GET /api/segments?status=Allocated&type=HC&fresh=true` + exact cluster match,
  `POST /release`. Env `SEGMENTS_MANAGER_URL` (global `workflows-orchestrator-config`, e.g.
  `http://segments-manager.segments-manager.svc.cluster.local:8000`), `SEGMENTS_MANAGER_API_TOKEN` (Secret).
- **herzi**: no direct call; it starts add-server-to-mce and checks pollers on the `segment-lifecycle-activity` queue (runs hang at `resolving-vlan`
  if that worker is down) — `herzi/internal/config/defaults.go:16`, `herzi/docs/design/herzi-design.md:488,713`.
- **server-scan**: no reference.
- **helm-charts-hostedclusters-setup**: no direct call; consumes the allocation indirectly via `dhcp_values.network`/`vlanId` in the day1 file,
  and its PostDelete hook triggers release-segment.
- **gitops-day2-prod**: only the shared `siteNetworks` hub value comment.

---

## 5. Concepts / naming Wingman must adopt

- **Site** = the key in `SITE_NETWORKS` = `GET /api/sites` = the `<site>` path segment in day1 (`sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml`)
  = the `<site>` token in MCE names. Lowercase tokens (`site1`, prod e.g. `bat-yam`). Wingman must not invent sites; a site without a
  `SITE_NETWORKS` entry is unusable (allocate 400). Wingman's "create site via MR" should be gated on / replaced by the SM site list.
- **Cluster name** in SM = the day1 values **file stem** (allocate-segment passes it). Conventionally `ocp4-`-prefixed:
  HC examples `ocp4-prep-herzi-site1-a`; MCE `ocp4-<env>-mce-<site>-<letter>` (`workflows/shared/cluster_names.py`; callers may drop `ocp4-`,
  workflows canonicalize); seed `ocp4-seed-<site>-<zone>`; KubeVirt `ocp4-kubevirt-<site>-<zone>…`; UPI e.g. `ocp4-upi-a`.
  SM validator: `[A-Za-z0-9_.-]`, ≤100 chars. Name is load-bearing (INVENTORY VLAN lookup, queues, release).
  ⚠ Verify: the chart derives `clusterName` = file's own `clusterName` key else stem minus `ocp4-` (HC `openshift-<clusterName>` in
  `hcp-<clusterName>`), and the release hook posts `.Values.clusterName` — check it equals the SM `cluster_name` (file stem) or release finds nothing.
- **Segment identity** = CIDR. Segment = VLAN + EPG + /24. Types: HC / MCE / INVENTORY / PXE / HUB / UPI. Type is assigned at allocation.
- Segments are **/24 only** for anything that flows through workflows/DHCP.
- Sandbox EPG convention `EPG_<site>_<TYPE>_<n>` (informational).

---

## 6. Integration points for Wingman

### READ (direct, public GETs, no token)
- *Wingman reads (2026-11-13)*: `by-segment` for the cluster page's EPG (ADR-0039), and `GET /api/sites`, `/api/stats` and
  `/api/segments` (`fresh=true` for Refresh) for its Segments area (ADR-0047). Still no writes.
- `GET /api/sites` → site dropdown / validation (replace Wingman's GitLab-folder-derived site list as the authority, or intersect them).
- `GET /api/stats` (or `/api/health` `sites_summary`) → "N free segments at site X" badge; block cluster creation when 0 free (HC pool empty → allocate 503).
- `GET /api/segments?site=X&status=Available` → optional free-segment list (display only; allocation picks lowest VLAN, you can't choose).
- `GET /api/segments?status=Allocated` (+ `fresh=true` for post-action refresh) → per-cluster network view: VLAN, CIDR, EPG, type; match `cluster_name`
  client-side exactly; treat list for UPI. One cheap call for the whole cluster list (avoid N+1 — SM has no cluster filter).
- MCE view: the MCE's INVENTORY segment (`type=INVENTORY`, `cluster_name==<mce>`) — show "inventory VLAN missing" as a readiness gate for adding servers.
- Cache with Wingman's `cache.get_or_fetch` ~30–60 s (SM itself caches 60 s).
- **Linking to it**: the UI reads no URL parameters (its `static/js/app.js`, read on the live sandbox with GET only,
  2026-11-11). No route or query opens one cluster's or one segment's row; its search box filters client-side over
  cluster names, EPG, CIDR and VLAN. A link can only open the UI and name what to search for; for one cluster's segment
  as JSON, `GET /api/segments/search?q=<file stem>`. Wingman's cluster page does both (`SEGMENTS_MANAGER_UI_URL`,
  `docs/notes/2026-11-11-cluster-nodes-api.md` §5).

### CALL (order during HC creation) — prefer the orchestrator, not SM writes
Wingman should **not** hold the SM token or call `POST /api/segments/allocate` itself; the ecosystem routes every SM write through
Temporal workflows (durable retry, read-back verification, values-file write, DHCP coupling).
1. Pre-flight: `GET /api/sites` (site valid), `GET /api/stats` (free > 0), name not already holding an HC segment.
2. Write `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml` on a new branch + MR (Wingman already does this; layout already matches).
   Do **not** write `vlanId`/`dhcp_values.network` yourself — the marker block is the workflow's; a foreign top-level `vlanId`/`dhcp_values` makes it refuse.
3. Allocation: either (a) let the day1 repo's CI pipeline call allocate-segment on that branch (current production shape — Wingman just watches
   the pipeline / the MR), or (b) Wingman calls orchestrator `POST /workflows/segment-lifecycle/allocate-segment {cluster, values_branch, type:"HC"}`
   and polls `GET /workflows/runs/{id}` (note the orchestrator API has no auth; 409 = already running). Don't do both — the pipeline would also run
   unless the branch/commit skips CI.
4. Show the result (vlan_id, segment, epg) from the run result or `GET /api/segments`; then the human merges (Wingman's approval flow).
5. Delete: delete the values file via MR; release is automatic (PostDelete hook → release-segment). Wingman should only display
   the segment returning to Available; optionally offer a "retry release" calling orchestrator `release-segment {cluster}` if the hook Job failed.
- New segments (network team onboarding): orchestrator `initialize-segment` / `/bulk`, not `POST /api/segments`.
- UPI: no workflow yet; manual `PUT /api/segments/clusters` with the token — keep out of Wingman unless an admin-only feature is wanted.

### What it replaces in Wingman
- Any VLAN/CIDR/network fields Wingman specs ask the user to type → replaced by the SM allocation (auto, lowest free VLAN at the site).
- Site list authority (Wingman's `GET /api/day1/sites` reads GitLab folders; `POST /api/day1/sites` creates folders) → `SITE_NETWORKS`/`/api/sites`.
- Network-related validation (overlap, pool containment, VLAN uniqueness) → SM is validator of record.
- Teardown network cleanup → release-segment workflow (via chart hook).
- It does NOT replace: gateway/DNS/baseDomain/VIP decisions (day1 values layers + hostedclusters-setup chart), MCE/InfraEnv listing (herzi/MCE),
  servers (server-scan).

### Gaps / gotchas
- No cluster filter, no owner check on release, no pool exposure, no per-IP data, no auth roles (single static token).
- `allocated_at` stays set after release; legacy `segment_connectivity_*` keys on some docs.
- 503 means "pool empty at site"; 422 on any extra field (`extra="forbid"`) — e.g. sending `type` on create.
- Site lookup is case-insensitive in SM, but day1 paths / workflows are case-sensitive — always use the exact spelling from `/api/sites`.
