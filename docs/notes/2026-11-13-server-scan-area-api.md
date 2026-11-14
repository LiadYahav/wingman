# The Server Scan area: the API the web reads (2026-11-13)

The **Server Scan** area (`/server-scan`) is server-scan's UI rebuilt in
Wingman, one page at a time (workstream 4 of `docs/ideas/single-pane.md`,
decision 22, ADR-0048). This note covers the area, its first page,
**Sites** (§1 to §7), its second, **Servers** (§8, 3.23.0), a
server's own page (§9, 3.25.0) and the **Claude** page (§12, 3.29.0). Each
later page adds its section here (§10 lists them).

- **server-scan's API does not change.** day1 reads server-scan with the
  viewer token it already holds (§4), and a server's History with its
  auditor token (§9.5). The one write is a server's maintenance on and off,
  with server-scan's admin token, behind Wingman's admin check (§8.5).
- **The browser never calls server-scan.** It reads day1's routes below.
- **Admins only** (decision 13 of the single-pane plan, until RBAC): every
  route takes `AdminUser`, so a viewer gets `403 FORBIDDEN` and an anonymous
  call `401 UNAUTHORIZED`. The web shows the area to admins only.
- **Off without server-scan.** With `SERVER_SCAN_URL` empty (chart:
  `serverScan.url`) every route answers `501 FEATURE_DISABLED`, as the other
  optional features do, and the web hides the area. With `DAY1_FAKE_FLEET=true`
  (development only) the fake server-scan answers (§6).
- **server-scan failing** is `502 DEPENDENCY_UNAVAILABLE` on these routes only.
  The Nodes tab, MCE placement and Inventory Management keep their own
  behaviour (ADR-0038, ADR-0050, ADR-0057).

## 1. What server-scan's Sites page shows and does

Read from `team-redbull/server-scan` at `92146d3` (2026-11-12):
`frontend/src/features/sites/SitesOverviewPage.tsx`, its test, and
`frontend/src/api/sites.ts`. It is server-scan's landing page (`/`), first in
its navigation.

- **Header**: "Sites", then "N servers across M sites" (M leaves out
  Unassigned); "Loading fleet…" while it loads.
- **Fleet** (a section heading): six cards in a fixed order, read off the
  answer's `fleet` and never summed in the browser:

  | Card | Subtitle | Counts | Its link |
  |---|---|---|---|
  | Across all sites | servers, every site | `fleet` | `/servers` |
  | UPI | servers, every site | `fleet.by_installation_type.UPI` | `/servers?installation_type=UPI` |
  | Hosted cluster | servers, every site | `….HOSTED_CLUSTER` | `/servers?installation_type=HOSTED_CLUSTER` |
  | MCE | servers, every site | `….MCE` | `/servers?installation_type=MCE` |
  | Available | no cluster holds these | `fleet.by_openshift_state.AVAILABLE` | `/servers?openshift_state=AVAILABLE` |
  | Installed | in use by a cluster | `….INSTALLED` | `/servers?openshift_state=INSTALLED` |

- **Sites** (a section heading): one card per configured site, in
  server-scan's order, subtitle "servers", linking to
  `/servers?site_id=<site_id>`. The **Unassigned** card ("no site in
  hostname") is shown only when it holds a server; a configured site with
  none is shown at 0.
- **Every card**: its name and total; then only the counts above zero, each
  a glyph, the number and a word, in this order: `◆ N critical`,
  `⬟ N major`, `▲ N warning`, `⏸ N in maintenance`, `○ N unknown`. Every
  server healthy: `● all healthy`; none at all: `empty`. A site card adds
  `N installed` and `N available` (each above zero) from its own
  `by_openshift_state`. Last, a bar per vendor (Dell, Cisco, HPE,
  Standalone, KubeVirt), as wide as its share of the card's own total, with
  its count; an empty card has none.
- **Every count is a link into Servers**: the card's filter plus
  `health_overall=<SEVERITY>`, `maintenance=true` or
  `openshift_state=<STATE>` (`/servers?site_id=tlv&health_overall=CRITICAL`).
- **Refresh**: one `GET /api/v1/sites`. Not polled: TanStack Query's
  `staleTime` is 30 seconds with `refetchOnWindowFocus` off, so the page reads
  again when it is opened after 30 seconds. (Its Servers page polls every
  30 seconds; Sites does not.)
- **States**: three and six skeleton cards while loading; a failure reads
  "Could not load sites: <message>". No actions.

## 2. What server-scan serves: `GET /api/v1/sites`

Any authenticated caller: a viewer, auditor or admin token, or anyone when
server-scan runs with auth off (its `backend/app/main.py`: the router is
included with `get_current_actor` only). Built by `backend/app/api/v1/sites.py`:

- every configured site (`INVENTORY_SITES`, `code:Display Name`, in that
  order), then `unassigned` last; a site with no servers is listed at 0;
- every server counted once in its site, its installation type and its
  OpenShift state. An unknown health counts as `UNKNOWN`, an unknown
  installation type as `UNCLASSIFIED`, an unknown state as `AVAILABLE`, and a
  site no longer configured as `unassigned`, so the slices add up to the
  total;
- every vendor and severity present, zeroes included;
- cached 30 seconds in server-scan's Redis. No `ETag`.

## 3. `GET /api/day1/server-scan/sites`

server-scan's answer, typed and passed through **in its own shape**, so
server-scan's TypeScript types and card logic apply as they are
(decision 18).

```json
{
  "items": [
    {
      "site_id": "tlv",
      "name": "Tel Aviv",
      "total": 42,
      "by_vendor": [
        {"vendor": "dell", "count": 30},
        {"vendor": "cisco", "count": 12},
        {"vendor": "hp", "count": 0},
        {"vendor": "standalone", "count": 0},
        {"vendor": "kubevirt", "count": 0}
      ],
      "by_health": {"UNKNOWN": 0, "HEALTHY": 39, "WARNING": 1, "MAJOR": 0, "CRITICAL": 2},
      "in_maintenance": 1,
      "by_installation_type": {
        "HOSTED_CLUSTER": {"total": 12, "by_vendor": ["…"], "by_health": {"…": 0}, "in_maintenance": 0},
        "MCE": {"…": "…"},
        "UPI": {"…": "…"},
        "UNCLASSIFIED": {"…": "…"}
      },
      "by_openshift_state": {
        "AVAILABLE": {"total": 7, "…": "…"},
        "INSTALLED": {"total": 35, "…": "…"},
        "INSTALLED_TO_INVENTORY": {"total": 0, "…": "…"}
      }
    },
    {"site_id": "unassigned", "name": "Unassigned", "total": 0, "…": "…"}
  ],
  "fleet": {
    "total": 42,
    "by_vendor": ["…"],
    "by_health": {"…": 0},
    "in_maintenance": 1,
    "by_installation_type": {"…": "…"},
    "by_openshift_state": {"…": "…"}
  }
}
```

| Field | Meaning |
|---|---|
| `items` | One entry per configured site, in server-scan's order, then `unassigned`. `site_id` is the code in server names; `name` is what the UI shows |
| `total`, `by_vendor`, `by_health`, `in_maintenance` | A **breakdown**: how many servers, per vendor (server-scan's vendor order), per overall health (`UNKNOWN`, `HEALTHY`, `WARNING`, `MAJOR`, `CRITICAL`) and how many in maintenance. The same four fields describe a site, the fleet, and each slice below |
| `by_installation_type` | A breakdown per `HOSTED_CLUSTER`, `MCE`, `UPI`, `UNCLASSIFIED`: what the server was **named** to be (server-scan's classification of the hostname) |
| `by_openshift_state` | A breakdown per `AVAILABLE` (no cluster holds it), `INSTALLED` (a cluster's node), `INSTALLED_TO_INVENTORY` (an MCE's Agent, in no cluster yet) |
| `fleet` | Every site together, summed by server-scan, with the same two slices |

day1 keeps every key server-scan sends in these maps, in its order, including
a vendor, severity, type or state it adds later; a malformed answer (a
missing field, a count that is not a whole number) is a `502`.

**Not computed from the fleet rows.** day1 already caches server-scan's fleet
rows with their `ETag` (the Nodes tab, placement and Inventory share them),
and the rows carry each server's vendor, site, health, maintenance,
installation type and state, so the counts could be summed from them. The
page would still be wrong: the rows do not carry the **site catalog** (the
display names, server-scan's order, and the configured sites that have no
server, which the page shows at 0 because "this site has nothing in it" and
"this site does not exist" are different facts). The catalog is server-scan's
`INVENTORY_SITES` setting and only `/api/v1/sites` serves it. The answer is
also a few kilobytes against the rows' 2.2 MB, and server-scan's counting
rules stay its own. The fake does count its rows (§6), with server-scan's
rules ported, so the demo's cards agree with its servers.

## 4. The token

- **Sites needs a viewer token**, which Wingman already holds:
  `SERVER_SCAN_TOKEN`, from the Secret the chart names in
  `serverScan.tokenSecret` (key `token`), read by day1 only. **No new Secret,
  value or key.**
- server-scan accepts three shared static bearer tokens, from its own Secret
  `<release>-auth-credentials`, keys `INVENTORY_API_TOKEN_VIEWER`, `_AUDITOR`
  and `_ADMIN`. Personal `ssk_` tokens are viewer or auditor and expire
  (90 days by default): not for a service.
- **Sandbox**: server-scan runs with auth off, so every caller is an admin and
  Wingman needs no token (`serverScan.tokenSecret.name` empty: no
  `Authorization` header is sent).
- **Production**: server-scan's `auth.enabled` is on. Wingman needs the viewer
  token in a Secret, as the Nodes tab already does
  ([3.3-to-3.4.md](../upgrade/3.3-to-3.4.md)):
  `oc create secret generic server-scan-viewer -n <ns> --from-literal=token=<INVENTORY_API_TOKEN_VIEWER>`
  and `serverScan.tokenSecret.name=server-scan-viewer`. A refused token is a
  `502` naming `SERVER_SCAN_TOKEN`.
- **Later pages**: History and Events need the auditor token; Jobs and the
  writes (maintenance on/off, "run a job now") need the admin token, used only
  behind Wingman's admin check and recorded in Wingman's audit with the
  person's name. Each is its own key in the same Secret, read by day1 only,
  added with the page that needs it: the admin token came with Servers'
  maintenance toggle (§8.4), the auditor token with a server's History
  (§9.5).

## 5. Errors

| Status | `code` | When |
|---|---|---|
| 401 | `UNAUTHORIZED` | No session |
| 403 | `FORBIDDEN` | Not one of Wingman's admins |
| 501 | `FEATURE_DISABLED` | `SERVER_SCAN_URL` is empty; the detail names it |
| 502 | `DEPENDENCY_UNAVAILABLE` | server-scan unreachable, answering an error, refusing the token (the detail says to check `SERVER_SCAN_TOKEN`), or sending an answer day1 cannot read |

## 6. Cache, metrics and the fake

- **Cached for 10 seconds per replica** (ADR-0011) under `server-scan:sites`;
  a failure is not cached. server-scan caches it 30 seconds itself, so a
  count is at most about 40 seconds old.
- **Metrics**: one new operation, `list_sites`, on `wingman_dependency_*`
  with `dependency="server_scan"` (`docs/ops/metrics.md`). `denied` is a
  refused viewer token, `unavailable` anything else that failed.
- **The fake**: with `DAY1_FAKE_FLEET=true`, `FakeServerInventory.sites()`
  counts its own rows by server-scan's rules (ported from `_pivot` in
  `backend/app/api/v1/sites.py`) over the site catalog in
  `dev/fleet-fixtures/servers.yaml` (`sites`, server-scan's `INVENTORY_SITES`;
  `site3` has no servers, so its card shows 0). A server the fake uninstall
  frees or the fake add-server places moves on the next read.

## 7. The web

- **The top bar's switch** gains "Server Scan" (Wingman · Segments · Server
  Scan), for admins with server-scan configured; the area is `/server-scan`.
  A viewer, or a deployment without server-scan, never sees it; a viewer who
  opens `/server-scan` sees the "for admins" state in Wingman's chrome.
- **The brand** (top left): server-scan's own mark, its app icon (a rack of
  three units with status lights, `frontend/public/icons/app-icon.svg`), and
  "Server Scan", its page title. Its header shows the team's Red Bull logo
  instead: a third-party trademark and not server-scan's mark, so it is not
  copied.
