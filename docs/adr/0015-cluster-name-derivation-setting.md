# ADR-0015: How a file stem becomes the chart's clusterName is a setting; production's rule is the default

Date: 2026-11-07
Status: Accepted (the team question it encodes is open)

## Context

The chart names the HostedCluster `openshift-<clusterName>` in namespace
`hcp-<clusterName>`. Where `clusterName` comes from differs:

- production's ApplicationSet (`gitops-day1/argocd-platform`) passes the
  file's own `clusterName` key if set, else the file name minus `.yaml` and
  minus `clusterFilePrefix: ocp4-` (`ocp4-prod-herzi-site1.yaml` →
  `openshift-prod-herzi-site1` in `hcp-prod-herzi-site1`);
- the GitHub sandbox's ApplicationSet passes the whole stem
  (`openshift-ocp4-prod-herzi-site1`), verified with `helm template`.

The legacy status service looked for a HostedCluster named after the full
stem in `hcp-<stem minus ocp4->`, which neither environment creates. Which
convention is canonical is open question 2 in `docs/ecosystem/README.md`.

## Decision

- `DAY1_CLUSTER_NAME_STRIP_PREFIX` (default `ocp4-`, production) is the
  prefix removed from the stem; empty means the sandbox rule. The legacy
  `MCE_CLUSTER_NAME_PREFIX` (the chart's `clusterStatus.clusterNamePrefix`)
  is accepted for the same value.
- An explicit `clusterName:` key in the file wins over both, as production
  does.
- Every place that needs the HostedCluster or its namespace (live status,
  name-length checks, the cluster views) goes through one
  `HostedClusterNaming`.

## Alternatives rejected

- **Hard-code production's rule**: the sandbox is where Wingman is tested
  against real hubs today.
- **Probe both names on the hub**: doubles hub calls and hides a
  misconfiguration instead of exposing it.

## Consequences

- A deployment against the sandbox must set the variable to empty.
- When the team decides question 2, the default may change; this ADR is
  then superseded.

## Verification

`apps/day1-service/tests/unit/domain/test_names.py` (both modes, explicit
key) and `apps/day1-service/tests/unit/application/test_status.py` (the hub
is asked for the right object in each mode).
