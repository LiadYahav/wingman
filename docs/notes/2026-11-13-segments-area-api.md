# The Segments area: the API the web reads (2026-11-13)

The **Segments** area (`/segments`) is segments-manager's read-only page
rebuilt in Wingman's own design: per-site cards, then every segment in one
table, with the original's columns and words (workstream 3 of
`docs/ideas/single-pane.md`, ADR-0047). It was built as an **alpha**
(3.15.0); since 3.21.0 it does everything the original's page does (the
user's decision 22, ADR-0047's second amendment): §7 lists the alpha's cuts,
now built, and what is still not here.

- **segments-manager's API does not change, and nothing is written to it.**
  day1 calls four of its open GETs (`/api/sites`, `/api/stats`,
  `/api/segments`, and `/api/segments?fresh=true` for Refresh); none needs a
  token. Allocation and release stay the workflows'.
- **The browser never calls segments-manager.** It reads day1's routes below,
  which type segments-manager's untyped answers.
- **Admins only** (decision 13 of the single-pane plan, until RBAC): every
  route takes `AdminUser`, so a viewer gets `403 FORBIDDEN` and an anonymous
  call `401`. The web shows the area to admins only.
- **Off without segments-manager.** With `SEGMENTS_MANAGER_URL` empty (chart:
  `segmentsManager.url`) every route answers `501 FEATURE_DISABLED`, as the
  other optional features do, and the web hides the area. With
  `DAY1_FAKE_FLEET=true` (development only) a fake ledger from
  `dev/fleet-fixtures/segments.yaml` answers.
- **segments-manager failing** is `502 DEPENDENCY_UNAVAILABLE` on these routes
  only. It never fails a cluster read: the cluster page's network card keeps
  ADR-0039's behaviour (`ledger_error`, the file's values shown).

## 1. `GET /api/day1/segments/sites`

segments-manager's site list (its `SITE_NETWORKS` keys), in its order. A
site may have no segments yet.

```json
{"sites": ["site1", "site2", "site3"]}
```

## 2. `GET /api/day1/segments/stats`

segments-manager's `GET /api/stats`, typed: one entry per site of §1, in that
order, sites without segments included.

