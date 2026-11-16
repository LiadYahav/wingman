# ADR-0061: Tuning profiles come from `tuning/` in the day1 repo; a flavor picks them per nodepool and can lock them as a rule

Date: 2026-11-15
Status: Accepted

## Context

A nodepool can carry node tuning: `nodepool[].tuningConfig` in the cluster
file names one or more OpenShift `Tuned` or `PerformanceProfile` manifests,
and the hostedclusters-setup chart turns each into a ConfigMap the NodePool
references. Until now the manifests themselves sat in each cluster file
under a hand-written `tuningConfigmap:` key, so the same profile was copied
from file to file and drifted, and Wingman offered `tuning_config` only as
free text (a template input of type string).

The user decided (2026-11-15) how this moves forward, and the day1 repo's
CI and Wingman are built in parallel against one contract:

- The catalogue is a folder `tuning/` at the day1 repo's root.
- The CI injects the manifests a cluster's nodepools name into the file's
  `tuningConfigmap`, the way it injects machine configs into `mcConfigMap`
  (ADR-0012, ADR-0027). An existing entry that differs from the catalogue
  is kept and reported by the CI, never overwritten.
- In Wingman a person selects profiles per nodepool in a flavor and at
  create, and a flavor can lock them.

## Decision

**The catalogue.** `GET /api/day1/tuning-profiles` lists what `tuning/`
offers. Day1 reads it through `GitLabPort` as part of the day1 repo's
snapshot (ADR-0035): one recursive tree listing and the files' contents,
cached like every other read (ADR-0011, ADR-0041), never written. The
machine-config service reads it beside `mc-files/`, so every use case that
already has the config catalogue reaches it without a new dependency.