- **The sidebar**: server-scan's pages, in its navigation's order, only those
  Wingman has built, so no entry leads nowhere: **Sites**, since 3.23.0
  **Servers**, and since 3.29.0 **Claude** (§12), in a Reference section.
  `apps/web/lib/server-scan/sidebar.ts` lists them; a new page is one entry.
- **The Sites page**: §1's cards, counts and words in Wingman's design (its
  colour tokens, light and dark). **The counts are not links yet**: the
  Servers page they open does not exist. Each card and count carries the
  filter it will open, in server-scan's parameter names (`data-filter`), so
  the Servers PR turns them into links in one place. Since 3.23.0 they are links to the
  Servers page (§8.8).
- **States**: skeleton cards while loading; "For admins" on `403`; "Server Scan
  is not set up" on `501`; the problem on `502`; a failed re-read keeps the
  last answer with a notice; zero servers: "No servers yet" instead of the
  fleet cards, the site cards still at 0.
- **Fresh data as the original**: read on open, read again when the page is
  opened after 30 seconds; no polling.
- **Reused from server-scan** (decision 18, credited in the code): its types
  for the answer, the card model (`fleetCards`, `siteCards`, the filters each
  card and count opens), the vendor labels, the severity glyphs, and its Sites
  page tests' cases as Vitest cases.

## 8. The Servers page (3.23.0)

`/server-scan/servers`: server-scan's Servers page, the fleet one row per
server (ADR-0048's 3.23.0 amendment). Inventory Management stays the view of
the MCE pools; this is the view of the fleet.

### 8.1 What server-scan's Servers page shows and does

Read from `team-redbull/server-scan` at `92146d3`: `frontend/src/features/inventory/`
(`InventoryPage.tsx`, `InventoryTable.tsx`, `rows.ts`, `sorting.ts`,
`ClusterSidebar.tsx`, `MultiSelect.tsx`, `MaintenanceToggle.tsx`,
`xlsxExport.ts`, `hooks.ts`), its badges in `frontend/src/components/`, and
`frontend/src/lib/donor.ts`. Second in its navigation, at `/servers`.

- **Header**: "Servers", then "N servers" (what the filters keep) and
  "Updated <generated_at>".
- **Search** ("Name, serial, BMC…", its tooltip the three syntaxes): plain
  text matches anywhere, `"text"` in quotes must equal a whole field,
  `/pattern/` is a case-insensitive regular expression of at most 64
  characters; an unusable one is shown under the box and keeps every row.
  It looks at the name, model, serial, vendor, site, installation type, BMC
  host, a held reservation's MCE and the MACs (a hex-looking query also
  matches a MAC without its separators).
- **Six dropdowns** of checkboxes, each option with how many servers ticking
  it would show (its count over what every *other* filter keeps): Vendor,
  Source (the collector: UCS Central, Intersight, OpenManage (Dell), OneView
  (HPE), Standalone (Redfish), KubeVirt (VMs)), Site (server-scan's sites,
  from `/sites`), Classification (`installation_type`), Installation
  (Installed, In inventory, Available) and Health (the five severities, then
  Maintenance, which keeps only servers in maintenance). Several values of one
  dropdown are OR, the dropdowns AND.
- **Toggles**, each with a tooltip and, while on, its count: Stale, Duplicate
  Name (the name is another server's too), Duplicate Server (claimed by two
  clusters), Name mismatch (OpenShift reports another hostname) and Donor (in
  maintenance with "donor" in the reason).
