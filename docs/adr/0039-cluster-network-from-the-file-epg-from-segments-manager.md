# ADR-0039: A cluster's network is read from its file; segments-manager adds the EPG and is checked against Git

Date: 2026-11-11
Status: Accepted

## Context

The cluster page's **HostedCluster & network** card showed `vlanId` and
`dhcp_values.network` from the cluster file, and from 3.4 linked to
segments-manager without calling it. The team also wants the segment's ACI
EPG, which only segments-manager records
(`docs/ecosystem/notes/segments-manager.md` §2).

The allocate-segment workflow allocates a segment in segments-manager and
writes `vlanId` and `dhcp_values.network` into the cluster file on the MR
branch (`docs/ecosystem/README.md`, the create flow). The two can disagree
afterwards: a hand edit of the file, a segment released or re-allocated
by hand, a VLAN changed in segments-manager. The user decided (2026-11-11):
**Git is the source of truth for clusters**; the VLAN and the segment come
from the file, and the EPG from segments-manager.

segments-manager's segments are always /24, and its open
`GET /api/segments/by-segment?segment=<cidr>` answers one segment, or 404
for an unknown one (also for a CIDR that is not a /24). Its `cluster_name` is
the cluster file's stem (ADR-0014), a list for a shared `UPI` segment.

## Decision

- **The VLAN and the segment are the file's.** The segment is
  `<dhcp_values.network>/24`, only when the network is a /24's network
  address (`wingman_day1.domain.network.segment_of`); the detail's
  `values.network` carries it as `segment`.
- **segments-manager is a port** (`SegmentLedger.segment(cidr)`), with an
  httpx adapter that calls `by-segment` and nothing else, a fake, and a
  per-replica cache (ADR-0011). A 404 is "no such segment", an answer that is
  cached like a record; any other failure is
  `SegmentsManagerUnavailableError`, which is not cached. It is counted as
  `dependency="segments_manager"`, `operation="get_segment"` (ADR-0010).
- **It adds the EPG and warnings, never values.** `GET /clusters/{name}/network`
  returns the file's `vlan_id` and `segment`, segments-manager's `epg_name`,
  its record, and `problems`: what it says that disagrees with the file, in
  plain words. The checks (`wingman_day1.domain.network.disagreements`):
  - segments-manager has no such segment;
  - its `status` is not `Allocated` (then the holder is not checked: an
    Available segment holds nobody);
  - it names another cluster than the file's stem, or a shared list without it;
  - its `vlan_id` differs from the file's `vlanId` (or the file has none).
- **It never fails the read.** Off (`SEGMENTS_MANAGER_URL` empty): the
  ledger part is `null`, with no error. Failing: `null` with `ledger_error`.
  The route reads the file only (not its history) and never the MCE.
- **Nothing is written to segments-manager.** Allocation and release stay
  the workflows' (`docs/ecosystem/README.md`).
- `SEGMENTS_MANAGER_UI_URL`, the links' base since 3.4, defaults to
  `SEGMENTS_MANAGER_URL`, the way `SERVER_SCAN_UI_URL` defaults to
  `SERVER_SCAN_URL`.

## Alternatives rejected

- **segments-manager as the source of the VLAN and the segment.** It is
  what the workflow allocated, but ArgoCD applies the file: the file is
  what the cluster runs with. Showing segments-manager's values would hide
  exactly the disagreement worth seeing.
- **Fixing a disagreement from Wingman** (an MR to the file, or a write to
  segments-manager). Which side is right needs a person; segments-manager's
  writes need the workflow worker's token, and Wingman holds none.
- **Searching by cluster name** (`GET /api/segments/search?q=`). It matches
  substrings, so it can answer another cluster's segment; the file's segment
  is the natural key.
- **The EPG in the cluster detail.** The detail would wait on
  segments-manager on every page load, and fail or slow with it; a separate
  route lets the card read it lazily.

## Consequences

- A cluster's card shows the EPG once `SEGMENTS_MANAGER_URL` is set
  (chart: `segmentsManager.url`). A running 3.4 sets it with
  `docs/upgrade/3.4-to-3.5.md`; the 3.4 `segmentsManager.uiUrl` keeps working.
- The page can show a warning for a cluster that runs fine: it is a
  disagreement to look at, not an outage.
- With `DAY1_FAKE_FLEET`, a fake ledger from `dev/fleet-fixtures/segments.yaml`
  serves the demo, with one deliberate VLAN mismatch (herzi). The fixture
  cluster files that had `dhcp_values` without `vlanId` gained one, as the
  workflow writes both.

## Verification

- `apps/day1-service/tests/unit/domain/test_network.py`: the segment, the
  VLAN and every check.
- `apps/day1-service/tests/unit/infrastructure/test_segments_manager.py`: the
  one call, 404 as `None`, failures as unavailable, the cache, the metrics, and
  the demo ledger agreeing with the fixture files except herzi.
- `apps/day1-service/tests/api/test_cluster_network_api.py`: the route's shape
  with segments-manager off, on, failing, and disagreeing.
- `tests/repo/test_chart_env_contract.py`: the chart sets the new variables, and
  values reused from 3.4 still render.
- `apps/web/e2e/tests/cluster-network.spec.ts`: the card.
