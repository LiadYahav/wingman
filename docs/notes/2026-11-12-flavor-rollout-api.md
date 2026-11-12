# A flavor reaches each cluster through its own MR: the API the web reads (2026-11-12)

A flavor's changes reach each cluster through that cluster's own merge
request, and the customer takes it when ready; a cluster is measured
against the flavor version it is on, not the newest (ADR-0044, the user's
decision of 2026-11-12). Importing clusters into a flavor
(`2026-11-12-import-mr-per-cluster.md`) is the same engine. This note is
the contract between day1 and the web: every new or changed field and
endpoint. Paths are relative to the day1 service; errors are RFC 9457
problems as before.

## 1. Each cluster is measured against its own version

A linked cluster's header names a flavor and a version (`# specName`,
`# specVersion`). Drift (ADR-0036) now compares the file with **that
version** of the flavor, read from the specs repo's history, and missing
add-ons with the add-ons **that version** lists. A newer version is never
drift: it is an **update**.

- `state` keeps its values (`in_sync`, `drifted`, `unknown`,
  `not_linked`) and its meaning, against the cluster's own version.
- `unknown` also when the header names no version, or a version the specs
  repo's history does not have (`error` says which). Never `in_sync`.
- New field **`update`**: `null` when the cluster is on the flavor's newest
  version (or the newest cannot be read), else
  `{"version": "<newest>", "merge_request": MergeRequestLink | null}`:
  the open MR that moves this cluster to that version, if there is one.
- `MergeRequestLink` is `{"repo": "day1", "iid": 12, "title": "...", "web_url": "..."}`.

Where:

| Endpoint | Change |
|---|---|
| `GET /clusters/{name}/drift` | `value_drift` and `addon_drift` against the cluster's own version; `current_spec_version` stays the newest; new `update` |
| `GET /clusters/drift-summary` (each row) | new `spec_name`, `spec_version`, `update` |
| `GET /specs/{name}/clusters` (each row) | new `spec_version`, `update` |
| `GET /specs/{name}/drift` (each row) | new `update` |

What a page shows, in this order: `drifted` → "Drifted" (against vN);
`unknown` → "Unknown" (`error`); `update.merge_request` → "Update MR open
(vN → vM)" linking to the MR's review page; `update` → "Update available
(vN → vM)"; otherwise "In sync · vN". `not_linked` → "No flavor".

## 2. A new flavor version opens one MR per cluster, automatically

When a new version of a flavor lands on the specs repo's main, day1 opens,
for every cluster that follows the flavor and is on an older version, one
day1 MR that syncs it to the new version: every locked value and machine
config the new version fixes, and the header's `specVersion` (the same
change as a sync, ADR-0037). Nothing changes on a cluster until its MR
merges; each customer merges theirs when ready.

- **When:** right after Wingman merges the flavor's MR (approve), when the
  specs project's webhook reports a push or merge, when an admin presses
  Reconcile (`POST /specs/{name}/rollout`), and whenever the rollout status
  is read and work is pending (the fallback). Every path is the same
  idempotent reconcile.
- **Each MR:** title `[Wingman/Day1] Sync cluster <name> to spec <flavor>
  v<version>` (as a sync), branch `platform/rollout/<flavor>/v<version>/<cluster>`
  (one per flavor, version and cluster, so a second run or a second pod
  finds it instead of opening another), labels `wingman`, `day1`, `sync`,
  `rollout`, author `system:wingman-rollout`. Its description says what it
  does to that cluster: the values and configs it sets, the configs it
  removes, the nodepools whose nodes roll and how.
- **Add-ons the new version needs:** where the version lists add-ons the
  cluster does not have, day1 asks day2 to open their install MRs first
  (one per team, as a bulk install), and the day1 MR's description links
  them. Day2 down or refusing is noted in the description; the day1 MR
  still opens.