```json
{
  "sites": [
    {
      "site": "site1",
      "total_segments": 12,
      "allocated": 10,
      "by_type": [
        {"type": "HC", "allocated": 6},
        {"type": "MCE", "allocated": 1},
        {"type": "INVENTORY", "allocated": 1},
        {"type": "PXE", "allocated": 1},
        {"type": "UPI", "allocated": 1},
        {"type": "HUB", "allocated": 0}
      ]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `total_segments` | Every segment at the site, Available or Allocated; `0` for a site without segments |
| `allocated` | Those Allocated. Free is `total_segments − allocated` |
| `by_type` | Allocated segments per type, in segments-manager's order (it lists every type, at 0 too). A plain count, never "x of y": an Available segment has no type, so a type has no total of its own. The card shows only the types above 0 |

## 3. `GET /api/day1/segments`

Every segment segments-manager records, with who holds it as Wingman knows
it. The web reads it unfiltered and filters in the browser (§5); the
filters below are segments-manager's own, passed through.

| Query | Meaning |
|---|---|
| `site` | One site, as §1 names it (segments-manager compares without case) |
| `status` | `Available` or `Allocated`; anything else is `422` |
| `type` | `HC`, `MCE`, `INVENTORY`, `PXE`, `UPI` or `HUB`; anything else is `422`. Only an Allocated segment has a type, so a type never matches an Available one |
| `fresh` | `true`: read segments-manager's database now (its Refresh button). day1 drops its own cached segments-manager answers, and segments-manager its 60-second cache. At most once per `5` seconds per day1 replica: a `fresh` read inside that window is answered from the cache the last one filled, and says so (`fresh: false`) |

```json
{
  "segments": [
    {
      "segment": "10.20.44.0/24",
      "site": "site1",
      "vlan_id": 1418,
      "epg_name": "EPG_site1_HC_1418",
      "dhcp": true,
      "status": "Allocated",
      "type": "HC",
      "cluster_name": "ocp4-prod-herzi-site1",
      "allocated_at": "2026-10-05T14:01:22+00:00",
      "holders": [
        {"name": "ocp4-prod-herzi-site1", "day1": {"site": "site1", "mce": "ocp4-prod-mce-site1-a"}}
      ],
      "mismatches": [
        {
          "cluster": "ocp4-prod-herzi-site1",
          "site": "site1",
          "mce": "ocp4-prod-mce-site1-a",
          "detail": "segments-manager has VLAN 1418 for this segment; the file has 1410"
        }
      ]
    },
    {
      "segment": "10.20.60.0/24",
      "site": "site1",
      "vlan_id": 1460,
      "epg_name": "EPG_site1_UPI_1460",
      "dhcp": false,
      "status": "Allocated",
      "type": "UPI",
      "cluster_name": ["ocp4-upi-a", "ocp4-upi-b"],
      "allocated_at": "2026-09-14T08:00:00+00:00",
      "holders": [
        {"name": "ocp4-upi-a", "day1": null},
        {"name": "ocp4-upi-b", "day1": null}
      ],
      "mismatches": []
    }
  ],
  "unreadable": [],
  "clusters_error": null,
  "fresh": false
}
```

| Field | Meaning |
|---|---|
| `segments` | In segments-manager's order. `segment` (the CIDR) is the key: unique, never null |
| `site`, `vlan_id`, `epg_name`, `dhcp`, `status`, `type`, `allocated_at` | segments-manager's values, unchanged; any may be `null` on an old record. A `null` status is shown as Available, as segments-manager's UI does. `allocated_at` stays set after a release (segments-manager never clears it) |
| `cluster_name` | segments-manager's holder: one name, a list for a shared `UPI` segment, `null` while Available |
| `holders` | The same names, one entry each, in order. `day1` is where that name's cluster file is in the day1 repo (exactly one file with that stem): the web links it to Wingman's cluster page. `null` for any other holder (an MCE, a UPI cluster, a name day1 does not have, or one two files share) |
| `mismatches` | Where segments-manager disagrees with a cluster file, ADR-0039's checks seen from the segment (§4). Empty when they agree, or when nothing in Git describes this segment |
| `unreadable` | Records segments-manager sent that Wingman could not read (a missing `segment`, a VLAN that is not a number), one sentence each. They are not in `segments`; the rest are |
| `clusters_error` | Why day1's cluster files could not be read (GitLab down): every holder is then `day1: null` and `mismatches` is empty. The segments are still listed |
| `fresh` | `true` when this answer was read from segments-manager's database just now |

## 4. Mismatches (ADR-0039's checks, from the segment's side)

Computed from data day1 already holds: this answer and the day1 repo's
cluster files, read once per commit and cached (ADR-0035). No call is added
for them. Git stays the source of truth: the row shows segments-manager's
values, and a mismatch is a warning to look at, never a fix.

- **A cluster file names this segment** (its `dhcp_values.network` as a /24 is
  `segment`): ADR-0039's checks, word for word, as the cluster page shows
  them (`wingman_day1.domain.network.disagreements`): segments-manager marks
  it not Allocated, allocates it to another cluster (or shares it without
  this one), or has another VLAN than the file's `vlanId`.
- **A holder's cluster file names another segment, or none**: `the file has
  segment 10.20.99.0/24, not this one`, or `the file has no segment`.
- Holders that are not day1 clusters (MCEs, UPI clusters) are not checked:
  Git has nothing to compare them with.

`cluster`, `site` and `mce` name the cluster file the mismatch is about, so
the web can link it. A file whose segment segments-manager does not list at
all has no row to mark: the cluster page says it (left for after the alpha:
a list of them on this page).

## 5. The page

`/segments`, reached from the top bar's area switch (Wingman, Segments: plain
links, the current area marked). A viewer has no Segments link, and the page
shows Wingman's "for admins" state; with segments-manager off the switch hides
the area and the page says it is not set up.

- **Site cards**: allocated out of total (`10 / 12 used`), and the allocated
  count of each type above 0. A card filters the table to its site; again
  clears it.
- **The table**, with the original's columns and words: Type, Site, VLAN ID,
  EPG Name, Network Segment, DHCP (On/Off), Cluster, Status. Every column
  sorts. VLAN ID, EPG name and Network segment copy on click (or Enter), with
  a toast. A Cluster cell links each holder whose file is in day1 to
  Wingman's cluster page; any other holder is plain text; a UPI list shows
  each name. A row with mismatches is marked, and its marker lists them.
- **Above it**: status tabs (All, Available, Allocated, each with its count
  under the other filters), the site filter, the search (cluster, EPG, VLAN
  ID, segment or site, as the original), the column picker (kept per
  browser), and **Download N shown as CSV | Excel**: exactly the rows shown,
  after every filter and the search, in the shown order and columns. The
  Excel file (`segments.xlsx`, one sheet "Segments", since 3.21.0) is
  written in the browser from the same table as the CSV: the same rows and
  columns, a VLAN ID as a number, the header row bold and frozen, each
  column as wide as its longest value (at most 50 characters, as the
  original's export). segments-manager's own export endpoints are not
  called: they apply only the status and site, with other columns.
- **A filter on every column** (Excel-style, as the original's headers; since
  3.21.0): each header's funnel opens the column's distinct values, from the
  rows left after the status tab, the site, the holder, "Disagrees with Git"
  and the search (the original's `lastBaseSegments`), each a checkbox, with a
  search among them, select all or none, Apply and Clear. A value is the
  cell's text as shown (DHCP `On`/`Off`, a UPI list's names joined with
  `, `, a record without a status `Available`); an empty cell is `(Blank)`.
  Keeping every value is no filter. Columns combine (a row must pass each),
  an active one marks its funnel and shows a chip that removes it (so a
  filter on a hidden column stays in sight), and the tabs' counts follow.
  Since 3.21.0 the Type column's filter replaces the alpha's Type row.
- **Fresh data**: the page re-reads every 30 seconds while it is open
  (`fresh=false`), and Refresh reads fresh (`fresh=true`, then the cards).
- **The connection dot** (the original's online/offline state; since
  3.21.0), beside "Updated … · every 30 s": green while segments-manager
  answered the last refresh (the 30-second re-read or Refresh, whichever
  came last); red when it did not, its tooltip saying "segments-manager
  didn't answer the last refresh: <reason>; showing the last good data". The
  page keeps showing the last good rows, never a blank table, with the
  failed re-read's problem above them, and keeps re-reading: the next good
  read turns the dot green. No extra call: the original's 10-second
  `/api/health` heartbeat is not copied.
- **Every filter lives in the URL**, so a view can be shared and linked:

| Parameter | Meaning |
|---|---|
| `status` | `available` or `allocated`; absent: All |
| `site` | One site |
| `f.<column>` | A column's filter, one parameter per value kept (`f.type=HC&f.type=UPI`); an empty value is the blank (`f.dhcp=`). `<column>` is a column id (listed under `sort`). Absent: every value |
| `type` | Before 3.21.0, the Type row: types comma-separated (`HC,UPI`). Still read, as the Type column's filter (unless the link has `f.type`); never written |
| `q` | The search |
| `cluster` | Exactly one holder (a UPI list matches if it has it). Shown as a removable chip. The cluster page's link opens `/segments?cluster=<file stem>` |
| `mismatch` | `1`: only rows with a mismatch |
| `sort` | A column id (`type`, `site`, `vlan_id`, `epg_name`, `segment`, `dhcp`, `cluster`, `status`), `-` before it for descending; absent: segments-manager's order |

- **The cluster page.** For an admin with the area on, the HostedCluster
  card's segments link opens `/segments?cluster=<name>`. Everyone else keeps
  the links to segments-manager's UI and to its search for the cluster
  (`segments_manager`, ADR-0039). Both are built by one helper in the web
  (`apps/web/lib/segments/links.ts`), so a link can become Wingman's own page
  in one place.

## 6. Metrics

Four new operations on `wingman_dependency_*` with
`dependency="segments_manager"` (`docs/ops/metrics.md`): `list_sites`,
`get_stats`, `list_segments` and `refresh_segments` (a `fresh=true` read).
Answers are cached per replica for 10 seconds (ADR-0011), so the page's
30-second re-read costs one call per route per replica; a failure is not
cached.

## 7. Left for after the alpha

- **No Excel export.** The CSV opens in Excel.
  *Built in 3.21.0: an Excel file of the rows shown, written in the browser
  (§5, ADR-0047's second amendment).*
- **No connection-status dot.** Wingman's error state replaces it: a failed
  read shows the problem, and the next 30-second re-read clears it.
  *Built in 3.21.0: the dot beside "Updated" (§5).*
- **Never the original's `/api/logs` endpoints** (the raw application log,
  served without a token).
- **No per-column filter popovers.** A Type filter row instead.
  *Built in 3.21.0 (ADR-0047's second amendment): a filter on every column,
  in the URL (§5); the Type row is gone.*
- **No segment detail panel** (the mock's side sheet).
- **Files whose segment segments-manager does not list** are not listed here
  (§4); the cluster page shows them.
- **The area's own sidebar** (workstream 2): `/segments` keeps Wingman's.
  *Done in 3.17.0 (ADR-0047's amendment): Segments has its own sidebar and
  brand.*
