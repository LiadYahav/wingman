# The Server Scan area: the API the web reads (2026-11-13)

The **Server Scan** area (`/server-scan`) is server-scan's UI rebuilt in
Wingman, one page at a time (workstream 4 of `docs/ideas/single-pane.md`,
decision 22, ADR-0048). This note covers the area and its first page,
**Sites**. Each later page adds its section here (§8 lists them).

- **server-scan's API does not change, and nothing is written to it.** day1
  reads server-scan's `GET /api/v1/sites` with the viewer token it already
  holds (§4).
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
  person's name. Each is its own Secret key, read by day1 only, added with
  the page that needs it (§8).

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
  Wingman has built, so no entry leads nowhere: today **Sites**.
  `apps/web/lib/server-scan/sidebar.ts` lists them; a new page is one entry.
- **The Sites page**: §1's cards, counts and words in Wingman's design (its
  colour tokens, light and dark). **The counts are not links yet**: the
  Servers page they open does not exist. Each card and count carries the
  filter it will open, in server-scan's parameter names (`data-filter`), so
  the Servers PR turns them into links in one place.
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

## 8. Left for later pages

In single-pane §4's order; each is its own PR, with its section in this note.

| Page | server-scan reads (token) | What Wingman adds |
|---|---|---|
| Servers | `GET /api/v1/servers/rows` (viewer), `GET /api/v1/sites` for the site filter | The shared fleet-rows cache and its `ETag`, served to the page as it is; every row field (day1 parses 18 of 22 today); filters, facets, search and paging in the browser from server-scan's pure TS and its tests, in the URL in server-scan's parameter names; the shared table; a sidebar of MCEs, hosted clusters and UPI clusters; the Excel export; the maintenance toggle (admin token, Wingman's audit). The Sites counts become links |
| Server detail | `GET /api/v1/servers/{id}`, `/vm-host` (viewer); History: `/servers/{id}/events` (auditor) | The full detail (day1 parses 3 fields today), five tabs; the auditor token |
| Confs | `GET /api/v1/confs` (viewer) | Read only |
| Rules & Policies | `GET /api/v1/classification-rules`, `/health-policies` (viewer) | Read only |
| Events | `GET /api/v1/events`, `/events/actors` (auditor) | Filters and cursor pages |
| Jobs | `GET /api/v1/jobs`, a run's pod logs, `POST /jobs/{cronjob}/run` (admin) | "Run now" behind the admin check, its confirmation, Wingman's audit |
| Architecture | none | server-scan's diagrams, framed from its UI (`SERVER_SCAN_UI_URL`) |
| Claude | none | A link out: server-scan mints the personal token only for its own login |
