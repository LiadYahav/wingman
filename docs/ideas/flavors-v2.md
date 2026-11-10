# Flavors v2

**Status:** built, 2026-11-08 (release 3.3): ADR-0026 to ADR-0029,
ADR-0036, ADR-0037, the API contract in
`docs/notes/2026-11-08-flavors-v2-api-changes.md`, the operator steps in
`docs/upgrade/3.2-to-3.3.md`. Still open: see "Left for later" at the end. "Flavor" is what the code and the API call a
cluster spec (`ClusterSpec`, `/api/day1/specs`, ADR-0013); the UI will say
Flavor.

## The problem

A flavor today sets list counts (how many nodepools) and marks fields with a
lock icon, but:

- a nodepool's machine configs are free text, so a typo fails in the
  platform-config CI after the MR, not in the form;
- every nodepool needs the same three configs (the per-cluster network
  config `nm-conf`, `workers-chrony-configuration`, `nic-ring-buffer`) and
  nobody fills them in for you;
- the lock is only a form hint: nothing enforces it;
- an existing cluster can't join a flavor, so drift only covers clusters
  Wingman created;
- the create-flavor page is hard to use.

## Decisions

| Question | Decision |
|---|---|
| What does a lock mean? | **A fixed value in the flavor.** A locked field takes the flavor's value; cluster create can't override it, and a later edit that changes it shows as drift. An unlocked value is a preset anyone can override at create. |
| What does sync change on a cluster imported into a flavor? | **Everything in one MR**: every locked value the cluster differs on, machine configs included, in one day1 MR, plus the day2 MRs for missing add-ons (one per team). |
| Owners (merkaz, anaf, mador) | **Numbers only**: three numeric fields, validated, no names or catalogue. |
| OCP version | **Not in the flavor.** Chosen per cluster at create, as today; upgrades are a separate flow (workflow-runs.md). |

## Design

### Machine configs per nodepool

- **Catalogue.** Day1 reads `mc-files/` in the day1 repo (`platform-config`)
  through `GitLabPort`. It never writes there. A new read endpoint lists:
  - static configs, which are files in the root and its subfolders (for example `kubevirt/`);
  - per-cluster network configs, from `templates/nm-conf-template-hw-<hw>.bu`. A
    nodepool picks the hardware type `<hw>`, and the name written to the file
    is `nm-conf-<clusterName>-<hw>`, the convention the CI resolves.
  - Not `legacy/`: those are restored originals for clusters not yet
    onboarded, not something to pick. *Built:* a name found only there is
    refused at save and create, although the CI would resolve it.
- **Entries** *(built)*: `{name: <static config>}` or `{name: nm-conf,
  hardware: <hw>}`. A flavor stores the second as written; day1 expands it
  to `nm-conf-<clusterName>-<hw>` before the shared template renders, and
  refuses it when an overlapping hardware type (`dell` and `dell-data`)
  would make the CI read the expanded name as another type.
- **Picker.** The shared searchable combobox, grouped by kind, showing each
  name with its folder. A hardware type is chosen from the template list.
- **Validation.** On flavor save and on create, each name must resolve by the
  same rule the CI uses (a static file, or a template suffix). An unknown
  name is a 422 problem in the form, not a failed pipeline later.

### Nodepool defaults

- `nodepool-defaults.yaml` in the specs project lists the configs a new
  nodepool starts with: `nm-conf` (hardware type to choose),
  `workers-chrony-configuration` and `nic-ring-buffer`. The team changes it
  by MR, like a flavor. *Built:* `configs: [<entry>, ...]`, where `nm-conf`
  may leave out its hardware; served by `GET /api/day1/machine-configs`; a
  missing file is no defaults, a broken one is served with its error.
- Defaults fill a nodepool when it is added, in the flavor editor and at
  create (unless the flavor locks the list). They are written into the
  file. Changing the defaults never changes an existing flavor or cluster.

### Locks

- Every value a flavor sets is either a **preset** (prefilled, overridable)
  or **locked** (shown read-only at create; day1 refuses a create that sends
  another value).
- **Day1 drift** becomes: a locked value that differs in the cluster file,
  beside the existing add-on drift (ADR-0016, ADR-0025). Presets never drift:
  overriding them is allowed.
- Specs already in GitLab keep loading: their `immutable_paths` are read as
  locked paths. The old wording ("can't change after create") goes away.
  *Built:* the field is now `locked_paths`; `immutable_paths` is read as an
  alias and never written. A lock needs a value in `spec.day1.values`; a
  stored lock without one, or on an input that is not lockable, still
  loads, is not enforced, and shows in the spec's `warnings`.
- *Built:* a create that sends another value for a locked path is a 422;
  one that leaves it out gets the flavor's value. Lockable: the owners,
  `platform`, and per nodepool `replicas`, `configs` and `node_labels`.
- Locked values are template inputs (`nodepools[0].configs`), but drift reads
  the file (`nodepool[0].configs`). Day1 keeps one table that maps each
  lockable input to its file key (owner, platform, replicas, configs,
  labels), next to the shared template. *Built:* `LOCKABLE` in
  `wingman_day1.domain.locks`.

