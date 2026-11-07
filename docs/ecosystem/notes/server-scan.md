# server-scan — notes for the Wingman modernization

Repo: `scratchpad/eco/server-scan` (read-only clone, `team-redbull/server-scan`, last commit f140914).
All paths below are relative to that repo unless they start with `apps/` (= Wingman).
Live: `<sandbox URL, see CLAUDE.local.md>` (probed with GET only).

---

## 1. Purpose, source of truth, where data lives, how it gets in

**What it is.** An air-gapped bare-metal server inventory for about 2,500 servers (planned up to 5,000)
across Dell, Cisco, HPE and "standalone" Redfish machines, in several sites (`README.md`, `CLAUDE.md`
"What this is"). It collects what every hardware manager reports, classifies each server by its hostname,
scores its health, tracks whether an OpenShift cluster or MCE is using it, and serves all of this through a
REST API and an admin UI.

**Source of truth for:**
- **Physical servers**: identity (vendor + serial), BMC address, NICs/MACs, hardware, health, site.
- **Whether a server is free or in use**: `openshift.lifecycle_state`, as the clusters report it.
- **Maintenance and the install lock (reservation)**: both are operator- or caller-set sub-documents.
- **Sites**: the `INVENTORY_SITES` catalog, projected into a `sites` collection.
- The audit trail of every change.

**Storage.** MongoDB is the only source of truth (ADR-0001). Redis is a cache-aside layer, and every read
falls back to Mongo. No Git repo and no CRs. Collections include `servers`, `sites`, `managers`,
`membership_runs`, `classification_rules`, `health_policies`, `events` and `api_tokens`. Every datetime is
stored as an ISO string (ADR-0006).

**How data gets in (three writers, each owning its own part of the document):**
1. **Vendor collectors.** One Kubernetes CronJob per manager type, `tools/run_collector.py --manager-type X`,
   on the schedule `0 */3 * * *` (every 3 h) in `deploy/helm/server-scan/values.yaml`. The manager types
   are `UCS_CENTRAL` (with `UCS_MANAGER` per domain), `INTERSIGHT`, `OPENMANAGE` (Dell OME plus iDRAC
   Redfish), `ONEVIEW` (HPE) and `REDFISH_STANDALONE` (one BMC at a time, from TOML inventory files).
   Each run classifies, scores health, writes audit events and upserts with a revision CAS (ADR-0044).
   Only hosts whose name matches `INVENTORY_COLLECTOR_NAME_PATTERN=^ocp` are ingested
   (`.env.example:232`).
