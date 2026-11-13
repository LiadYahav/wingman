# The Server Scan area: the API the web reads (2026-11-13)

The **Server Scan** area (`/server-scan`) is server-scan's UI rebuilt in
Wingman, one page at a time (workstream 4 of `docs/ideas/single-pane.md`,
decision 22, ADR-0048). This note covers the area, its first page,
**Sites** (§1 to §7), and its second, **Servers** (§8, 3.23.0). Each later
page adds its section here (§9 lists them).

- **server-scan's API does not change.** day1 reads server-scan with the
  viewer token it already holds (§4). The one write is a server's
  maintenance on and off, with server-scan's admin token, behind Wingman's
  admin check (§8.5).
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
  maintenance toggle (§8.4).

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
  Wingman has built, so no entry leads nowhere: **Sites**, and since 3.23.0
  **Servers**.
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
date and time), and **`DELETE`** on the same path, answer the server's new
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
  record.
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
| 422 | `VALIDATION_FAILED` | A reason over 500 characters or an `expected_end` that is not a date and time; or server-scan refused the body (its `422`) |
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

## 9. Left for later pages

In single-pane §4's order; each is its own PR, with its section in this note.

| Page | server-scan reads (token) | What Wingman adds |
|---|---|---|
| Server detail | `GET /api/v1/servers/{id}`, `/vm-host` (viewer); History: `/servers/{id}/events` (auditor) | The full detail (day1 parses 3 fields today), five tabs; the auditor token |
| Confs | `GET /api/v1/confs` (viewer) | Read only |
| Rules & Policies | `GET /api/v1/classification-rules`, `/health-policies` (viewer) | Read only |
| Events | `GET /api/v1/events`, `/events/actors` (auditor) | Filters and cursor pages |
| Jobs | `GET /api/v1/jobs`, a run's pod logs, `POST /jobs/{cronjob}/run` (admin) | "Run now" behind the admin check, its confirmation, Wingman's audit |
| Architecture | none | server-scan's diagrams, framed from its UI (`SERVER_SCAN_UI_URL`) |
| Claude | none | A link out: server-scan mints the personal token only for its own login |
