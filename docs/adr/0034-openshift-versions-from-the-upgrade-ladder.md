# ADR-0034: A new cluster's OpenShift versions come from the upgrade ladder, per MCE

Date: 2026-11-08
Status: Accepted; amended 2026-11-13 (3.20.0: the clusters list's upgrade suggestion)

## Context

The create form offered one list for every MCE: `openshift-versions.txt` in
the specs project (ADR-0013). Not every MCE can host every release. An MCE's
HyperShift operator hosts only some OCP minors (its
`hypershift/supported-versions` ConfigMap), so the list offered releases the
chosen MCE could not run, and nothing stopped a create with one. The user:
"It should be read from the upgrade ladder, because not every MCE cluster
can host any OCP version HostedCluster."

The day1 repo already says both halves, for the cluster-upgrade workflow:
`upgrade/ladder.yaml` lists the verified releases (`ladder[].version`, bare
`4.20.44`, at least one per minor) and `upgrade/mces/<mce>.yaml` lists the
minors each MCE can host (`mce.supportedHostedVersions`, `"4.22"`). Their
JSON schemas are in `upgrade/schema/`.

## Decision

- The versions a new cluster on MCE X may use are the ladder's rungs whose
  minor is in X's `supportedHostedVersions`, newest first.
  `GET /api/day1/mces/{mce}/openshift-versions` returns
  `{mce, versions[], problems[]}`. The files are read through the cached day1
  repository (ADR-0011). An MCE folder that exists nowhere is a 404.
- The JSON schemas are the contract for the parts Wingman reads (the rung
  pattern `4.N.N`, the minor pattern `4.N`). The day1 repo's
  `scripts/validate_upgrade_rules.py` checks the rest, `schemaVersion`
  included (see the correction below). An
  entry that breaks them is left out and named in `problems`. An unquoted
  `4.20` is the float `4.2`, so it is refused, not guessed.
- A missing or broken file means no versions and a problem in plain words,
  with status 200: "MCE X has no upgrade/mces/X.yaml in the day1 repo, so
  Wingman can't tell which OpenShift versions it can host. Add it (see
  upgrade/README.md)." Not knowing is not the same as allowing everything,
  so Wingman never falls back to the whole ladder.
- Create and preview refuse a rendered `mastertag` the MCE does not offer:
  422 with the version, the MCE and the allowed list. Before comparing,
  `4.20.44-x86_64` becomes `4.20.44`. The file keeps what was sent, because
  the chart adds `-x86_64` to a bare version itself.
- `openshift-versions.txt`, `GET /api/day1/specs/versions/openshift` and
  `SpecCatalog.versions()` are removed. This supersedes the release-list part
  of ADR-0013.
- The web picker reads the endpoint for the chosen MCE and is disabled until
  one is chosen. It shows `problems` under the field. A spec's preset version
  (and the MCE's default `mastertag`) prefills only when the MCE offers it.

## Alternatives rejected

- **Keep the specs list and filter it by MCE**: there would be two lists
  that must agree, and the ladder is the one the upgrade workflow trusts.
- **Fall back to the whole ladder when an MCE has no file**: the form would
  offer releases the MCE may not host. That is the bug this ADR fixes.
- **Validate with a JSON-schema library**: it would add a dependency to check
  keys Wingman never reads. The day1 repo's validator already runs on every
  change there.
- **Read the MCE's `hypershift/supported-versions` ConfigMap live**: that
  needs hub credentials for every MCE (status may be off). The upgrade
  workflow already checks that the file matches the ConfigMap before every
  run.

## Consequences

- Onboarding an MCE that clusters are created on now needs an
  `upgrade/mces/<mce>.yaml` (`docs/upgrade/legacy-to-ecosystem.md`, check
  4.4). Until it has one, the form offers that MCE no version.
- A minor with no ladder rung (4.22 today) is not offered, even on MCEs that
  can host it. Clusters move into a minor only once a verified rung exists.
- The fixtures give every convention MCE a file: the production MCEs host
  4.16 to 4.18, and `ocp4-prep-mce-site1-a` hosts 4.17 to 4.21.

## Verification

- `apps/day1-service/tests/unit/domain/test_openshift_versions.py`: the
  fixture files parse cleanly, filtering and ordering, missing and broken
  files, the float trap, `-x86_64` normalisation.
- `apps/day1-service/tests/api/test_openshift_versions_api.py`: the endpoint
  per MCE, a missing MCE file or ladder, an unknown MCE (404), and create and
  preview refusing a release the MCE can't host (422).
- `apps/web/e2e/tests/cluster-creation.spec.ts`: the per-MCE list, the
  problem when an MCE has no file, the disabled picker before an MCE is
  chosen, a spec preset the MCE can't host.

## Correction (2026-11-08)

The first version also required `schemaVersion: 1` and offered no version
when it was missing. Production's `upgrade/ladder.yaml` has no
`schemaVersion` (the sandbox copy that the fixtures follow added it), so every
MCE offered nothing and no cluster could be created. Wingman now ignores
`schemaVersion`: it reads only `ladder[].version`, and checks each rung's own
shape, so a file whose format moves on still says which rung it can't read.

## Amendment (2026-11-13, 3.20.0)

The same list, per MCE, feeds the clusters list's "Upgrade available →
<version>" while upgrades are on (ADR-0055's 3.20.0 amendment):
`upgrade_hint` takes the newest release a cluster's MCE offers that is newer
than its `mastertag`. It is a suggestion only; the upgrade-cluster workflow
still plans every upgrade from the ladder itself.