- `tuning/<name>.yaml` is a **shared profile**: exactly one YAML document
  (duplicate keys refused), a `Tuned` (`apiVersion: tuned.openshift.io/v1`) or a `PerformanceProfile`
  (`apiVersion: performance.openshift.io/v2`), whose `metadata.name` is
  `<name>`. `<name>` is a DNS-1123 label of at most 63 characters (it
  becomes a ConfigMap's name).
- `tuning/<clusterName>/<name>.yaml` is a **variant** for one cluster: the
  same rules, and for that cluster it wins over the shared file of the same
  name. `<clusterName>` is the CI's `resolve_cluster_name`: the cluster
  file's own `clusterName` key when it has one, else the file stem minus
  `DAY1_CLUSTER_NAME_STRIP_PREFIX` (ADR-0015), which is the HostedCluster
  name day1 already derives.
- Nothing deeper. A file that breaks a rule is listed in the response's
  `problems` with its path and why, and is never offered, a `README.md`
  included (unlike `mc-files/`, ADR-0027, the CI accepts only `.yaml`
  there). Hidden files (`.gitkeep`) are ignored, as the CI ignores them.
- A Tuned's summary is the `summary=` line of the `[main]` section of its
  first profile's `data`; the picker shows it.
- **Pairing.** A Tuned that builds on a PerformanceProfile's generated
  profile has `include=openshift-node-performance-<pp>` in the `[main]`
  section of a profile's `data`; the catalogue gives that `<pp>` as the
  Tuned's `requires_performance_profile`. A nodepool that names the Tuned
  without that PerformanceProfile gets a warning in the web with a
  one-click "Add `<pp>`"; it is never refused, since the include may be
  satisfied another way.
- A day1 repo without
  `tuning/` is an empty catalogue (`found: false`): nothing is offered and
  nothing else changes.

**The input and the file.** A nodepool's template input `tuning_config`
is a list of profile names in the order chosen (a single name as a string
is still accepted). Day1 writes `nodepool[].tuningConfig` as a string for
one name, a list for several, and leaves the key out for none; the shared
template renders whichever it is given, and day1 checks that the rendered
file holds exactly the names chosen.

**`tuningConfigmap` is an automation key** (amending ADR-0012): the CI
writes it. A rendered file may not contain it, so neither provisioner
(merge request or the provision-cluster workflow, ADR-0042) ever sends it,
and an edit that changes or removes it is refused, as for `mcConfigMap`.
Existing hand-written entries stay valid input.

**Checked at flavor save, create and edit** (422, one problem per name, at
its path, with a "did you mean" for a near miss):

- at flavor save (`POST`/`PUT /specs`), every name in
  `spec.day1.values.nodepools[i].tuning_config` must be a shared profile;
- at preview and create, every name of the merged inputs must be a shared
  profile;
- at an edit of an existing cluster (`PATCH /clusters/{name}`, a sync), every
  name the edit adds to the file must be a shared profile, a variant for
  this cluster, or an entry of the file's own `tuningConfigmap`. Names the
  file already had are not re-checked: an edit of something else never
  fails on tuning the cluster already runs.
- everywhere, **a nodepool names at most one PerformanceProfile**: a
  HyperShift NodePool references at most one, and its reconciler fails on
  more. Any number of Tuned is fine. At an edit only a nodepool whose
  `tuningConfig` the edit changes is checked, and a name's kind is the
  CI's resolution for this cluster (its variant, else the shared file,
  else the file's own `tuningConfigmap` entry). In the web, picking a
  second PerformanceProfile replaces the first and says why.

**The tuning rule.** `nodepools[*].tuning_config` (file key
`nodepool[*].tuningConfig`) is lockable as a rule for every nodepool, like
the configs rule (ADR-0029), and compared **as a set by name**: order and
repetition do not count, since each name is its own ConfigMap. Its value is
the names every flavor nodepool sets, which must agree and may not be
empty (to keep a fleet free of tuning, lock nothing: a rule of no profiles
would need sync to delete the key, which the text editor does not do). No
position locks tuning. At create a nodepool that sends other profiles is a
422 naming it; one that sends none gets the rule's.

**Drift and sync.** A nodepool whose `tuningConfig` names other profiles
than a locked rule is value drift (ADR-0036), with the names a sync adds
and removes. A sync (ADR-0037) writes only `tuningConfig` names, in the
flavor's order, and never `tuningConfigmap`: the CI injects the manifests
on the MR branch. A name the sync would add that does not resolve for this
cluster blocks the sync with the reason. Changing a pool's tuning can
reboot its nodes (a PerformanceProfile, kernel arguments), so the preview
lists those pools among the rebooting ones, the web's confirmation names
them ("their nodes may reboot"), and the MR description says so; the CI
adds no such warning. Removing a profile needs no extra confirmation (the
configs' `confirm_removals` is about MachineConfigs).

## Alternatives rejected

- **Keep manifests in each cluster file, edited by Wingman**: the copies
  drift, and Wingman would write a key the CI now owns.
- **Overwrite a differing `tuningConfigmap` entry with the catalogue's**:
  the user's decision is to keep it and report it; overwriting can reboot
  nodes nobody chose to reboot.
- **Offer variants at create and in flavors**: a variant belongs to one
  existing cluster; a flavor names shared profiles only.
- **Compare as an ordered list or a multiset**: reordering or repeating a
  name changes nothing on the nodes, so it must not be drift.
- **A positional lock (`nodepools[0].tuning_config`)**: an existing
  cluster's nodepools come in any order (ADR-0029's reasoning).
- **A new port and adapter for `tuning/`**: it is a folder of the day1 repo,
  read through `GitLabPort` and the snapshot like `mc-files/`; a new GitLab
  read is already covered by the metrics contract (ADR-0010).

## Consequences

- The web offers a "Tuning profiles" multi-select per nodepool in the
  flavor editor and on the create form, with a lock switch like configs,
  drift and a sync confirmation that names the pools that may reboot.
- A deployment whose day1 repo has no `tuning/` sees an empty picker and
  no other change. Injection needs the day1 repo's CI step; until it runs,
  a new name in `tuningConfig` has no manifest in the file.
- The provision-cluster workflow refuses automation keys in a submitted
  file and, on a re-run, compares the branch's file with the CI's
  `mcConfigMap` set aside. With the CI also appending `tuningConfigmap`,
  the workflow must set that key aside too; that change is the workflow's,
  not Wingman's. Wingman never sends `tuningConfigmap`.

## Verification

- `apps/day1-service/tests/unit/domain/test_tuning_profiles.py`: the
  catalogue rules (shared, variants, every problem, summaries, the
  PerformanceProfile a Tuned builds on), the input and file forms, and the
  save, create and edit checks, one PerformanceProfile per nodepool
  included.
- `apps/day1-service/tests/unit/domain/test_tuning_rule.py`: the tuning
  rule's save rules, enforcement and fill at create, the render form, drift
  as a set, and the rebooting pools.
- `apps/day1-service/tests/unit/domain/test_cluster_file.py`:
  `tuningConfigmap` refused in a rendered file and kept by an edit.
- `apps/day1-service/tests/unit/application/test_tuning_profiles.py`: the
  read, a missing `tuning/`, hidden files not read, a failed read.
- `apps/day1-service/tests/unit/application/test_tuning_sync.py`: a sync
  writing only names, a name that does not resolve blocking it, the pools
  that may reboot, `tuningConfigmap` untouched.
- `apps/day1-service/tests/api/test_tuning_profiles_api.py`: the endpoint on
  the fixtures, the 422s at save, create and edit, and a create through
  both provisioners carrying the names and never `tuningConfigmap`.
- `apps/web/e2e/tests/flavor-tuning.spec.ts`: picking, locking, creating
  with a locked profile, an unknown name's 422, a second PerformanceProfile
  replacing the first, the pairing warning, drift and the sync
  confirmation.

## Amendment (2026-11-16): tuning in the flavor's every-nodepool panel

The user (2026-11-16): when a flavor gives every nodepool the same machine
configs, the tuning profiles are in most cases the same too, so they belong
to that choice, optional. The web editor changes; day1, the create form,
drift and sync do not (the rule, its save checks and its enforcement stay
as decided above).

- **One panel.** With the configs "The same on every nodepool" (ADR-0029),
  the panel "On every nodepool" holds the configs rule and a switch, "Same
  tuning profiles on every nodepool". On is the tuning rule
  `nodepools[*].tuning_config`: the panel's picker sets every nodepool's
  names, and each nodepool card shows them read-only ("Gets the rule's
  tuning profiles: …"). Off, each card keeps its own picker as a preset,
  with no lock of its own: in this mode the panel's switch is the lock.
- **The default.** Choosing the mode turns the switch on, starting from
  Nodepool 1's names, unless the nodepools name different profiles
  (compared as a set) or the catalogue offers none: it then stays off and
  nothing is overwritten, and the panel says that turning it on gives
  every nodepool Nodepool 1's. On with no names yet is an editing state:
  the rule may not be empty, so the save is refused at the panel ("Choose
  the profiles every nodepool gets, or turn off the same tuning
  profiles"). In the panel the rule's names are checked once, there,
  instead of on every card.
- **Leaving the mode.** "Each nodepool its own" drops both rules; every
  nodepool keeps its configs and its names as presets. In that mode the
  card's lock still means the every-nodepool rule, as in 3.37.0, so a
  flavor saved that way loads and edits unchanged.
- **Loading.** A saved flavor shows the switch on exactly when its
  `locked_paths` holds the tuning rule beside the configs rule; nothing is
  turned on when a flavor is opened.

Rejected: always including tuning in the panel (a flavor whose nodepools
differ would have them overwritten, and a fleet without tuning could not
use the configs rule, since the tuning rule may not be empty); a lock on
each card in this mode beside the switch (two controls for one rule).

Verified in `apps/web/components/specs/flavor-editor/tuning-model.test.ts`
(the default, differing nodepools, the empty rule's message, leaving the
mode, a 3.37.0 lock kept) and `apps/web/e2e/tests/flavor-tuning.spec.ts`
(the panel's switch from Nodepool 1, differing nodepools kept, the empty
rule refused, the cards' pickers back when off, the saved body, and saved
flavors loading as they were saved).