- **"Filtered by:"** a chip per active filter that removes it, and "Clear
  filters".
- **Cluster sidebar**, left of the table: **MCE**, **Hosted clusters** and
  **UPI clusters**, each a list of checkboxes with counts over what every
  other filter keeps, largest first. The lists are read off the fleet itself
  (a cluster with an MCE on any row is hosted, one with none is UPI), so a
  new cluster appears with the next read. A find box narrows all three when
  they hold more than 8 entries; the sidebar folds away ("‹ Hide filters",
  "Clusters (n) ›").
- **Table**: Name (a link to the server's page, a copy button on hover), BMC
  (opens `https://<bmc_host>` in a new tab; nothing without one),
  Installation (Available, Installed or In inventory, and "→ <MCE>" under it
  while an install holds the server), MCE (only when a row on the page has
  one), Cluster (and "Contested with <cluster>"), Model, State (the severity
  with its glyph; a Maint or Donor chip whose tooltip is the reason and who;
  Stale with its age; Name mismatch), Maintenance (the toggle, §8.5). Name,
  Installation, MCE, Cluster, Model and State sort, naturally and with blanks
  last; State by severity. A left edge marks critical, major and warning rows.
- **Paging**: 50 rows a page, Previous, "Page X of Y", Next.
- **Everything in the URL**, so a link or a refresh lands on the same view:
  `search`, `vendor`, `site_id`, `source_provider`, `installation_type`,
  `openshift_state`, `health_overall` (each repeated for several values),
  `maintenance` (`true`: only those; `exclude`: hide them), `stale`,
  `duplicate`, `contested`, `name_mismatch`, `donor` (`true`), `mce`,
  `cluster` (repeated), `sort`, `sort_desc`, `page`. A filter change goes back
  to page 1. The Sites page's cards and counts open it with these.
- **Export Excel**: every row the filters keep, not only the page, in the
  order shown, as `inventory-<date>.xlsx`, sheet "Servers": Name, Vendor, BMC
  address, Model, Serial, SPT, Installation, MCE, Cluster, State.
- **Fresh**: the rows are read every 30 seconds, in the background too; an
  unchanged fleet is a `304`.
- **States**: "Loading servers…"; the problem's detail; "No servers match:
  <filters>." with filters, "No servers match the current filters." without.

### 8.2 What server-scan serves

| Call | Token | Answer |
|---|---|---|
| `GET /api/v1/servers/rows` | any (viewer) | `{items: ServerRow[], generated_at}`: every server, 22 fields each (`id`, `name`, `vendor`, `model`, `site_id`, `source_provider`, `installation_type`, `health`, `maintenance` {`enabled`, `reason`, `created_by`}, `reservation` {`held`, `holder`, `mce_cluster`, `infra_env`, `expires_at`}, `openshift_state`, `cluster_name`, `mce_name`, `openshift_reported_name`, `contested_with`, `profile_template_name`, `last_seen_at`, `stale`, `reachable`, `serial`, `bmc_host`, `macs`). A weak `ETag` over the body and `Cache-Control: no-cache`; `If-None-Match` with it is a bodiless `304`. Cached by server-scan, cleared by its writes |
| `GET /api/v1/sites` | any (viewer) | The Site dropdown's options: names and order (§2) |
| `PUT /api/v1/servers/{id}/maintenance` | admin | Body `{reason?, expected_end?}`. Puts the server into maintenance, or updates the reason of one already in it; answers the server (`ServerDetail`). Its event and `created_by` name the caller: for a static token, `api-token-admin` |
| `DELETE /api/v1/servers/{id}/maintenance` | admin | Ends it; answers the server |

Both writes answer `404` for an unknown id, `401`/`403` for a token that is
not an admin's, `422` for a malformed body.

### 8.3 day1's routes

**`GET /api/day1/server-scan/servers`**: server-scan's answer in its own
shape, plus whether the maintenance toggle works here:

```json
{
  "items": [
    {
      "id": "srv_…", "name": "ocp-dell-r660-site1-…", "vendor": "dell",
      "model": "PowerEdge R660", "site_id": "site1", "source_provider": "OPENMANAGE",
      "installation_type": "HOSTED_CLUSTER", "health": "HEALTHY",
      "maintenance": {"enabled": false, "reason": null, "created_by": null},
      "reservation": {"held": false, "holder": null, "mce_cluster": null, "infra_env": null, "expires_at": null},
      "openshift_state": "INSTALLED", "cluster_name": "ocp4-prod-lark-site1",
      "mce_name": "ocp4-prod-mce-site1-a", "openshift_reported_name": null,
      "contested_with": null, "profile_template_name": "R660-Standard",
      "last_seen_at": "2026-11-11T08:00:03Z", "stale": false, "reachable": true,
      "serial": "DLFAKE0101", "bmc_host": "192.0.2.101", "macs": ["02:00:00:00:01:01"]
    }
  ],
  "generated_at": "2026-11-11T08:00:03Z",
  "maintenance_available": true,
  "maintenance_detail": null
}
```

- **Every field server-scan sends** (day1 read 18 of 22 before; it now reads
  `source_provider`, `openshift_reported_name`, `profile_template_name`,
  `bmc_host`, the maintenance's `reason` and `created_by`, and
  `contested_with`'s value). The rows keep server-scan's order. A
  reservation is `held` as server-scan judged it when day1 read it; one not
  held has every other field null.
- **`maintenance_available`** is whether the toggle works in this deployment
  (§8.4); `maintenance_detail` says why not, in one line, else `null`.
- **One cache, two `304`s.** The rows come from the cache the Nodes tab,
  placement and Inventory Management share (`server-scan:rows`, for
  `DAY1_CACHE_TTL_SECONDS`, 30 s by default), which asks server-scan with
  its `ETag`: an unchanged fleet costs server-scan a `304` and no download,
  however many pages are open. day1 sends its own weak `ETag` over its own
  answer and `Cache-Control: no-cache`; the browser's `If-None-Match` that
  matches gets a bodiless `304`, so a page polling an unchanged fleet
  downloads nothing (nginx keeps a weak `ETag` when it gzips).

**`PUT /api/day1/server-scan/servers/{server_id}/maintenance`**, body
`{"reason": "Replacing PSU 2 — INC-4417", "expected_end": "2026-11-14T16:00:00Z"}`
(both optional; `reason` at most 500 characters, `expected_end` an ISO 8601
date and time with its offset, `Z` or `+02:00`), and **`DELETE`** on the same path, answer the server's new
maintenance:

```json
{"id": "srv_…", "name": "ocp-dell-r660-site1-…", "maintenance": {"enabled": true, "reason": "Replacing PSU 2 — INC-4417", "created_by": "api-token-admin"}}
```

### 8.4 The tokens

- **Reads** use the viewer token, `SERVER_SCAN_TOKEN`, as Sites (§4).
- **The writes use server-scan's admin token**, a new optional key in the
  same Secret: `serverScan.tokenSecret.adminKey` (default `admin-token`) is
  read into `SERVER_SCAN_ADMIN_TOKEN`, by day1 only, through a
  `secretKeyRef` marked `optional`, so a Secret without the key still starts
  day1. Add it with
  `oc -n <ns> set data secret/<serverScan.tokenSecret.name> admin-token=<INVENTORY_API_TOKEN_ADMIN>`
  and restart day1. It is sent only on the two writes, never on a read.
- **Whether the toggle works**:

  | Viewer token | Admin token | Writes |
  |---|---|---|
  | any | set | sent with the admin token |
  | none | none | sent with no token: server-scan runs with auth off (the sandbox), where every caller is an admin |
  | set | none | off: the toggle is greyed out, its tooltip the one line below, and the routes answer `501 FEATURE_DISABLED` |

  The line: "Maintenance needs server-scan's admin token: add the key
  admin-token to the server-scan Secret and restart day1
  (SERVER_SCAN_ADMIN_TOKEN)."

### 8.5 The write: maintenance on and off

- **As server-scan's UI does it.** The toggle is the row's last cell. A
  server not in maintenance opens a dialog: "Put into maintenance", the
  server's name, "Why is it going into maintenance?", "Include the word
  “donor” to mark it as a parts donor.", the placeholder "Replacing PSU 2 —
  INC-4417", then Cancel and Start maintenance ("Starting…" while sent). A
  server in maintenance ends it in one click, as the original (the operators'
  asked-for asymmetry). The reason may be empty, as there.
- **Expected end**: server-scan's API takes one and its plan (decision 14)
  lists it, but its own dialog does not ask. Wingman's dialog adds it as one
  optional field, sent as `expected_end`.
- **Behind Wingman's admin check** (`AdminUser`), as the whole area.
- **Recorded with the person's name.** server-scan records the token as the
  actor (`api-token-admin`), so its own history cannot say who. day1 logs
  each write with the person, as node uninstall does (`node_uninstall_started`,
  ADR-0038): `server_maintenance_started` and `server_maintenance_ended` (info)
  with `user`, `server_id`, `server_name`, `reason` and `expected_end`, and
  `server_maintenance_unconfirmed` (warning) when the answer did not come
  back. Wingman has no audit store besides Git; these log lines are its
  record. (Until 3.23.0 none of Wingman's INFO records reached the pod's log:
  uvicorn configures only its own loggers. `create_base_app` now writes them
  to stderr, node uninstall's too.)
- **Never retried** (ADR-0006). Not sent (server-scan unreachable before the
  request left) is `502`, nothing changed. Sent but unanswered (a timeout or a
  connection lost after sending, or a gateway's `504`), or answered `200` in a
  shape day1 cannot read, is `504 AMBIGUOUS_WRITE`: it may have changed, and
  the page says to look at the row before trying again.
- **Seen at once.** After a write day1 drops its cached rows and sites, so the
  next read is server-scan's new answer. The page patches the row from the
  answer, then reads the rows and the Sites counts again (server-scan's own
  hook does the same).

### 8.6 Errors

| Status | `code` | When |
|---|---|---|
| 401 | `UNAUTHORIZED` | No session |
| 403 | `FORBIDDEN` | Not one of Wingman's admins |
| 404 | `NOT_FOUND` | A write to a server server-scan does not have |
| 422 | `VALIDATION_ERROR` | A reason over 500 characters or an `expected_end` that is not a date and time with its offset; or server-scan refused the body (its `422`, its words in `details.problems`) |
| 501 | `FEATURE_DISABLED` | `SERVER_SCAN_URL` is empty; on a write also: a viewer token without an admin token (§8.4) |
| 502 | `DEPENDENCY_UNAVAILABLE` | server-scan unreachable, answering an error, or refusing the token: the viewer token on a read (check `SERVER_SCAN_TOKEN`), the admin token on a write (check `SERVER_SCAN_ADMIN_TOKEN`) |
| 504 | `AMBIGUOUS_WRITE` | A write sent and not answered (§8.5) |

### 8.7 Metrics and the fake

- **Metrics**: the rows are the existing `list_server_rows`. Two new
  operations on `dependency="server_scan"`: `enable_maintenance` and
  `disable_maintenance`, with `ok`, `denied` (the admin token refused),
  `not_found`, `rejected` (its `422`), `unavailable` and `ambiguous`.
- **The fake** (`DAY1_FAKE_FLEET=true`): its rows are read from
  `dev/fleet-fixtures/servers.yaml` with all 22 fields; its writes change the
  row (by `dev`, as server-scan with auth off records it), and no token is
  needed, as on the sandbox.

### 8.8 The web

- **`/server-scan/servers`**, "Servers" in the area's sidebar after Sites,
  as server-scan's navigation orders them.
- **§8.1 in Wingman's design**: the shared table (`components/data-table/`),
  Wingman's colour tokens, light and dark, the explanations in tooltips.
- **Reused from server-scan** (decision 18, credited in the code): its row
  type, `rows.ts` (filter, search, sort, facets, dropdown facets, the cluster
  lists, paging), `sorting.ts`, `donor.ts`, the vendor, source and severity
  words and glyphs, the export's columns, and the cases of `rows.test.ts` and
  `xlsxExport.test.ts` as Vitest cases.
- **Wingman's column filter** (`f.model`) on Model, the one column
  server-scan offers no filter for; the dropdowns, toggles and the cluster
  sidebar stay server-scan's.
- **The cluster sidebar sits inside the page**, left of the table, as in
  server-scan: it filters this page and its counts follow the page's other
  filters, while the area's sidebar is navigation between pages, shown on
  every page.
- **Speed**: about 3,100 rows. The page shows them 50 at a time, as
  server-scan pages them, through the shared table, so the DOM holds 50 rows
  whatever the fleet; filtering, the facet counts and the cluster lists run
  in memory over the whole fleet when a filter changes (a few milliseconds),
  and the search waits for typing to pause. Not virtualised: paging is the
  original's, and a page of 50 needs nothing more. The rows are never kept in
  the browser's storage (the query cache persists other answers; 2 MB of
  rows polled every 30 seconds would not fit).
- **Export**: the Excel file of §8.1 (the shared `write-excel-file` export)
  and a CSV of the same rows and columns.
- **The Sites page's cards and counts are links** to
  `/server-scan/servers?<their filter>`.
- **States**: skeleton rows while loading; "For admins" on `403`; "Server
  Scan is not set up" on `501`; the problem on `502`; a failed re-read keeps
  the last rows with a notice; no server at all: "No servers yet"; nothing
  matching: "No servers match: <filters>." with Clear filters.

## 9. The server's page (3.25.0)

`/server-scan/servers/<id>`: server-scan's server page, one server's
record (ADR-0048's 3.25.0 amendment). It is **the one view of a server** in
Wingman: the Servers table, Inventory Management and (since 3.26.0) the
cluster page's Nodes tab link to it instead of repeating it (§9.8).

### 9.1 What server-scan's server page shows and does

Read from `team-redbull/server-scan` at `92146d3`: `frontend/src/features/servers/`
(`ServerDetailPage.tsx`, `OverviewTab.tsx`, `HardwareTab.tsx`,
`NetworkTab.tsx`, `ConnectivityTab.tsx`, `drives.ts`, `hooks.ts`),
`frontend/src/features/events/` (`HistoryTab.tsx`, `EventList.tsx`,
`EventTimeline.tsx`, `describeEvent.ts`, `hooks.ts`), its badges in
`frontend/src/components/` (`Reported.tsx`, `LinkStateBadge.tsx`,
`InstallationBadge.tsx`, `ReservationBadge.tsx`, `BmcLink.tsx`,
`CopyButton.tsx`, `HealthBadge.tsx`, `Badge.tsx`), `frontend/src/lib/`
(`datetime.ts`, `actor.ts`, `gpuModel.ts`) and their tests. It is at
`/servers/:id`, opened from a row's name on the Servers page.

- **Header**: "← Back to inventory" (to the Servers page with the filters it
  was opened from, else the unfiltered list), the server's name with a copy
  button, a **BMC** button opening `https://<bmc host>` in a new tab (none
  without a host), and the model under the name: the chassis model, else the
  GPUs' short name with "(from GPU)" (`inferredGpuModel`), else "—".
- **Five tabs**: Overview, Hardware, Network, Connectivity, History. History
  is shown only to a person who may read the audit trail (an auditor or an
  admin). The tab is component state, not in the URL.
- **Overview**, two columns of fields, each a small uppercase label over its
  value:
  - left: **Name**; **Model** (the GPU hint as in the header); **Serial**;
    **Manager** (the collector's manager id); **OpenShift**: the state badge
    ("Available", "Installed", "Installed to inventory"), the cluster, and
    "→ Installing to <MCE>" while an install holds the server (InfraEnv, who
    and until when in its tooltip), then "MCE <name>" or "—", then "Name
    mismatch · Installed as <name>" when OpenShift reports another hostname,
    and "Duplicate server · Also claimed by <cluster> as <name>"; **Host**,
    only for a KubeVirt VM: its node ("Not running" when stopped) and
    "· cluster <name>", the host server's name linking to its page with its
    health badge and a Maintenance badge, "CPU <model>", "· matched by name
    only", or "Node <n> is not in the inventory", "Node <n> matches more than
    one server", "Could not look up the host"; **Health breakdown**: a badge
    per category (Memory, Storage, RAID, Network, Connectivity, Power, GPU,
    BMC, Name), each only where server-scan can judge it (BMC not for
    Cisco's fabric collectors or KubeVirt, Power not for KubeVirt,
    Connectivity only for Cisco's fabric collectors, RAID only for
    OpenManage, standalone Redfish and Cisco UCS, GPU only with GPUs, Name
    only once judged), RAID with which BMC and method answered and why it is
    Unknown, then "Why this health": each policy that fired, worst first, its
    severity, category and message; **Last seen**: relative ("3 hours ago"),
    the exact time on hover, a Stale badge, or "Never collected".
  - right: **Vendor**; the profile template under its vendor's own name
    (Service profile template for UCS Central, Server profile template for
    Intersight and OneView, Deployment template for OpenManage; none for a
    standalone BMC or KubeVirt); **Site**; **Classification** (a badge);
    **Matched rule** ("<rule> (<field> ~ <pattern>)"); **Overall health**;
    **Maintenance** ("<reason> - by <who>", a static token read as "API
    token (admin)", or "Not in maintenance"), **read only** on server-scan's
    page; **Collection**, only when the BMC was unreachable ("Wrong
    credentials since <time>", "Timed out", "TLS error", "Not an iDRAC", …);
    **Last changed**.
- **Hardware**: CPU (Model, Sockets, Cores, Threads); Memory ("512.0 GiB
  total (16 modules)", binary units); Storage (the total in decimal TB or
  GB, then the drives smallest first, an unread capacity last: Model,
  Serial, Media, Capacity, Health with the vendor's raw word in brackets);
  GPU (Vendor, Model, Serial, PCI, VRAM, Memory type, ECC, Errors
  (correctable/uncorrectable), Temp, Power, Health, Firmware); Power (each
  PSU: its model, "— 1400W rated, 312W now", its health). A field the last
  collection could not read (`unread_fields`) says "Not reported" where
  nothing was ever read, or shows the carried-forward value dimmed and marked
  "unconfirmed".
- **Network**: BMC (Address with a copy button, MAC); Interfaces, in
  server-scan's order: the name and MAC, then where it is ("Slot 1 · port
  2", "Onboard · port 1" for a Dell NIC FQDD, else the BMC's location),
  "MAC #n" (its discovery order, which tooling picks bond pairs by), the
  speed and a link-state badge (UP, DOWN, DISABLED, UNKNOWN), and "OS name
  (derived): eno1" when server-scan's settings name it.
- **Connectivity** (Cisco): "N/M fabric paths up", then a card per fabric
  ("Fabric A", "Fabric B", …, "Other" last) of the physical uplinks only
  (a vNIC reports the same fabric): the interconnect's name and its
  operational state, Model, Serial, Server interface, Server port, Fabric
  port, Admin state, Speed. "No connectivity data." or "No physical fabric
  connections reported." otherwise.
- **History**: the server's audit trail, newest first, 50 a page, with
  Previous, "Page X of Y" and Next. Three columns: **What happened** (the
  event type in a pill tinted by kind; a health change as FROM → TO severity
  chips; another transition as "FROM → TO"; "▸ Details"), **When** (the exact
  time, relative on hover) and **User** (the actor and a user, token or
  system chip). Details open under the row: the event in a sentence
  (`describeEvent`; a health change instead shows the worst reason on each
  side, every field labelled), the matched rule of a classification change,
  then the event's data as JSON. "Loading history…", the problem, "No events
  recorded.".
- **Times**: every timestamp in Israel's zone (`Asia/Jerusalem`), day/month/
  year and 24 hours, whatever the browser's locale (`formatTimestamp`).
- **Fresh**: read when opened and again when opened after 30 seconds
  (server-scan's query client); not polled. The VM host is read with it. A
  History page is read when shown.
- **States**: "Loading server…"; the problem's detail ("No server with id
  'srv_…'." for an unknown id).

### 9.2 Every button on server-scan's server page

| Button | What it does | Kind | In Wingman |
|---|---|---|---|
| ← Back to inventory | The Servers page, with the filters it was opened from | read (navigation) | "← Servers", the same |
| Copy server name | The name to the clipboard | read | The same |
| BMC | `https://<bmc host>` in a new tab | read (a link out) | The same |
| Overview, Hardware, Network, Connectivity, History | Switch tab | read | The same; the tab is in the URL |
| A VM host's name (Overview, Host) | That server's page | read (navigation) | The same |
| Copy BMC address (Network) | The address to the clipboard | read | The same |
| ▸ Details / ▾ Hide details (History) | Opens one event | read | The same |
| Previous, Next (History) | Pages of 50 | read | The same |
| Maintenance (Overview) | Nothing: server-scan shows it read only | read | Read only too, with a "Switch on Servers" link to the list at this server (§9.8) |

**No new admin write.** server-scan's page has no other control: its
commit `0bb7dad` ("switch maintenance only from the inventory list; the
detail page is read-only for it") removed the page's maintenance buttons.
Its API has more server writes, and no button in its UI calls them:
`POST /servers/{id}/reclassify` (run classification again), `POST
/servers/{id}/health/recalculate` (judge health again) and `POST`/`DELETE
/servers/{id}/reservation` (the install lock, which herzi and the workflows
take and release). Decision 14 is server-scan's UI, every button of it, so
Wingman does not offer them.

### 9.3 What server-scan serves

| Call | Token | Answer |
|---|---|---|
| `GET /api/v1/servers/{id}` | any (viewer) | Its `ServerDetail`: the server whole (hardware, network, connectivity, classification, health with its reasons, maintenance, reservation, OpenShift, VM host, unread fields, …). `404` for an unknown id. Cached by server-scan per revision |
| `GET /api/v1/servers/{id}/vm-host` | any (viewer) | `{cluster_name, node_name, match, host}`: the bare-metal server a KubeVirt VM runs on, resolved now (`match`: `MEMBERSHIP`, `NAME`, `AMBIGUOUS`, `NOT_IN_INVENTORY`, `NOT_RUNNING`; `host` set on the first two). `404` for an unknown id or a server that is not a VM. Never cached |
| `GET /api/v1/servers/{id}/events?cursor=&page_size=` | **auditor or admin** (`require_audit_access`; a viewer token is `403`) | `{items: AuditEventResponse[], page: {next_cursor, has_more, page_size, total}}`: newest first, keyset pages, `page_size` 1 to 200 (50), `total` on the first page only. An unknown id is an empty page |

### 9.4 day1's routes

**`GET /api/day1/server-scan/servers/{server_id}`**: the record, in
server-scan's own shape (the fields its UI reads, every one typed by day1),
plus whether the maintenance toggle and History work here:

```json
{
  "id": "srv_…", "name": "ocp-dell-r660-site1-128c-1024gb-DLFAKE0101",
  "model": "PowerEdge R660",
  "profile_template": {"name": "R660-Standard", "external_id": "tmpl-r660"},
  "identity": {"vendor": "dell", "serial": "DLFAKE0101", "system_uuid": "…", "nic_macs": ["02:00:00:00:01:01"]},
  "hardware": {
    "cpu": {"sockets": 2, "cores": 64, "threads": 128, "model": "Intel(R) Xeon(R) Platinum 8462Y+"},
    "memory": {"total_bytes": 1099511627776, "modules": [{"slot": "A1", "size_bytes": 68719476736, "speed_mhz": 4800, "health": "HEALTHY", "health_detail": "OK"}]},
    "storage": {
      "total_bytes": 3840000000000,
      "drives": [{"id": "Disk.Bay.0", "model": "…", "serial": "…", "media_type": "SSD", "capacity_bytes": 960000000000, "health": "HEALTHY", "health_detail": "OK"}],
      "controllers": [{"id": "RAID.SL.3-1", "name": "PERC H755", "kind": "RAID", "volumes": [{"id": "Disk.Virtual.0", "raid_type": "RAID1", "volume_type": "Mirrored", "capacity_bytes": 480000000000, "health": "HEALTHY"}]}],
      "raid": {"state": "PRESENT", "method": "redfish_storage", "bmc": "iDRAC9", "reason": null}
    },
    "gpus": [],
    "power": {"psus": [{"id": "PSU.Slot.1", "model": "…", "serial": "…", "health": "HEALTHY", "health_detail": "OK", "capacity_watts": 1400, "power_watts": 312.0}]}
  },
  "network": {
    "bmc": {"address_raw": "https://192.0.2.101", "scheme": "https", "host": "192.0.2.101", "port": null, "mac": "02:00:00:00:01:ff"},
    "interfaces": [{"name": "NIC.Integrated.1-1-1", "mac": "02:00:00:00:01:01", "speed_mbps": 25000, "link_state": "UP", "location": "1/1/1"}]
  },
  "connectivity": {"attachments": [], "facts": {"fabric_paths_total": 0, "fabric_paths_up": 0, "fabric_paths_down": 0, "fabrics_present": []}},
  "classification": {"installation_type": "HOSTED_CLUSTER", "matched_rule_id": "…", "matched_rule_name": "Hosted cluster nodes", "matched_field": "name", "matched_pattern": "^ocp-"},
  "health": {"overall": "HEALTHY", "memory": "HEALTHY", "storage": "HEALTHY", "raid": "HEALTHY", "network": "HEALTHY", "connectivity": "UNKNOWN", "power": "HEALTHY", "gpu": "UNKNOWN", "bmc": "HEALTHY", "name": "HEALTHY", "reasons": []},
  "maintenance": {"enabled": false, "reason": null, "created_by": null, "created_at": null, "updated_at": null, "expected_end": null},
  "reservation": {"held": false, "holder": null, "mce_cluster": null, "infra_env": null, "namespace": null, "workflow_id": null, "created_at": null, "expires_at": null},
  "site_id": "site1", "manager_id": "openmanage-site1", "source_provider": "OPENMANAGE",
  "openshift": {"lifecycle_state": "INSTALLED", "cluster_name": "ocp4-prod-lark-site1", "mce_name": "ocp4-prod-mce-site1-a", "last_reported_at": "…", "reported_by_agent_id": "…", "reported_name": null, "contested_with": null, "contested_name": null},
  "vm_host": null,
  "unread_fields": [], "nic_os_names": {"NIC.Integrated.1-1-1": "eno12399np0"}, "tags": [],
  "last_seen_at": "2026-11-11T08:00:03Z", "stale": false, "reachable": true,
  "unreachable_since": null, "unreachable_reason": null,
  "updated_at": "2026-11-11T08:00:03Z", "created_at": "2026-09-01T06:00:00Z",
  "maintenance_available": true, "maintenance_detail": null,
  "history_available": true, "history_detail": null
}
```

- **The fields server-scan's UI reads** (its `frontend/src/types/server.ts`
  `ServerDetail`), each typed: a field of the wrong type is a `502`, never a
  blank. Left out are server-scan's internals the UI never reads
  (`schema_version`, `name_normalized`, `model_normalized`, `search_tokens`,
  `revision`, a drive's slot, protocol and firmware, a module's type and
  serial, a controller's drive count, the BMC's `host_is_ip` and path, an
  identity's external ids, the health's `evaluated_at` and policy keys, the
  classification's version and time, the OpenShift claim's agent history).
  Enumerations (`vendor`, severities, states, `installation_type`,
  `media_type`, a controller's `kind`, …) are kept as server-scan sends
  them, so a value it adds later reaches the page, which shows it as it is.
  A list or object server-scan leaves out on an older document
  (`health.reasons`, `storage.controllers`, `storage.raid`) is sent as empty
  or `null`.
- **`maintenance`** carries server-scan's `created_at`, `updated_at` and
  `expected_end` too: Wingman's dialog sets an expected end (§8.5), so the
  record shows it.
- **`reservation.held`** is computed by day1 when it reads the record, with
  server-scan's rule for its rows (`_reservation_flag`: a holder, and no
  expiry or one still ahead). server-scan's own detail answer has no `held`,
  which its UI's type expects, so its page never shows "→ Installing to" on
  a server's page; Wingman's does.
- **`maintenance_available`** and **`maintenance_detail`** are §8.3's;
  **`history_available`** and **`history_detail`** say whether History works
  in this deployment, and why not (§9.5).
- **Not cached by day1**: server-scan caches the record per revision itself,
  so a read costs it a Redis hit. One read per page open (and per re-read
  after 30 seconds), whoever opens it.

**`GET /api/day1/server-scan/servers/{server_id}/vm-host`**: server-scan's
answer, typed, in its shape:

```json
{
  "cluster_name": "ocp4-prod-virt-site1", "node_name": "worker-3", "match": "MEMBERSHIP",
  "host": {
    "id": "srv_…", "name": "ocp-dell-r760-site1-…", "vendor": "dell", "model": "PowerEdge R760",
    "site_id": "site1", "cpu": {"sockets": 2, "cores": 96, "threads": 192, "model": "…"},
    "memory_total_bytes": 1649267441664, "health": "HEALTHY", "maintenance": false,
    "cluster_name": "ocp4-prod-virt-site1"
  }
}
```

`404 NOT_FOUND` for an unknown server or one that is not a VM. The page asks
only for a VM (`vm_host` not null), as server-scan's does. Not cached (the
host's health and maintenance change without the VM changing).

**`GET /api/day1/server-scan/servers/{server_id}/events?cursor=<cursor>&page_size=<n>`**:
one page of the server's audit trail, server-scan's answer in its shape, read
with server-scan's **auditor token**:

```json
{
  "items": [
    {
      "id": "evt_…", "event_type": "MAINTENANCE_ENABLED",
      "server_id": "srv_…", "server_name": "ocp-dell-r660-site1-…",
      "actor": {"type": "TOKEN", "id": "api-token-admin", "display": null},
      "request_id": "…", "created_at": "2026-11-12T09:14:00Z",
      "data": {"reason": "Replacing PSU 2 — INC-4417"}
    }
  ],
  "page": {"next_cursor": "…", "has_more": true, "page_size": 50, "total": 132}
}
```

- `page_size` 1 to 200 (default 50), `cursor` the previous page's
  `next_cursor` (at most 512 characters), both passed through. An event's
  `data` is whatever its writer recorded, passed through as JSON; every
  other field is typed. `event_type` is kept as server-scan sends it.
- **The person behind a Wingman write is not in it**: server-scan records
  the admin token (`api-token-admin`), so its History says "API token
  (admin)". Wingman's own log names the person (§8.5).
- Not cached by day1; the page reads a page when it is shown.

### 9.5 The tokens: the auditor token

- **The record and the VM host** use the viewer token, `SERVER_SCAN_TOKEN`,
  as Sites (§4).
- **History uses server-scan's auditor token**, a third optional key in the
  same Secret: `serverScan.tokenSecret.auditorKey` (default `auditor-token`)
  is read into `SERVER_SCAN_AUDITOR_TOKEN`, by day1 only, through a
  `secretKeyRef` marked `optional`, so a Secret without the key still starts
  day1. Add it with
  `oc -n <ns> set data secret/<serverScan.tokenSecret.name> auditor-token=<INVENTORY_API_TOKEN_AUDITOR>`
  and restart day1. It is sent only on the History read, never on another
  call; the admin token stays on the maintenance writes only, though
  server-scan would let it read the audit trail too.
- **Whether History works**, as §8.4's table for the toggle:

  | Viewer token | Auditor token | History |
  |---|---|---|
  | any | set | read with the auditor token |
  | none | none | read with no token: server-scan runs with auth off (the sandbox) |
  | set | none | off: the tab says so in one line, and the route answers `501 FEATURE_DISABLED` |

  The line: "History needs server-scan's auditor token: add the key
  auditor-token to the server-scan Secret and restart day1
  (SERVER_SCAN_AUDITOR_TOKEN)."
- A refused auditor token is a `502` naming `SERVER_SCAN_AUDITOR_TOKEN`.

### 9.6 Errors

| Status | `code` | When |
|---|---|---|
| 401 | `UNAUTHORIZED` | No session |
| 403 | `FORBIDDEN` | Not one of Wingman's admins |
| 404 | `NOT_FOUND` | server-scan has no such server; on `/vm-host` also: the server is not a VM |
| 422 | `VALIDATION_ERROR` | `page_size` outside 1 to 200, a `cursor` over 512 characters |
| 501 | `FEATURE_DISABLED` | `SERVER_SCAN_URL` is empty; on `/events` also: a viewer token without the auditor token (§9.5) |
| 502 | `DEPENDENCY_UNAVAILABLE` | server-scan unreachable, answering an error, refusing the token (the viewer token on the record and the VM host: check `SERVER_SCAN_TOKEN`; the auditor token on History: check `SERVER_SCAN_AUDITOR_TOKEN`), or sending an answer day1 cannot read |

The maintenance toggle on this page calls §8.3's `PUT`/`DELETE` routes, with
§8.6's errors.

### 9.7 Metrics and the fake

- **Metrics**: three new operations on `dependency="server_scan"`:
  `get_server_record` (the record), `get_vm_host` and `list_server_events`
  (History), with `ok`, `not_found` (the record, the VM host), `denied` (the
  viewer token refused; on `list_server_events` the auditor token) and
  `unavailable`. `get_server` stays the uninstall's fresh check, which reads
  only the server's name and cluster (ADR-0038). The toggle is §8.7's
  `enable_maintenance` and `disable_maintenance`.
- **The fake** (`DAY1_FAKE_FLEET=true`): a server's record is its row from
  `dev/fleet-fixtures/servers.yaml` and the hardware of its model from
  `dev/fleet-fixtures/server-records.yaml` (CPU, memory, drives, RAID,
  PSUs and NICs per model; GPUs on one model; Cisco's fabric uplinks), with
  a few servers' health reasons, unread fields and an unreachable BMC to
  show those states. No fake server is a VM, so `/vm-host` answers `404`.
  Its History is made from the row (discovered, classified, installed,
  health, maintenance) and every maintenance change made in the fake since it
  started, by `dev` as server-scan with auth off records it. No token is
  needed, as on the sandbox.

### 9.8 The web

- **`/server-scan/servers/<id>`**, below Servers in the area (the sidebar
  keeps Servers marked). The tab is in the URL: `?tab=hardware`, `network`,
  `connectivity` or `history`; Overview has none.
- **§9.1 in Wingman's design**: server-scan's tabs, fields, words and
  badges, Wingman's colour tokens (light and dark), the explanations in
  tooltips.
- **The maintenance block is read only**, as server-scan's page is (its
  `0bb7dad`): the state, the reason (since when and the expected end in its
  tooltip), and a "Switch on Servers" link that opens the Servers list at
  this server, where the toggle is (§8.5).
- **History** is a tab for every admin (server-scan hides it from viewers;
  the area is for admins). Without the auditor token it says so in the one
  line of §9.5.
- **"← Servers"** returns to the Servers page with the filters it was opened
  from (server-scan keeps them in its router's state), else the unfiltered
  list.
- **Links into it**:
  - the Servers table's **Name** cell is a link to the server's page; its
    copy button stays (§8.1: server-scan's Name is a link);
  - **Inventory Management**: a pool's candidates and the add-server runs'
    **Server** column link to it, for a person who has the Server Scan area
    (an admin, with server-scan configured); for anyone else they stay
    text. In the install dialog's picker the link opens a new tab, so the
    choice in the dialog stays. A run names its server only by name, so `GET
    /api/day1/inventory/runs` gains `server_id`: server-scan's id for that
    name, when exactly one server has it (ignoring case), from the rows day1
    already caches; `null` otherwise, or when server-scan could not be read
    (the runs are still listed);
  - a VM's **Host** links to its host server's page.
  - **The cluster page's Nodes tab** (3.26.0, ADR-0048's amendment): a
    server's name there, and a node in the Overview's opened nodepool,
    opens its page in this tab, without the external-link mark, for a
    person who has the area; anyone else keeps server-scan's own page
    (`url`) in a new tab. The nodes read already carries the id
    (`server.id`); `nodeServerLink` in `lib/server-scan/server-page.ts` is
    the one decision. Nothing else on the cluster page changes.
- **States**: skeleton fields while loading; "For admins" on `403`; "Server
  Scan is not set up" on `501`; "No server <id>" on `404`, with a link to
  Servers; the problem on `502`; a failed re-read keeps the record with a
  notice. History: loading, the not-set-up line, the problem, "No events
  recorded.".
- **Fresh as the original**: read on open, again when opened after 30
  seconds; not polled.
- **Reused from server-scan** (decision 18, credited in the code):
  `datetime.ts` (`formatTimestamp`, `formatRelative`), `actor.ts`,
  `gpuModel.ts`, `drives.ts`, `describeEvent.ts`, the fabric grouping of
  `ConnectivityTab.tsx`, the NIC wording of `NetworkTab.tsx`, the health
  breakdown's rules, the profile-template and unreachable labels, the event
  tints, its types, and their tests' cases as Vitest cases.

## 10. Left for later pages

In single-pane §4's order; each is its own PR, with its section in this note.

| Page | server-scan reads (token) | What Wingman adds |
|---|---|---|
| Confs | `GET /api/v1/confs` (viewer) | Read only |
| Rules & Policies | `GET /api/v1/classification-rules`, `/health-policies` (viewer) | Read only |
| Events | `GET /api/v1/events`, `/events/actors` (auditor) | Filters and cursor pages; History's timeline and its auditor token (§9) reused |
| Jobs | `GET /api/v1/jobs`, a run's pod logs, `POST /jobs/{cronjob}/run` (admin) | "Run now" behind the admin check, its confirmation, Wingman's audit |
| Architecture | none | server-scan's diagrams, framed from its UI (`SERVER_SCAN_UI_URL`) |
| Claude | `GET /api/v1/skill`, `/skill/download` (viewer) | Built in 3.29.0 (§12): the skill and its zip through day1; the personal token stays a link out, server-scan makes it only for its own login |

## 12. The Claude page (3.29.0)

server-scan's **Claude** page (`/skill`, the seventh in its navigation)
rebuilt at `/server-scan/claude`, in Wingman's design and server-scan's
words (ADR-0048's 3.29.0 amendment). Read from `team-redbull/server-scan`
at `92146d3`: `frontend/src/features/skill/` (`SkillPage.tsx`,
`McpSection.tsx`, `TokenSection.tsx`, `skillText.ts` and their tests),
`frontend/src/api/skill.ts`, `backend/app/api/v1/skill.py`,
`backend/app/application/services/skill_bundle.py`, its ADR-0052 (the skill
page) and ADR-0054 (the MCP server).

### 12.1 What server-scan's Claude page shows and does

A guide to `server-scan-api`, the Claude Code skill in server-scan's repo
(`.claude/skills/server-scan-api`: `SKILL.md` and `references/*.md`).
Everything on it is read from `GET /api/v1/skill`, so editing the skill
updates the page; it is read again every minute and on window focus.

- **Header**: "Ask Claude about Server Scan"; "Install the `<name>` skill in
  Claude Code and ask in plain language. It builds the API calls, pages
  through the results and answers with real data."; **Download
  `<name>.zip`**. "Loading the skill…" while it loads; "This server carries
  no skill, or it could not be read." when it cannot.
- **Set it up in a minute**, four steps: (1) Download the zip: "The address
  of this server (`<origin>`) is already written into it."; (2) Unzip it
  into your skills folder: `unzip -o ~/Downloads/<name>.zip -d
  ~/.claude/skills`, with a copy button; (3) Add your token: "Create it
  below, then open `~/.claude/skills/<name>/SKILL.md` and replace the
  `VIEWER_TOKEN` (a viewer) or `AUDITOR_TOKEN` (anyone else) placeholder.
  Keep it out of git."; (4) Ask: "Start Claude Code and just ask.", with up
  to six chips, the quoted examples in the skill's description, each copied
  on click.
- **Your token** (only when login is on and the person is signed in to
  server-scan): their one personal token (ADR-0053 there): its prefix,
  access, expiry, last use; **Create my token** / **Replace my token** and
  **Revoke**; a new token is shown once, as the line to paste
  (`AUDITOR_TOKEN=ssk_…`).
- **Or connect it as an MCP server**: "One command, nothing to unzip and no
  file to edit. …", the command `claude mcp add --transport http
  server-scan <origin>/mcp --header "Authorization: Bearer <your token>"`
  with a copy button; a token just created is filled in.
- **When Claude uses it** (the description and `when_to_use`) and **What it
  may run** ("Read-only. The skill is limited to these tools and stays on
  GET requests.", the `allowed-tools` as chips).
- **What's inside**: each file as a tab, an "On this page" outline of its
  `##` and `###` headings (fenced code skipped) that scrolls to the line,
  the line count, a copy button for the file, the numbered lines.

### 12.2 Every button, and Wingman's

| server-scan | Wingman |
|---|---|
| Download `<name>.zip` | The same, through day1 (§12.4); server-scan's zip, its address written in |
| Copy the unzip command, a prompt chip, the MCP command, a file | The same |
| Create my token, Replace my token, Revoke | **None.** server-scan makes a personal token only for a person signed in to server-scan itself (its session, never a service token), so step 3 and the MCP section link to server-scan's own Claude page (`<server-scan>/skill`, a new tab) and say so in one line |
| The outline's headings, the file tabs | The same |

### 12.3 What server-scan serves

| Call | Token | Answer |
|---|---|---|
| `GET /api/v1/skill` | any resolved caller (viewer) | `{name, description, when_to_use, allowed_tools, version, updated_at, files: [{path, content}]}`, read from server-scan's disk on every call (`SKILL.md` first); `version` is a hash of the files. `404` when the deployment carries no skill |
| `GET /api/v1/skill/download?base_url=` | any resolved caller (viewer) | `application/zip`, `attachment; filename="<name>.zip"`: `<name>/SKILL.md` and `<name>/references/*.md`, `base_url` written over the `BASE_URL=` line (a plain http(s) address, else `422`), the token never; a viewer caller's copy says `VIEWER_TOKEN` where the skill says `AUDITOR_TOKEN`. `404` as above |
| `/mcp` | the person's token | server-scan's MCP server (its ADR-0054), behind its UI's nginx when its chart's `mcp.enabled`; Wingman never calls it |

### 12.4 day1's routes

**`GET /api/day1/server-scan/skill`**: server-scan's skill in its shape,
typed by day1, plus two fields:

```json
{
  "name": "server-scan-api",
  "description": "Queries the Server Scan REST API … (\"all Dell servers in site1\", …)",
  "when_to_use": "Also for questions about a server's BMC address, …",
  "allowed_tools": "Bash(curl *) Bash(jq *)",
  "version": "0123456789ab",
  "updated_at": "2026-11-01T08:00:00Z",
  "files": [{"path": "SKILL.md", "content": "---\nname: server-scan-api\n…"}, {"path": "references/endpoints.md", "content": "…"}],
  "server_scan_url": "https://server-scan.example",
  "token_line": "VIEWER_TOKEN"
}
```

- `server_scan_url` is server-scan's address for people and Claude Code:
  `SERVER_SCAN_UI_URL`, else `SERVER_SCAN_URL` (the node links' rule), the
  fake fleet's `http://server-scan.example` when both are empty. server-scan's
  page uses its own origin; Wingman's cannot, since Claude Code must call
  server-scan, never Wingman.
- `token_line` is the placeholder the download's `SKILL.md` names, by
  server-scan's own rule with Wingman as the caller whose copy it is:
  `VIEWER_TOKEN` when Wingman sends its viewer token, `AUDITOR_TOKEN` when it
  sends none (server-scan with auth off: every caller is an admin).
- Cached for 60 seconds per replica (`server-scan:skill`), the original's
  refresh; a failure is not cached.

**`GET /api/day1/server-scan/skill/download`**: server-scan's zip as it
sent it, `base_url` = `server_scan_url`, once it reads as a zip;
`application/zip`, `Content-Disposition: attachment; filename="<name>.zip"`
(server-scan's name when it is a skill name, else `server-scan-api`),
`Cache-Control: no-cache`. Never cached by day1.

### 12.5 The token

**The viewer token only** (`SERVER_SCAN_TOKEN`, §4) on both reads; no new
Secret, key or value. The person's own token is server-scan's: it is made,
replaced and revoked on server-scan's Claude page by someone signed in to
server-scan, and never passes through Wingman. A person whose server-scan
token is an auditor's pastes it over the `VIEWER_TOKEN` line of a viewer
copy; the line's name is only a name, and the skill reads the value.

### 12.6 Errors

| Status | `code` | When |
|---|---|---|
| 401 | `UNAUTHORIZED` | No session |
| 403 | `FORBIDDEN` | Not one of Wingman's admins |
| 404 | `NOT_FOUND` | server-scan carries no skill (its own words in the detail) |
| 501 | `FEATURE_DISABLED` | `SERVER_SCAN_URL` is empty |
| 502 | `DEPENDENCY_UNAVAILABLE` | server-scan unreachable, answering an error, refusing the viewer token (check `SERVER_SCAN_TOKEN`), refusing the address written into the zip (its `422`: check `SERVER_SCAN_UI_URL`), or sending a skill day1 cannot read or a download that is not a zip |

### 12.7 Metrics and the fake

- **Metrics**: two new operations on `dependency="server_scan"`:
  `get_skill` and `download_skill`, with `ok`, `not_found` (no skill),
  `denied` (the viewer token refused) and `unavailable`
  (`docs/ops/metrics.md`).
- **The fake** (`DAY1_FAKE_FLEET=true`): a short stand-in skill in
  `dev/fleet-fixtures/skill/` (`SKILL.md` with server-scan's frontmatter
  keys and its `BASE_URL=`/`AUDITOR_TOKEN=` lines, and one
  `references/endpoints.md`), read and zipped as server-scan's
  `skill_bundle.py` does (ported), as a server-scan with auth off answers:
  `AUDITOR_TOKEN`. Without a skill the fake answers `404`.

### 12.8 The web

- **`/server-scan/claude`**, in the sidebar's **Reference** section after
  the Fleet pages (server-scan's order: … Rules & Policies, Claude,
  Architecture).
- **§12.1 in Wingman's design**, server-scan's words, with these changes:
  step 1 names server-scan's address (`server_scan_url`), not the page's
  origin; step 3 links to server-scan's Claude page for the token and says
  in one line that server-scan makes a personal token only for someone
  signed in to it; there is no token section; the MCP command keeps `<your
  token>`, with a line to paste it from server-scan's page.
- **The download** fetches day1's zip with the session's token (as every
  call) and hands it to the browser as `<name>.zip`; a failure shows day1's
  problem under the button.
- **States**: a skeleton while loading; "For admins" on `403`; "Server Scan
  is not set up" on `501`; "No Claude skill" on `404`; the problem on
  `502`; a failed re-read keeps the page with a notice.
- **Fresh as the original**: read again every minute and on window focus.
- **Reused from server-scan** (decision 18, credited in the code):
  `skillText.ts` (`extractPrompts`, `outline`), the tools' split, its types,
  and its tests' cases as Vitest cases (`lib/server-scan/skill-text.test.ts`).
