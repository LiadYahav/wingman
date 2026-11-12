# ADR-0036: Day1 drift is the flavor's locked values the file does not hold, and its missing add-ons

Date: 2026-11-08
Status: Accepted (supersedes in part ADR-0016 and ADR-0025); superseded in part by ADR-0044 (a cluster is compared with the flavor version it is on)

Since ADR-0044 (2026-11-12) drift compares a linked cluster with the flavor
as it was at the version its header names, read from the specs repo's
history, and missing add-ons with that version's list: a newer version is
an update, never drift. A header with no version, or one history does not
have, is unknown. What is compared, and how, is unchanged.

## Context

ADR-0016 made drift add-on drift only: Wingman stored no render inputs, so
it could not re-render a cluster to compare files, and the file
legitimately changes after create. ADR-0025 narrowed that to a missing
add-on. Flavors v2 makes a lock a fixed value (ADR-0026, user decision
2026-11-08) and adds that "a later edit that changes a locked value shows as
drift". A locked value is one the flavor states and the cluster file holds,
so it can be compared without re-rendering anything: `LOCKABLE` maps each
lockable template input to the file key the shared template writes it to.

## Decision

**Two things make a linked cluster `drifted`**: value drift, or a missing
add-on (ADR-0025's rule, unchanged). Version differences are still only
reported.

**Value drift** is each enforced lock of the flavor (`ClusterSpec.locks()`)
whose value the cluster file does not hold at the lock's file key. *(Since
ADR-0044: the flavor at the cluster's own version, not its newest.)* Values
compare in the file's form:

| Lock | File key | Compared |
|---|---|---|
| `owner_*` | `owner.*` | as text; a whole number in the file equals its digits (`42` is `"42"`, not `"0042"`) |
| `platform` | `platform` | `kubevirt`, or the Agent default; a file without the key is Agent |
| `nodepools[i].replicas` | `nodepool[i].replicas` | as numbers; a missing key drifts |
| `nodepools[i].node_labels` | `nodepool[i].nodeLabels` | as a mapping; no key equals `{}` |
| `nodepools[i].configs` | `nodepool[i].configs` | by name, each as often, in any order (ADR-0029); `{name: nm-conf, hardware: hw}` is `nm-conf-<clusterName>-<hw>` |
| `nodepools[*].configs` | every `nodepool[i].configs` | the same, with each nodepool's own network config |

`clusterName` is the chart's: an explicit `clusterName` key wins over the
file name (ADR-0015). Only the cluster file is compared, not the merged
value layers: the lock fixes what the file says.

Each item gives the lock path, the file key, the flavor's value (in the
file's form) and the cluster's (or that the key is absent), the nodepool
(position and the NodePool name the chart renders) and, for configs, the
names a sync would add and remove.

**Presets never drift.** Only locks are compared; overriding a preset is
allowed.

**Some drift needs a person.** Where a nodepool's hardware is its own (the
rule, or a stored lock with no hardware) it is read from the one config name
a hardware template captures. A nodepool with none or several, a position
the file does not have (`nodepool[1]` of a one-nodepool file), or a nodepool
that is not a mapping, is drift with `needs_decision` saying why. Wingman
never guesses: a wrong network config breaks a node's networking.

**Unknown is never in sync.** A linked cluster is `unknown` when its file
does not parse, its flavor is gone or unreadable, or day2 does not answer
and nothing else drifted. When values drifted and day2 did not answer, the
cluster is `drifted` (that much is known) and `error` says the add-on part
is unknown.

**For import**, the same comparison runs against a flavor the file does not
name yet (`DriftService.against`).

## Alternatives rejected

- **Re-render the template and diff the files**: the inputs are not stored,
  and CI, the allocate-segment workflow and people change the file after
  create by design (ADR-0016).
- **Compare the merged value layers**: the lock fixes the cluster file;
  what an MCE layer sets is the MCE's, not the flavor's.
- **Compare presets too**: a preset is a starting value, not a promise.
- **Day2 down makes every cluster `unknown`**: a cluster whose locked values
  differ has drifted whatever day2 says; hiding it helps nobody.

## Consequences

- `GET /clusters/{name}/drift` gains `value_drift`; a cluster created from a
  flavor and edited by hand where it is locked shows as `drifted`.
- Day1 drift reads the machine-config catalogue (for the hardware types)
  beside the specs; both are cached reads (ADR-0011).
- Sync (ADR-0037) fixes exactly the value drift that needs no decision.

## Verification

- `apps/day1-service/tests/unit/domain/test_value_drift.py`: every row of
  the table, the multiset comparison, network configs read per nodepool,
  none or several needing a person, a person's choice, positions the file
  does not have.
- `apps/day1-service/tests/unit/application/test_drift.py`: presets never
  drift, a locked value edited later drifts, imported fixture clusters,
  day2 down with and without value drift, an unparsable linked file.
- `apps/day1-service/tests/api/test_flavor_links_api.py`: the `value_drift`
  JSON.