### Owners

`owner_merkaz`, `owner_anaf` and `owner_mador` are digits only (validated by
day1 and the form). *Built:* a string of 1 to 10 ASCII digits, so a leading
zero survives. A flavor can preset or lock them, for example for a
flavor that belongs to one team. The cluster list can filter and group by
the three numbers.

### Importing existing clusters

1. **Pick.** From a flavor's page, "Add existing clusters": search and
   filter by site, MCE and owner. Each one shows what differs from the
   flavor: its locked values and any missing add-ons.
2. **Import.** One day1 MR writes the flavor's link (the provenance comment
   Wingman already writes at create: `specName`, `specVersion`) into each
   picked cluster's file. Nothing else changes. After the merge, these
   clusters show their differences as drift.
3. **Sync.** Per cluster:
   - One day1 MR writes every locked value the cluster differs on.
   - Day2 MRs install the missing add-ons.
   - The confirm dialog and the MR description name the nodepools whose machine
     configs change: merging reboots those nodes, rolling, because that is
     how OpenShift applies a MachineConfig.
   - Sync never touches the keys others own: `vlanId`, `dhcp_values`, `mcFiles`, `mcConfigMap`.
4. **Which clusters use this flavor.** The flavor page lists its clusters and
   their drift. A flavor in use can't be deleted. Its version history is the
   spec file's commit history.

Still to settle while building: how a flavor's nodepool locks match an
existing cluster's nodepools, which come in any number and order. The
proposal is to lock configs as a rule for every nodepool ("every nodepool
has these configs, plus `nm-conf` for its hardware") rather than by
position. A position only means something for clusters the flavor creates.
Stage 1 locks by position (`nodepools[0].configs`). *Settled in stage 2:*
the rule `nodepools[*].configs` (ADR-0029), compared exactly by name in any
order; a sync's removals are confirmed one by one (ADR-0037).

### The flavor page

Redesigned with the apple-design skill once the model above exists. One page
in four parts (basics, nodepools, add-ons, review). Each value has a clear
preset/locked switch. Machine configs come from the picker, prefilled from
the defaults. A live preview shows the cluster file the flavor produces.

## Where this is going

The architecture's self-service catalog "exposes pre-packaged NodePool
profiles": flavors are those profiles (architecture-fit.md). Two things move
when the workflows exist:

- **Create:** the create workflow takes worker types (a node type and a count)
  and spreads each over three zones itself. A flavor's nodepools then become
  worker types with totals, and the zones stay out of the form. Keep the
  flavor's nodepool entries close to that shape.
- **Sync:** once the scale workflow (update-nodepool) owns the NodePool files,
  a flavor sync changes NodePool fields through it, not by Wingman's own
  commit: one writer per file. Until then the sync MR carries the file's
  `last_commit_id` (ADR-0006), so it can't overwrite a change made after
  Wingman read the file.

Where a nodepool's machine configs live in the VM model (the node type or the
cluster) is a question for the architect.

## Order of work

1. Day1: the machine-config catalogue endpoint, nodepool defaults, config
   validation, enforced locks at create, owner validation. *Done.*
2. Day1: import, day1 drift on locked values, the sync MR. *Done.*
3. Web: the flavor page, the create form's config picker, import, and drift
   for day1 values. *Done:* the flavor editor in four parts, the create form's
   locks, presets and picker, the flavor page with "Add existing clusters",
   value drift and "Sync to flavor" on the cluster page, owner filters and
   grouping on the cluster list; the UI says Flavor.
4. E2E: mocked tests for each, then the live suite against the seeded local
   GitLab (the fixtures need an `mc-files/` tree). *Done:* `flavor-*.spec.ts`
   (mocked), `live-flavors.spec.ts`, and `scripts/dev/day1_live_e2e.py`'s
   import and sync on GitLab CE 19.5.3.

Each stage lands with its ADR: locks, machine configs and defaults,
import and sync.

## Left for later

- **A preview of an unsaved flavor.** `POST /clusters/preview` renders only a
  flavor in the specs repo at its saved version, so a new flavor has no
  cluster-file preview until it is merged (its edit page has one). It needs a
  preview that takes the flavor document in the request.
- **Missing add-ons in one MR per team.** Sync and the drift tab install them
  one chart per MR through day2's per-chart install; day2's
  `POST /clusters/{id}/addons/bulk` would make it one MR per team.
- **The cluster-name prefix in the web.** The create form shows
  `nm-conf-<clusterName>-<hw>` assuming day1 strips `ocp4-` (the default of
  `DAY1_CLUSTER_NAME_STRIP_PREFIX`); on the sandbox (`""`) the hint is wrong,
  and the preview shows day1's real name. Day1 could say its prefix.
- **A rule's hardware.** Under `nodepools[*].configs` each flavor nodepool's
  `nm-conf` needs a hardware type at save (a preset each cluster may change),
  so a flavor cannot leave it for create time.
