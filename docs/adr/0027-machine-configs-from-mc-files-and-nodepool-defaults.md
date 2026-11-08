# ADR-0027: Machine configs come from mc-files and are checked; new nodepools start from the team's defaults

Date: 2026-11-08
Status: Accepted

## Context

A nodepool's `configs` lists MachineConfig sources by name. After a day1
merge request is pushed, the day1 CI resolves each name to a file under
`mc-files/` in the day1 repo (`gitops-day1/platform-config`), renders it,
and writes the result into the cluster file's `mcConfigMap` (ADR-0012). The
create form took free text, so a typo failed in that pipeline, after the MR
was open. Every nodepool also needs the same three configs (the cluster's
own network config `nm-conf`, `workers-chrony-configuration` and
`nic-ring-buffer`), and nobody filled them in. This is stage 1 of flavors
v2 (`docs/ideas/flavors-v2.md`, user decisions of 2026-11-08).

## Decision

**The catalogue.** `GET /api/day1/machine-configs` lists what `mc-files/`
offers. Day1 reads it through `GitLabPort`, as one recursive tree listing
of the day1 repo's default branch, cached like every other read
(ADR-0011), and never writes there.

**The rule is the CI's**, in Wingman's words
(`wingman_day1.domain.machine_configs`):

1. Each `mc-files/templates/nm-conf-template-hw-<hw>.bu` is a hardware type
   `<hw>`. A name ending in `-<hw>` is rendered from that template; when
   several types match, the longest wins (`-dell-data` before `-dell`).
   Templates are tried before static files.
2. Otherwise the name is a static file: `<name>.bu` anywhere before a file
   named exactly `<name>`; within each, the `mc-files/` root before
   subfolders, subfolders in path order. `templates/` is never a static
   source.
3. A butane file's config name has no `.bu` (the CI renders `x.bu` as `x`);
   any other file's config name is its whole file name.

**Wingman narrows it.** `legacy/` holds restored originals of clusters not
yet onboarded: the CI would find a name there, but Wingman neither offers
nor accepts it. Documentation (`*.md`, dot files) is not a config. A config
name is lowercase letters, digits, `-` and `.`. A static file that a
template captures (its name ends in `-<hw>`), a name found twice, and a
template file not named `nm-conf-template-hw-<hw>.bu` are not offered and
are listed in the response's `problems`. A day1 repo without `mc-files/`
is an empty catalogue that says so: nothing resolves there.

**An entry is `{name: <static config>}` or `{name: nm-conf, hardware: <hw>}`.**
The second is the cluster's own network config. Day1 expands it to
`{name: nm-conf-<clusterName>-<hw>}` before rendering, where clusterName is
the chart's (the file stem minus `DAY1_CLUSTER_NAME_STRIP_PREFIX`,
ADR-0015), so the shared `cluster-template.j2` (which renders
`config.name`) and the file the CI reads keep their shape.

**Checked at flavor save and at create.** On `POST /specs` and `PUT
/specs/{name}`, every entry in `spec.day1.values.nodepools[i].configs` must
resolve; a flavor has no cluster name, so a network entry names only a
known hardware type, and a written-out `nm-conf-<...>-<hw>` is refused in
favour of the structured form. On preview and create, every entry of the
merged inputs must resolve for this cluster: the expanded network name must
be one the CI reads as the chosen hardware type (an overlapping type can
capture it), and a written-out name is accepted only when it is this
cluster's own. Within one nodepool an entry may not repeat. Each broken
entry is one line of the 422 problem's `details.problems`, at its
template-input path (`nodepools[1].configs[0]: ...`), with a "did you
mean" for a near miss. Flavor values must also pass the template's input
check (ADR-0013) at save, not only at create.

**Nodepool defaults.** `nodepool-defaults.yaml` at the root of the specs
project (next to `cluster-template.j2`) is `configs: [<entry>, ...]`; there
`nm-conf` may leave its hardware type to the nodepool. The team's file
lists `nm-conf`, `workers-chrony-configuration` and `nic-ring-buffer`. The
endpoint serves it with the catalogue; the web fills a new nodepool with it
in the flavor editor and on the create form. Day1 never applies it to a
flavor or cluster that exists. A missing file means no defaults (`found:
false`); a file that does not parse is served with its `error` and no
entries, never as an empty list; entries that would not resolve are listed
in its `problems`; a failed GitLab read fails the request (ADR-0004).

## Alternatives rejected

- **Leave the check to the CI**: the status quo; the failure arrives after
  the MR exists, as a pipeline log.
- **Offer `legacy/` because the CI resolves it**: those files are frozen
  payloads of clusters that are not onboarded yet; a new cluster that picks
  one copies someone else's frozen config.
- **Write `nm-conf-<clusterName>-<hw>` in a flavor**: a flavor has no
  cluster name; only the hardware type is the flavor's to choose.
- **Defaults in day1's settings or the chart**: the team changes them by MR,
  like a flavor, so they live in the specs project.
- **A broken defaults file fails the whole endpoint**: the picker would be
  gone because of one file; the spec list already reports a broken spec
  inline (`load_error`) for the same reason.

## Consequences

- The web can build the config picker from one read: static configs with
  their folders, hardware types, and the defaults.
- A change to `mc-files/` shows within the cache TTL, or at once with the
  GitLab webhook.
- The fixtures carry a small, made-up `mc-files/` tree (no real servers,
  addresses or hostnames), which the fake backend and `seed_gitlab.py` load
  like every other fixture file.

## Verification

- `apps/day1-service/tests/unit/domain/test_machine_configs.py`: the
  fixture catalogue, every resolution and narrowing rule (including the
  longest-suffix rule and path ordering), the defaults document, and a
  property test that an accepted network entry is one the CI renders from
  its own template.
- `apps/day1-service/tests/unit/application/test_machine_configs.py`: a
  missing `mc-files/`, missing, broken and unresolvable defaults, a failed
  read propagating, and the cache.
- `apps/day1-service/tests/api/test_machine_configs_api.py`: the response
  the web reads.
- `apps/day1-service/tests/unit/application/test_flavor_rules.py` and
  `apps/day1-service/tests/api/test_flavor_rules_api.py`: the expansion in
  the rendered file (in both `DAY1_CLUSTER_NAME_STRIP_PREFIX` modes), and
  the 422s at flavor save and at create.
