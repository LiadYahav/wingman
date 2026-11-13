# ADR-0012: A cluster file is a chart values file; people and automation own disjoint keys

Date: 2026-11-07
Status: Accepted; amended by ADR-0055 (with `DAY1_UPGRADES` on, `mastertag`, every `workertag` and `pausedUntil` belong to the upgrade-cluster workflow: an edit may not change them, except to remove `pausedUntil`)

## Context

The day1 repo (`gitops-day1/platform-config`) holds one file per hosted
cluster at `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml`. The
tier-3 ApplicationSet turns **every file** in that folder into an ArgoCD
Application of the hostedclusters-setup chart, layering it last on top of
`sites/configValues.yaml`, the site's and the MCE's `values.yaml`. An empty
file fails the generator. The legacy service rendered multi-document
HyperShift manifests into this file (which Helm would read as values),
wrote `hostedClusters/.gitkeep` when it created an MCE, and read
`<cluster>.wingman.yaml` sidecars from the same folder.

After Wingman opens the MR, two other writers commit to the same file on
the MR branch: the allocate-segment workflow adds `vlanId` and
`dhcp_values`, and CI adds `mcConfigMap` (and may set `mcFiles`).

## Decision

- Wingman writes exactly one file per cluster, the values file, and nothing
  else under `hostedClusters/`: no placeholder, no sidecar.
- People and Wingman own `owner`, `mastertag`, `nodepool[]` (`infraEnvName`,
  `replicas`, `labels.allowDeletion`, `configs[].name`, optional `name`,
  `nodeLabels`, `tuningConfig`) and optional fields such as
  `platform: kubevirt`. Automation owns `vlanId`, `dhcp_values`, `mcFiles`,
  `mcConfigMap`. `clusterName`, `site` and `mce` come from the path.
- A rendered file (create) is refused unless it is one YAML mapping without
  duplicate keys, has a valid `mastertag`, a non-empty `nodepool` that obeys
  the chart's rules (an InfraEnv on the Agent platform, no duplicate derived
  pool names, whole-number replicas), and none of the automation or path keys.
- An edit (modify, or editing an MR's file in review) is refused if it
  changes or removes any automation key or `clusterName`, whatever value
  automation wrote. Wingman never force-pushes; it commits on top.
- Wingman's own bookkeeping is a comment header (`# specName:`,
  `# specVersion:`, `# wingmanAddons: [...]`), which Helm, ArgoCD and the CI
  scripts (they rewrite files preserving formatting) ignore. The first two
  lines are the legacy service's, so files it created keep their spec link.
- Any other file found under `hostedClusters/` is reported as stray on the
  MCE view, never treated as a cluster.

## Alternatives rejected

- **A sidecar next to the file** (`.wingman.yaml`): it becomes a bogus
  Application.
- **A Wingman-owned path outside `sites/`**: a second file per create, which
  the MR then has to keep consistent; the header carries the same facts in
  the one file that is reviewed anyway.
- **Unknown top-level keys for Wingman's data**: they become chart values.

## Consequences

- The legacy `.gitkeep` bug cannot recur: there is no code path that writes
  anything but `ClusterRef.path`.
- A reviewer sees in one file what the cluster gets, and who asked for it.
- If CI ever rewrote files without preserving comments, the spec link would
  be lost; the cluster would show as "not linked", never as wrong.

## Verification

- `apps/day1-service/tests/unit/domain/test_cluster_file.py`: every rule of
  `rendered_file_problems` and `edit_problems`, the strict loader, the header
  round trip.
- `apps/day1-service/tests/api/test_cluster_lifecycle.py`: a create adds
  exactly the one file and leaves `main` untouched; an edit that drops
  `vlanId` is refused with 422.
- `apps/day1-service/tests/unit/test_guards.py`: every path the provisioner
  writes is a cluster file.