- **Superseded:** a cluster with an open sync MR to an older version of the
  flavor gets the new MR, then the old one is commented on ("superseded by
  !N") and closed.
- **Needs a decision:** a cluster the sync cannot change without a person
  (a nodepool's hardware, a position the file does not have, a file
  Wingman cannot edit) gets no MR; it is listed with the reason, and a
  person syncs it by hand from its page.
- **Declined:** a customer who closes their rollout MR has declined that
  version; no new MR opens for it. A person can still sync it by hand.
- **Unconfirmed writes** (ADR-0006) are never resent blindly: the next run
  checks the cluster's branch and MR first. Once GitLab stops answering, a
  run starts no more MRs.

### `GET /specs/{name}/rollout` (any session)

The rollout of the flavor's newest version, from GitLab's state (the
cluster files and the open and closed MRs), plus whether this replica is
opening MRs now. Reading it starts a reconcile when work is pending.

```json
{
  "spec_name": "agent-baseline",
  "version": "1.1.0",
  "running": false,
  "last_run": {"trigger": "merge", "started_at": "2026-11-12T10:15:00+00:00", "finished_at": "2026-11-12T10:15:09+00:00", "opened": 12, "failed": 0},
  "counts": {"on_version": 3, "merge_request_open": 12, "pending": 0, "needs_decision": 1, "declined": 0, "failed": 0, "unknown": 0},
  "clusters": [
    {
      "name": "ocp4-prod-lark-site1", "site": "site1", "mce": "ocp4-prod-mce-site1-a",
      "path": "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-lark-site1.yaml",
      "from_version": "1.0.0",
      "state": "merge_request_open",
      "merge_request": {"repo": "day1", "iid": 12, "title": "[Wingman/Day1] Sync cluster ocp4-prod-lark-site1 to spec agent-baseline v1.1.0", "web_url": "..."},
      "reasons": []
    }
  ]
}
```

- `version`: the flavor's newest version; `null` (and `clusters` empty)
  when the flavor cannot be read.
- `state`, per cluster that follows the flavor:
  - `on_version`: its header is on `version`;
  - `merge_request_open`: an open MR syncs it to `version` (`merge_request`);
  - `pending`: an MR will open (the next run, or the one running);
  - `needs_decision`: no MR will open until a person syncs it; `reasons`;
  - `declined`: its MR for `version` was closed without merging (`merge_request`);
  - `failed`: this replica's last attempt failed (`reasons`); the next run
    tries again, after checking its branch and MR;
  - `unknown`: its file cannot be read (`reasons`).
- `last_run`: this replica's last run for the flavor (`trigger` is
  `merge`, `webhook`, `reconcile` or `read`), or `null`.

### `POST /specs/{name}/rollout` (admins)

Reconcile now, even after recent failures: `202` with the status above
(`running` is `true` when there is work).

### `GET /approvals/{iid}/rollout?repo=specs` (any session)

Before a flavor MR is merged: what merging it will open. Merging it is the
one confirmation; each cluster MR repeats what it does to its cluster.

```json
{
  "applies": true,
  "reason": null,
  "spec_name": "agent-baseline",
  "version": "1.1.0",
  "current_version": "1.0.0",
  "following": 16,
  "opens": 12,
  "already_on_version": 0,
  "needs_decision": [{"name": "...", "site": "...", "mce": "...", "reasons": ["nodepool[1].configs: ..."]}],
  "rolls_nodes": [{"name": "...", "site": "...", "mce": "...", "nodepools": [{"name": "...", "replicas": 3, "replaces_nodes": false, "max_unavailable": null}]}],
  "removes_configs": [{"name": "...", "site": "...", "mce": "...", "removals": [{"nodepool": "...", "name": "restored-example-config"}]}],
  "adds_addons": ["redbull/cluster-roles"]
}
```

`applies` is `false` (with `reason`) for an MR that does not give an
existing flavor a new version: a new flavor, a deletion, a file that does
not parse. `adds_addons` are the add-ons the MR's version lists and
main's does not.

## 3. Saving a flavor needs a new version

`PUT /specs/{name}` refuses (422, `details.problems`) an edit that keeps
the current version or reuses an earlier one: a version, once saved, never
changes, because clusters are measured against it.

```
metadata.version: 1.0.0 is the current version; an edit needs a new one, which reaches each cluster through its own merge request
metadata.version: 0.9.0 was used before; a version never changes once saved
```

## 4. A sync that is already open

`POST /clusters/{name}/sync` refuses (409 `ALREADY_EXISTS`) when an open MR
already syncs the cluster to the flavor's newest version; the detail names
it. A sync to the newest version closes an open sync to an older version
of the flavor, as a rollout does.
