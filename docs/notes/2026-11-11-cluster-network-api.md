# A cluster's network: the API the web reads (2026-11-11)

The cluster page's **HostedCluster & network** card shows the cluster's
VLAN and segment from its file, and the EPG segments-manager records for
that segment, with what segments-manager says that disagrees with the file
(ADR-0039). Git is the source of truth: the values shown are always the
file's.

## 1. The detail carries the segment

`GET /api/day1/clusters/{name}`: `values.network` gains `segment`, the
file's `dhcp_values.network` as its /24.

```json
"network": {"vlan_id": 412, "dhcp_network": "10.20.90.0", "segment": "10.20.90.0/24"}
```

`segment` is `null` while the allocate-segment workflow has not written
`dhcp_values`, and when the network is not a /24's network address
(`10.20.90.5`): Wingman does not guess. `vlan_id` stays the file's raw value.

## 2. `GET /api/day1/clusters/{name}/network?site=&mce=`

Any signed-in user. `site` and `mce` are optional, as for the detail (names
are unique). It reads the cluster file only, never its history and never
the MCE, so it answers with live status off.

```json
{
  "vlan_id": 412,
  "segment": "10.20.90.0/24",
  "epg": "EPG_site2_HC_412",
  "ledger": {
    "vlan_id": 413,
    "cluster_name": "ocp4-prep-amit-site2-a",
    "status": "Allocated",
    "type": "HC",
    "site": "site2"
  },
  "problems": ["segments-manager has VLAN 413 for this segment; the file has 412"],
  "ledger_error": null
}
```

| Field | Meaning |
|---|---|
| `vlan_id` | The file's `vlanId`, as a number; `null` when the file has none (or not a number) |
| `segment` | The file's segment, as in §1; `null` until it is allocated |
| `epg` | segments-manager's `epg_name` for `segment`; `null` when it is off, failed or has no such segment |
| `ledger` | segments-manager's record of `segment`. `cluster_name` is a list for a shared `UPI` segment, `null` for an Available one |
| `problems` | What segments-manager says that disagrees with the file, one sentence each (below). Empty when it agrees, is off or failed |
| `ledger_error` | Why segments-manager could not be read, e.g. `SegmentsManagerUnavailable: segments-manager answered 503 reading segment 10.20.90.0/24`; never fails the read |

How the web tells the cases apart:

| Case | `ledger` | `problems` | `ledger_error` |
|---|---|---|---|
| segments-manager off (`SEGMENTS_MANAGER_URL` empty) | `null` | `[]` | `null` |
| No segment in the file yet | `null` | `[]` | `null` (nothing is asked) |
| It agrees | the record | `[]` | `null` |
| It disagrees | the record | the sentences | `null` |
| It has no such segment | `null` | `["segments-manager has no segment 10.20.90.0/24"]` | `null` |
| It failed | `null` | `[]` | the reason |

The problems, in the order they are listed:

- `segments-manager has no segment <segment>`;
- `segments-manager marks this segment <status>, not Allocated` (then the
  holder is not checked: an Available segment holds nobody);
- `segments-manager allocated this segment to <other>, not to <name>`, or for
  a shared segment `segments-manager shares this segment among <a, b>, not
  with <name>`. The holder is compared with the file's stem (`name`), the
  `cluster_name` allocate-segment gives segments-manager, not with the
  chart's `clusterName`;
- `segments-manager has VLAN <n> for this segment; the file has <m>` (or
  `the file has no vlanId`).

Errors: `404 NOT_FOUND` for an unknown cluster, `401` without a session.
segments-manager's failures are never a problem response.

## 3. Settings (day1)

| Variable | Default | Meaning |
|---|---|---|
| `SEGMENTS_MANAGER_URL` | empty (off) | segments-manager's API, e.g. `http://segments-manager.<ns>.svc:8000`. Day1 calls only its open `GET /api/segments/by-segment?segment=<cidr>`, with no token, and caches the answer per replica (`DAY1_CACHE_TTL_SECONDS`) |
| `SEGMENTS_MANAGER_UI_URL` | `SEGMENTS_MANAGER_URL` | Where the card's links point (the cluster nodes note's §5); both empty: no link |
| `SEGMENTS_MANAGER_SSL_VERIFY` | `true` | `true`, `false`, or a CA bundle path |
| `SEGMENTS_MANAGER_TIMEOUT_SECONDS` | `5` | Per request, at most 60 |

Chart: `segmentsManager.url`, `.uiUrl`, `.sslVerify`, `.timeoutSeconds`.
`DAY1_FAKE_FLEET=true` serves a fake ledger from
`dev/fleet-fixtures/segments.yaml` instead (development only).

## 4. The card

- **VLAN**: the detail's `values.network.vlan_id`, **pending** when the file
  has none.
- **Segment** (was "DHCP network"): the detail's `values.network.segment`,
  **pending** when the file has none.
- **EPG**: this route's `epg`. A skeleton while it loads, "—" when there is
  none (segments-manager off, no segment yet, or none recorded), and
  **unknown** with `ledger_error` when segments-manager failed.
- `problems` as a quiet warning list under the rows.
- The links to segments-manager stay as they were.

The card reads this route lazily, with the page: the detail does not wait
on segments-manager.