2. **`nodes-status` membership jobs** (`deploy/helm/nodes-status`). One Helm release per OpenShift cluster,
   deployed by ArgoCD. These jobs run every 5 minutes inside each cluster and write
   `Server.openshift` and nothing else, **directly to MongoDB** (they never call the API).
   - `openshift-nodes` runs on every cluster. It lists `Node`s and writes `INSTALLED` with
     `cluster_name=<clusterName>`.
   - `openshift-agents` runs on MCE hubs only. It lists `agent-install.openshift.io` `Agent`s. An Agent with
     `spec.clusterDeploymentName.name` set is written as `INSTALLED` with that cluster name and
     `mce_name`. An unbound Agent is written as `INSTALLED_TO_INVENTORY` with `mce_name` only
     (`backend/app/infrastructure/openshift/records.py::agent_observation`).
   - Correlation is by hostname: `spec.hostname`, else `status.inventory.hostname`, lowercased and with the
     domain stripped. It falls back to the hardware serial (from the Agent's inventory, or SSH for nodes)
     when the name is not a unique match (ADR-0024, ADR-0036).
   - Each job reconciles only the servers that already name its own cluster or MCE. A server is freed
     (set back to `AVAILABLE`) when it is no longer seen. A failed or empty read writes nothing.
   - `excludeNameParts` defaults to `infra,control-plane,master`.
   - BareMetalHosts are deliberately not read.
3. **API writes** (admin only): maintenance, reservation, reclassify and health recalculation. In addition,
   `GET /servers/available` writes back what its live recheck finds (`IngestService.ingest_one`).

Freshness:
- Hardware is refreshed about every 3 h.
- Membership is refreshed every 5 min.
- `stale` = not seen by any collector for 12 h (`INVENTORY_STALE_AFTER_SECONDS=43200`).

---

## 2. Data model

Main model: `backend/app/domain/models/server.py` (`Server`), plus `openshift.py`, `reservation.py`,
`maintenance.py`, `network.py`, `hardware.py`, `health.py` and `classification.py`. The enums are in
`backend/app/domain/enums/core.py`.

| Field | Meaning |
|---|---|
| `id` (`_id`) | `srv_<32 hex>`, server-scan's own stable id. **Use this as the key, not `name`.** |
| `name` | The hostname as the manager reports it. **Not unique**: ADR-0032 measured 548 duplicate names among 2,500 documents, so `?name=` can return 409 `AVAILABLE_SERVER_NAME_AMBIGUOUS`. |
| `identity` | `vendor` (dell/cisco/hp/standalone), `serial`, `serial_normalized`, `system_uuid`, `nic_macs[]`, and `external_ids{manager_id: id}`. Correlation key: `(vendor, serial_normalized)`. |
| `model`, `profile_template{name, external_id}` | The hardware model and the vendor profile/SPT template. |
| `hardware` | `cpu{sockets, cores, threads, model}`, `memory{total_bytes, modules[]}`, `storage{total_bytes, drives[], controllers[], raid{state}}`, `gpus[]`, `power.psus[]`. |
| `network.bmc` | `address_raw` (e.g. `ipmi://10.12.2.118:623`), `scheme`, `host`, `host_is_ip`, `port`, `mac`. |
| `network.interfaces[]` | `name`, `mac`, `speed_mbps`, `link_state` (UP/DOWN/UNKNOWN/DISABLED), `location`. The detail view also has `nic_os_names{hw_name: os_name}` from `INVENTORY_NIC_OS_NAMES`. |
| `site_id` | A lowercase site code, or null ("Unassigned"). The site comes from the BMC IP prefix first, then the hostname token, then the Cisco org DN (ADR-0057). `site_from_bmc` and `site_from_name` keep both answers, and a disagreement between them is a CRITICAL `name.site_conflict` health reason. |
| `classification.installation_type` | `UPI`, `HOSTED_CLUSTER`, `MCE` or `UNCLASSIFIED`. This is a regex verdict on the name (what the machine was *named* to be), plus the matched rule, pattern and field. |
| `openshift` (`OpenShiftLifecycle`) | `lifecycle_state` (`AVAILABLE`, `INSTALLED` or `INSTALLED_TO_INVENTORY`), `cluster_name`, `mce_name`, `last_reported_at`, `reported_by_agent_id`, `reported_name`, `agent_uid`, plus the contested-claim fields (`previous_reporter`, `claim_changed_at`, `contested_with`, `contested_name`; ADR-0041). Cluster names are unique across the estate, including across MCEs. |
| `health` | `overall` plus one severity per category: memory, storage, raid, network, connectivity, power, gpu, bmc, name. Values are `HEALTHY`, `WARNING`, `MAJOR`, `CRITICAL` or `UNKNOWN`; also `reasons[]` and `active_policy_keys[]`. **`UNKNOWN` is not a verdict** (ADR-0027). An unreachable BMC makes the server `CRITICAL`. |
| `maintenance` | `enabled`, `reason` (a reason of "donor" means a parts donor, ADR-0038), `created_by`, `created_at`, `expected_end`. |
| `reservation` | The install lock: `holder`, `mce_cluster`, `infra_env`, `namespace`, `workflow_id`, `created_at`, `expires_at` (ADR-0035). |
| `reachable`, `unreachable_since`, `unreachable_reason` | Reachability of the BMC. |
| `last_seen_at`, `stale`, `unread_fields[]` | Freshness. `None` means "not read this run", and the stored value is carried forward. |
| `source_provider`, `manager_id` | Which collector found the server (`UCS_CENTRAL`, `INTERSIGHT`, `OPENMANAGE`, `ONEVIEW` or `REDFISH_STANDALONE`). |
| `tags[]`, `search_tokens[]` | `tags` exists but is empty in practice. **There is no free-form label map, no rack/row/position field and no "role" field** beyond `installation_type`. |

There is no rack or location data. Location is the site only.

### Real example from the live API (trimmed; the live data is a seeded fake fleet, see §8)

`GET /api/v1/servers/rows` item:
```json
{"id":"srv_d226c05c968244e19f68e4aa8f16bad3","name":"ocp-cisco-m6-bat-yam-128c-128gb-CIS0000630",
 "vendor":"cisco","model":"UCS C220 M6","site_id":"bat-yam","source_provider":"INTERSIGHT",
 "installation_type":"HOSTED_CLUSTER","health":"UNKNOWN",
 "maintenance":{"enabled":false,"reason":null,"created_by":null},
 "reservation":{"held":false,"holder":null,"mce_cluster":null,"infra_env":null,"expires_at":null},
 "openshift_state":"INSTALLED","cluster_name":"hc-bat-yam-03","mce_name":"mce-bat-yam",
 "openshift_reported_name":null,"contested_with":null,"profile_template_name":"UCS-X-Standard",
 "last_seen_at":"2026-11-07T13:00:03.650631Z","stale":false,"reachable":true,
 "serial":"CIS0000630","bmc_host":"10.12.2.118","macs":["37:7a:0e:ef:de:0b","d8:5c:20:00:7b:10"]}
```
`GET /api/v1/servers/{id}` for the same server adds:
- `identity.system_uuid` and `external_ids{"mgr_intersight":"intersight/0000…276"}`
- `hardware.cpu` (2 sockets, 32 cores, 64 threads, Xeon Gold 6348)
- `network.bmc` (`address_raw: ipmi://10.12.2.118:623`, port 623)
- `interfaces` `eth0` and `eth1`, with `nic_os_names` `eno5` and `eno6`
- `openshift` (`reported_by_agent_id: mce-bat-yam`, `agent_uid`)
- `classification` (matched `system-default-hardware-hosted-cluster`, pattern `^ocp-`)
- `unread_fields` (`hardware.memory.modules`, …), `revision` 108

A real reservation event from the live audit trail (written by the workflows team's test, 2026-09-26):
```json
{"event_type":"SERVER_RESERVED","server_name":"ocp4-hypershift-data-nyc-92",
 "data":{"holder":"install-server","mce_cluster":"ocp4-mce-workflow-test",
         "infra_env":"hp-gen11-nyc-64c-128gb","workflow_id":"install-server-hp-gen11-nyc-64c-128gb",
         "expires_at":"2026-09-27T01:45:35+00:00"}}
```

---

## 3. API surface relevant to a provisioning portal

The OpenAPI document is at `/openapi.json` and the interactive docs at `/docs`. The best human-readable
reference is `.claude/skills/server-scan-api/SKILL.md` together with `references/endpoints.md`. Errors are
RFC 9457 `application/problem+json` documents with a stable `code`. For example, the live API answered
`?bogus=1` with `{"code":"UNKNOWN_FILTER","details":{"allowed":[…]}}`.

### Reads

| Endpoint | Use for Wingman |
|---|---|
| `GET /api/v1/sites` | `{items:[{site_id, name, total, by_vendor, by_health, in_maintenance, by_installation_type, by_openshift_state}], fleet}`. **This is the site list for dropdowns.** |
| `GET /api/v1/servers` | Keyset-paginated list. Filters (exact set, AND-combined): `site_id`, `vendor`, `manager_id`, `installation_type`, `health_overall`, `maintenance`, `source_provider`, `openshift_state`, `cluster_name`, `stale`. Also `search` (word-boundary token search over name/serial/model; `"exact"` and `/regex/` forms per ADR-0046), `sort` (`name`, `serial`, `model`, `updated_at`, `last_seen_at`, `openshift_state`, `cluster_name`, `mce_name`), `sort_desc`, `page_size` (≤200), `cursor`, `with_count`. **There is no `mce_name` filter.** For that, use `/servers/rows` and filter on the client. |
| `GET /api/v1/servers/rows` | The whole fleet as flat rows (about 238 KB gzipped for 3,008 servers on the live instance), with a weak ETag so `If-None-Match` gets a 304. The server-scan UI polls it every 30 s. Best source for MCE, cluster and capacity rollups. |
| `GET /api/v1/servers/{id}` | Full detail. |
| `GET /api/v1/servers/{id}/events`, `GET /api/v1/events` | Audit trail. **Auditor or admin only**; a viewer gets 403. |
| `GET /api/v1/classification-rules`, `/health-policies`, `/health-metrics` | The rules the platform applies (read-only). |
| `GET /health/live`, `/health/ready` | Probes, no auth. |

### Availability and the free pool

- **"Free"** means `openshift_state=AVAILABLE`: no cluster's nodes job and no MCE's agents job claims the
  server.
- **`INSTALLED_TO_INVENTORY`** means the server is an unbound Agent in some MCE's InfraEnv. That is the
  pool a hosted cluster binds from. The live sandbox currently has none.
- Quick browse: `GET /servers?site_id=tlv&openshift_state=AVAILABLE&installation_type=HOSTED_CLUSTER&health_overall=HEALTHY`.
- **`GET /api/v1/servers/available`** returns live-verified, assignable servers for creating a BMH. It is
  the endpoint the `install-server` workflow uses (ADR-0032).
  - Params: exactly one of `name` (exact) or `pattern` (Mongo regex on the name); `count` (≤20, pattern
    mode only); `vendor`; `source_provider`; `health` (HEALTHY, WARNING or MAJOR); `min_nic_macs`.
  - It ranks candidates in Mongo, then **live-queries the vendor manager** for the few it returns and
    **writes the result back**. So it is a GET with side effects. It also has no concurrency cap yet
    (`CLAUDE.md`, "NOT done yet"): a caller that retries in a loop can exhaust a vendor manager's session
    limit.
  - Assignable means all of: `AVAILABLE`, not in maintenance, reachable, `health.network == HEALTHY`,
    overall not CRITICAL or UNKNOWN, and no live reservation
    (`backend/app/application/services/available_servers.py:219`, `:482`).
  - Item fields: `id`, `name`, `vendor`, `source_provider`, `bmc_vendor` (HP, DELL, CISCO or INTERSIGHT),
    `bmc{host, scheme, port…}`, `nic_macs[]`, `interfaces[{name, mac, location, os_name, link_state,
    speed_mbps}]`, `site_id`, `health_overall`, `live_recheck_performed`. No credentials are returned.
  - Error codes: 404 `AVAILABLE_SERVER_NOT_FOUND` (with `details.reasons` such as `INSTALLED`, `CLAIMED`,
    `MAINTENANCE`, `UNREACHABLE`, `RESERVED`, `HEALTH`, `NETWORK`), 409 for an ambiguous name, 503 when a
    vendor manager fails.
  - The capacity alias `INVENTORY_CAPACITY_ALIASES="5tb:hypershift(?!-data),10tb:hypershift-data"` makes
    `pattern=5tb` also match servers named `ocp4-hypershift-*`.
  - **I did not call it on the live instance**, because of the side effects.

### Reservation (assignment) — admin only

- `POST /api/v1/servers/{id}/reservation` with body
  `{holder, mce_cluster (required), infra_env?, namespace?, workflow_id?, ttl_seconds (300..86400, default 7200)}`.
  It returns `ServerDetail`, or 409 when someone else holds the server.
  - Mutual exclusion is a revision compare-and-set. A repeat claim with the same `workflow_id` extends the
    existing lock, so Temporal retries are safe.
  - `backend/app/api/v1/reservation_schemas.py`, `backend/app/application/services/reservation_service.py`.
- `DELETE /api/v1/servers/{id}/reservation` with body `{holder?, workflow_id?}`.
  - Releasing a server that is not held succeeds.
  - A release with no holder is the operator override.
  - An expired lock stays on the document as a record, and the rows show it as `held:false`.
- The reservation is the **only** link server-scan stores between a server and an InfraEnv or namespace.
  After the install, the link is `openshift.mce_name` (an Agent exists) and then `openshift.cluster_name`
  (the Agent is bound to a hosted cluster's ClusterDeployment).
- Server-scan **does not create** InfraEnvs, BMHs, NMStateConfigs, BMC Secrets or clusters. It holds no BMC
  credentials.

### Other writes (admin only)

`PUT` and `DELETE /servers/{id}/maintenance`, `POST /servers/{id}/reclassify`,
`POST /servers/{id}/health/recalculate`, and `/api/v1/jobs` (run a collector CronJob; admin only even for
GETs).

### Auth model (ADR-0034, ADR-0043, ADR-0053; `backend/app/dependencies.py::get_current_actor`)

- `INVENTORY_AUTH_ENABLED` is **false by default**, which admits every caller as the `dev` ADMIN. **The
  live sandbox runs that way**: `/api/v1/auth/me` returns
  `{"login_required":false,"username":"dev","role":"ADMIN"}`.
- With auth on, humans sign in with **LDAP / Active Directory**. `POST /api/v1/auth/login` sets a
  stateless session cookie with an 8 h TTL, and there is a login throttle.
  - Roles come from the AD group lists or user lists `INVENTORY_ADMIN_*`, `INVENTORY_AUDITOR_*` and
    `INVENTORY_VIEW_*`.
  - **There is no OpenShift OAuth and no OIDC.** This differs from Wingman, whose roles come from
    OpenShift groups.
- **Machine callers** send `Authorization: Bearer <token>` with one of three **static shared tokens**,
  `INVENTORY_API_TOKEN_ADMIN`, `_AUDITOR` and `_VIEWER`. They are set in env or a Secret and must all
  differ. `.env.example` has dev placeholder values for them; the real values were not seen.
- **Personal tokens** (`ssk_…`, one per user) are always VIEWER or AUDITOR, never ADMIN. They are created
  from the UI's `/skill` page.
- There are no per-service accounts. A caller that needs to reserve must hold the shared admin token.
- Every router except health, auth and metrics needs a resolved caller. Writes also need `require_admin`.
- **CORS** is controlled by `INVENTORY_CORS_ALLOWED_ORIGINS` (empty by default). Wingman should call
  server-scan from its backend.

---

## 4. Role in creating a hosted cluster, and in day 2

Nothing in the repo mentions herzi, segments-manager, kubevirt, HostedCluster or Wingman. It does mention
the **`install-server` Temporal workflow** (the workflows repo), the **`server-lifecycle-worker`** that runs
inside each MCE, and **bmh-generator-operator / bmhgen** (the old operator that `install-server` replaces)
(ADR-0032 updates, ADR-0035).

The flow below is pieced together from ADR-0032, ADR-0035, `records.py` and the live reservation event.
Steps marked **[inferred]** need confirming against the herzi and workflows notes.

1. **An MCE hub has InfraEnvs named after a hardware flavor**, for example `hp-gen11-nyc-64c-128gb`. The
   candidate pool for an InfraEnv is the name regex **`^ocp-<infraEnv>`** (ADR-0032: "its workflow id keys on
   the CANDIDATE POOL (`^ocp-<infraEnv>`)").
2. Something decides the InfraEnv needs more hosts **[inferred: herzi]** and starts
   **`install-server`**. Its workflow id was `install-server-<infraEnv>`; ADR-0035 says it can become
   `install-server-<infraEnv>-<mce>`.
   - It runs on the MCE's `server-lifecycle-worker`.
   - It calls `GET /servers/available?pattern=^ocp-<infraEnv>&count=N&health=…`.
   - It then calls `POST /servers/{id}/reservation` with `holder=install-server`, `mce_cluster`,
     `infra_env`, `namespace` and `workflow_id`.
   - It skips candidates that already have a BMH in its own MCE.
   - It creates the BMC Secret, BareMetalHost and NMStateConfig, using `bmc_vendor`, `bmc.host`, the
     ordered MACs and `os_name` for bonds.
   - It releases the reservation when it tears a candidate down, or lets it expire.
3. The host boots the discovery ISO and an `Agent` appears on the MCE. Within 5 minutes the
   `openshift-agents` job marks the server `INSTALLED_TO_INVENTORY` with `mce_name=<mce>`.
4. A hosted cluster is created **[inferred: from the helm-charts-hostedclusters-setup chart, through
   gitops]** and its NodePool binds Agents. The Agent's `spec.clusterDeploymentName.name` becomes the hosted
   cluster's name, and the agents job writes `INSTALLED`, `cluster_name=<hc>`, `mce_name=<mce>`.
5. **Day 2.**
   - Scaling down or deleting frees Agents back to `INSTALLED_TO_INVENTORY`, or to `AVAILABLE` once the
     BMH or Agent is gone. This is reconcile-on-absence, scoped per MCE or cluster.
   - Operators flag hardware with `maintenance` (and "donor").
   - Health, staleness and `contested_with` (one server claimed by two MCEs) are the signals to show.
   - Hardware is never repaired by server-scan. The one exception is the Dell collector, which can reset an
     iDRAC whose disks or NICs all read UNKNOWN (ADR-0050). That is report-only by default.

**segments-manager**: no link in the code. Server-scan has no VLAN or segment data, only NIC MACs and link
state and Cisco fabric connectivity. NMState and networking come from elsewhere.

**gitops**: server-scan is deployed from `team-redbull/redbull-platform` at `gitops/charts/server-scan`.
CI syncs the chart templates there (ADR-0031). `nodes-status` has one ArgoCD Application per cluster.

---

## 5. Concepts and naming conventions Wingman must adopt

- **Site codes**: lowercase tokens from `INVENTORY_SITES` (`code:Display Name`, comma-separated, `|` for
  aliases).
  - Shipped default and live instance: `nyc` (New York City), `tlv` (Tel Aviv), `bat-yam` (Bat Yam), `five`
    (Site Five), plus `unassigned` for servers with no site.
  - Production values live in redbull-platform and were not seen. The skill's example mentions "bat yam".
  - Wingman's site keys should be these codes, and the display name should come from `/sites`.
- **Hostname conventions** (classification rules, `classification_rule_repository.py:136`; the fake
  generator mirrors the real estate):
  - `HOSTED_CLUSTER`: `^ocp4-hypershift` (`ocp4-hypershift-<site>-NN`, a 5 tb box;
    `ocp4-hypershift-data-<site>-NN`, a 10 tb box) **or** `^ocp-`, which is hardware-spec naming:
    `ocp-<vendor>-<model>-<site>-<cores>c-<mem>gb[-<disk>tb][-<gpu>]-<serial>`, for example
    `ocp-dell-r650-bat-yam-192c-1024gb-h100-DEL0001310`.
  - `MCE`: the name contains `mce` (`ocp4-mce-<site>-NN`), the MCE hub's own nodes.
  - `UPI`: everything else (`ocp4[-prod|-prep]-<site>-compute|control-plane|infra-NN`).
  - Only `^ocp*` names are ingested.
- **InfraEnv name = hardware flavor = `<vendor>-<model>-<site>-<cores>c-<mem>gb…`.** The server pool for it
  is `^ocp-<infraEnv>`.
- **Cluster and MCE names**: `cluster_name` is unique across the estate. The MCE name is whatever the
  `nodes-status` release was given (`agents.mceName`), and it is the same string the reservation's
  `mce_cluster` uses.
  - Docs examples: `ocp4-tlv` (UPI), `mce-tlv` (MCE).
  - Workflows test: `ocp4-mce-workflow-test`.
  - Fake data: `hc-<site>-NN`, `mce-<site>`, `upi-<site>`.
  - Wingman's MCE identifiers must match the `mceName` used by nodes-status and workflows.
- **States**:
  - `openshift_state`: `AVAILABLE`, `INSTALLED` or `INSTALLED_TO_INVENTORY`.
  - `installation_type`: `UPI`, `HOSTED_CLUSTER`, `MCE` or `UNCLASSIFIED`. This is what the server is
    named to be, not what it is doing. When it disagrees with `openshift_state`, that is a signal.
  - Health: `HEALTHY`, `WARNING`, `MAJOR`, `CRITICAL` or `UNKNOWN`; `UNKNOWN` means "not read", not "fine".
  - Flags: `maintenance` (and the "donor" reason), `reservation.held`, `stale`, `reachable`,
    `contested_with`.
- **Vendors**: `dell`, `cisco`, `hp`, `standalone`. BMC driver vocabulary: `HP`, `DELL`, `CISCO`,
  `INTERSIGHT`. Source providers as in §2.
- Labels: there is no label model. `tags[]` is unused.

---

## 6. UI patterns (the visual reference)

Files: `frontend/src/index.css`, `frontend/src/components/*`, `.claude/rules/frontend.md`, ADR-0033.

- **Stack**: React 19, Vite 8, Tailwind 4 `@theme` tokens (no tailwind.config), TanStack Query 5 and
  TanStack Table 9, react-router 8, oxlint, vitest and Playwright.
- **Dark only**, on purpose (wall displays). Colors are oklch tokens:
  - Surfaces: `--surface-page`, `-raised`, `-sunken`, `-hover`.
  - Borders and text: `--border-subtle`, `-strong`; `--text-primary`, `-secondary`, `-muted`.
  - Status hues: healthy, info, warning, critical, maintenance, unknown.
  - Status chips are a tint and text pair (`--tint-*`, `--text-on-*`), plus major, donor and
    maintenance.
  - Every status pairs a glyph with a word and a color: CRITICAL ◆, MAJOR ⬟, WARNING ▲, HEALTHY ●,
    UNKNOWN ○ (`components/severity.ts`).
  - System font stack, a `.tabular` class for numerals, motion under 200 ms, and support for reduced
    motion.
- **Pages**:
  - Sites overview (`/`): per-site cards with totals, health, installation types, and available vs
    installed.
  - Inventory (`/servers`): one polled `/servers/rows` every 30 s with ETag; all filtering, search, sort
    and facets happen on the client in `features/inventory/rows.ts`; filters live in the URL.
  - **ClusterSidebar**: MCE, hosted-cluster and UPI multi-select lists derived from the rows. It uses
    repeated URL params (`?mce=a&mce=b&cluster=x`).
  - Server detail (`/servers/:id`): Overview, Hardware, Network, Connectivity and History tabs, and a
    "Back to inventory" that keeps the filters.
  - Events (`/events`), Rules (`/rules`), Jobs (`/jobs`, admin), Architecture (`/architecture`),
    Claude skill (`/skill`), Status (`/status`).
- **Components**:
  - `StateBadge` with wrapping chips (`Maint`, `Stale 20h`).
  - `ReservationBadge` sits **under** the installation badge and is never a replacement for it. It shows
    the target MCE, with holder, InfraEnv and expiry on hover.
  - `HealthBadge`, `InstallationBadge`, `LinkStateBadge`, `BmcLink` (icon that opens `https://<bmc_host>`),
    `CopyButton`, `Toaster`, `AdminGate` and `AuditGate`.
  - The maintenance toggle exists only in the inventory list.
  - CSV export has an "Installing to" column that is separate from "MCE".

---

## 7. Integration points for Wingman

### READ (from the Wingman backend, with the viewer token; cache with `cache.get_or_fetch`)

1. **Sites**: `GET /api/v1/sites` gives the site codes and display names, plus capacity counts for site
   cards. This **replaces** Wingman's `sites/` directory scan in GitLab
   (`apps/day1-service/src/services/cluster_service.py::list_sites`) as the source of *which sites exist*.
   The GitLab folder can stay as the place cluster YAML lives, keyed by those codes.
2. **MCEs per site**: take the distinct `mce_name` from `/servers/rows`, plus the MCE hubs' own
   `cluster_name` where `installation_type=MCE`, grouped by `site_id`.
   - This can validate or replace `list_mces` (also a GitLab directory scan today).
   - Caveat: it only knows MCEs that run the nodes-status agents job.
3. **Capacity for the cluster-create form**, per MCE and InfraEnv flavor:
   - Count `INSTALLED_TO_INVENTORY` rows for that `mce_name`: Agents ready to bind now.
   - Count `AVAILABLE` rows whose name matches `^ocp-<infraEnv>`, with health and reachability: servers
     install-server could add.
   - Use `/servers/rows` and filter on the client. Don't use `/available`.
   - Show reservations in progress from `reservation.held`, `mce_cluster` and `infra_env`.
4. **Cluster detail and day 2**: `GET /servers?cluster_name=<hc>` (or rows filtered by `cluster_name`) for
   the nodes' hardware, health, BMC links, maintenance, stale and contested flags. Show `/servers/{id}`
   detail or link out to the server-scan UI at `/servers/:id`.
5. **Events** (auditor token) for a server's history panel, if wanted.

### CALL (writes) — preferably not from Wingman directly

- Reservation and BMH creation belong to the `install-server` Temporal workflow. Wingman should **start
  workflows** through the orchestrator API (or commit a spec that herzi or gitops acts on). It should not
  call `/servers/available` and `/reservation` itself.
  - `/available` writes back and has no concurrency cap.
  - Reserving needs the shared ADMIN token.
- If Wingman offers "put server in maintenance", it needs the admin token. A user-scoped write path does
  not exist; tokens are shared static secrets and personal tokens are read-only.

### What server-scan replaces in Wingman

- **Site list**: server-scan `/sites` (codes from `INVENTORY_SITES`) instead of GitLab `sites/<site>`
  directories.
- **Server and host knowledge**: Wingman has none today. Server-scan is now the source for which physical
  hosts exist, are free, healthy and reserved.
- **InfraEnv list**: server-scan does **not** list InfraEnvs.
  - Wingman's live `GET /mces/{mce}/infraenvs` (`apps/day1-service/src/routers/mces.py`, which reads the MCE
    kube API) has no direct replacement here.
  - Server-scan provides the naming link (InfraEnv name = `^ocp-` hardware-flavor prefix), capacity per
    flavor, and `reservation.infra_env`.
  - The InfraEnv inventory itself presumably comes from herzi or the MCE. Check the herzi notes.
- **Cluster live status (nodes)**: server-scan's `cluster_name`/`mce_name` rows give per-cluster
  node-to-server mapping and hardware health without Wingman's `CLUSTER_STATUS_ENABLED` kube clients.
  Agent and HostedCluster *conditions* still come from the MCE.
- **Auth mismatch to plan for**: server-scan uses AD/LDAP and static tokens, while Wingman uses OpenShift
  OAuth and its own JWT. Use a service-to-service viewer token held in a Wingman Secret.

---

## 8. Live instance observations (GET only)

- `/health/ready`: mongo ok, redis ok. API title `server-scan-api` 0.1.0.
- **Auth disabled**: every caller is the `dev` ADMIN. That means anyone with the URL can write, so take
  care.
- **Fake fleet**: `/api/v1/jobs` shows only `server-scan-collector-fake` deployed (every 3 h) and
  `prune-events`. All real collectors are `enabled:false`. There are no nodes-status jobs; membership comes
  from `fake/openshift.py`.
- Fleet: 3,008 servers.
  - Sites: nyc 675, tlv 672, bat-yam 681, five 682, unassigned 298.
  - Vendors: 750 dell, 744 cisco, 737 hp, 777 standalone.
  - Installation types: HOSTED_CLUSTER 1,028, MCE 329, UPI 1,651.
  - States: AVAILABLE 607, INSTALLED 2,401, INSTALLED_TO_INVENTORY 0.
  - Flags: 557 stale, 88 unreachable, 24 contested, 0 reserved now, 0 in maintenance.
- Clusters: `hc-{bat-yam,five,nyc,tlv}-0{1,2,3}`, `mce-{site}`, `upi-{site}` and `upi-unassigned`.
- Audit trail: 12,063 events. One historic `SERVER_RESERVED` by `install-server` (shown above). One manual
  `JOB_TRIGGERED` of the fake collector on 2026-11-04.
- Router sets a sticky-session cookie (HAProxy), not an auth cookie.

## 9. Secrets seen

- `.env.example` contains dev placeholder values for `INVENTORY_API_TOKEN_{ADMIN,AUDITOR,VIEWER}` and a dev
  `INVENTORY_SESSION_SECRET`. These are placeholders, not production values, and were not reproduced here.
- The `nodes-status` values have `db.mongoUri` and `db.cursorSecret` fields (empty in the repo).
  Production values sit in the private redbull-platform repo.
- No real credentials were found in the repo.
