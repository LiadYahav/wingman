# ADR-0029: A flavor can lock every nodepool's configs as one rule, compared exactly by name

Date: 2026-11-08
Status: Accepted

## Context

A flavor lock is a fixed value (ADR-0026, user decision 2026-11-08), and
stage 1 locks by position: `nodepools[0].configs` is the first nodepool of
the create request. That is enough for a cluster the flavor creates, whose
nodepools come from the flavor's form. It means nothing on a cluster the
flavor did not create: flavors v2 imports existing clusters into a flavor,
and an existing file has any number of nodepools in any order, so "the first
nodepool" is whichever someone wrote first. The team's real requirement is a
property of every nodepool: each has its network config (`nm-conf`, for that
nodepool's own hardware), `workers-chrony-configuration` and
`nic-ring-buffer`.

## Decision

**A rule path.** The path grammar gains `[*]`, "every position":
`index := "0" | [1-9][0-9]{0,2} | "*"`. `nodepools[*].configs` is lockable
(file key `nodepool[*].configs`): every nodepool of the cluster has exactly
these configs. It is the only rule; replicas and node labels stay positional
(below).

**Its value is what the flavor's nodepools set.** The rule's value is the
`configs` of every nodepool in `spec.day1.values.nodepools`, which must
agree. A save refuses the rule when there are no nodepools, when one sets no
configs, when two name different configs, or when the configs do not list
`nm-conf` exactly once: a rule without it would remove every nodepool's
network config. A position cannot lock configs beside the rule
(`nodepools[0].configs` with `nodepools[*].configs` is refused at save; a
stored spec with both enforces the rule only).

**Compared by name, in any order, exactly.** Two config lists match the rule
when they name the same configs, each as often, in any order. Order is not
compared: a MachineConfig applies by name, the CI renders one ConfigMap per
name (`mcFiles` is first-seen order), and reordering alone would roll the
nodes for nothing. The comparison is **exact**, not a subset: a nodepool
with a config the rule does not list has drifted, and syncing it removes
that config. The user's decision is that a lock is a fixed value; a subset
would let extra configs (a copied `legacy/` config, another cluster's
network config) accumulate unseen, and drift would never report them. The
cost is that sync removes configs, which reboots nodes and may drop
something a team relies on; ADR-0037 makes every removal explicit in the
preview, the confirmation and the MR.

**`nm-conf` is each nodepool's own.** In the rule, `nm-conf` matches any
hardware type: each nodepool keeps its own. The hardware of the flavor's
`nm-conf` entries stays a per-nodepool preset for create. On an existing
cluster the hardware is read from the nodepool's network-config entry: the
one config name a hardware template captures (`nm-conf-<clusterName>-<hw>`,
by the CI's longest-suffix rule, ADR-0027). A nodepool with none, or with
several, needs a person to choose the hardware; Wingman reports it and never
guesses (ADR-0036).

**At create.** A nodepool that sends configs must match the rule (by name, in
any order, `nm-conf` with any known hardware); otherwise the create is a 422
naming the nodepool. A nodepool that sends none gets the rule's entries, and
the config check then asks for its `nm-conf` hardware. Positional locks keep
working as in ADR-0026, compared exactly as JSON.

## Alternatives rejected

- **Subset ("at least these configs")**: drift could not see a config that
  should not be there, and the lock would no longer be a fixed value.
- **Order-sensitive comparison**: an imported file listing the same configs
  in another order would drift, and syncing it would roll every node to
  change nothing.
- **The rule's value in a field of its own** (`spec.day1.rules`): a second
  place for a locked value, and the flavor's own nodepools could then
  disagree with it.
- **Rules for replicas and node labels**: a replica count is each
  nodepool's own total (capacity moves through totals, and the scale
  workflow will own it), and node labels often carry per-pool facts such as
  the zone, which a fleet-wide rule would erase.
- **Guess the hardware of a nodepool without one network config** (from the
  InfraEnv name, or the first match): a wrong network config breaks the
  node's networking on its next reboot.

## Consequences

- An imported cluster can follow a flavor's machine configs whatever the
  number and order of its nodepools; `agent-baseline` is the fixture
  flavor that does.
- The flavor editor offers "lock configs on every nodepool": one config list
  for all the flavor's nodepools, with a hardware type per nodepool as a
  preset. Its paths are those of `docs/notes/2026-11-08-flavors-v2-api-changes.md`.
- Problems may now name `nodepools[*].configs`.

## Verification

- `apps/day1-service/tests/unit/domain/test_locks.py`: the `[*]` grammar
  (with the round-trip property test), the rule's file key, its save rules,
  the overlap with a position, enforcement at create and the fill.
- `apps/day1-service/tests/unit/application/test_flavor_rules.py`: creates
  from `agent-baseline` in any order and hardware, a nodepool that breaks
  the rule, one that sends none, and a rule whose nodepools disagree.
