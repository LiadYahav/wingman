# ADR-0014: New cluster names follow ocp4-<env>-<name>-<site>[-<seq>]; existing ones are flagged, not hidden

Date: 2026-11-07
Status: Accepted; amended by ADR-0040 (a new cluster's `<seq>` is one letter, `a` to `z`) and on 2026-11-24 (a new name is at most 24 characters after `ocp4-`)

## Context

The team's names: MCEs `ocp4-<env>-mce-<site>-<letter>`, cluster files
`ocp4-<env>-<name>-<site>[-<seq>]`, env one of prod, prep, test. The chart's
day2 registration derives `<env>` from the MCE name and fails on names that
break the rule; segments-manager and the workflows use the file stem as the
cluster's identity, unique across the estate. Some repos break the rule
(`ocp4-upgrade-demo` under MCE `ocp4-mce-workflow-test`). Site tokens may
contain dashes in other environments (`site-a`, `bat-yam`), so a name cannot
be split on dashes to find its site. HyperShift derives the namespace
`hcp-<cn>-openshift-<cn>`, a DNS label of at most 63 characters, which
limits `clusterName` to 24 characters. (Corrected 2026-11-08: the
HostedCluster is `ocp4-<cn>`, so the namespace is `hcp-<cn>-ocp4-<cn>` and
the limit is 26 characters; see ADR-0015.)

## Decision

- A **new** cluster name must: be a DNS-1123 label; match
  `ocp4-<env>-<name>-<site>[-<seq>]` where `<site>` is the folder it is
  created in (matched literally, never parsed out); carry the env of its MCE;
  be unused anywhere in the repo and by any open create MR; and keep the
  HostedCluster name and control-plane namespace within 63 characters under
  the deployment's naming mode (ADR-0015).
- The MCE must itself follow its convention, or the env cannot be checked:
  Wingman does not create clusters under off-convention MCEs. (Team question
  3 in `docs/ecosystem/README.md` remains open: if the team decides such
  MCEs may host clusters with an explicit `day2.env`, this rule changes.)
- **Existing** names are read the same way and flagged
  (`naming.follows_convention`, `naming.problems`) in lists and details,
  never dropped or refused.

## Alternatives rejected

- **Refuse to list off-convention clusters**: they exist and are deployed;
  hiding them hides real state.
- **Split on dashes**: wrong for dashed sites.

## Consequences

- The create form gets every naming problem at once (`details.problems`).
- Creating under the sandbox's `ocp4-mce-workflow-test` is refused until the
  team decides question 3.

## Verification

`apps/day1-service/tests/unit/domain/test_names.py` (every fixture name,
dashed sites, env mismatch, off-convention MCE, namespace length in both
modes) and the create refusals in
`apps/day1-service/tests/unit/application/test_clusters.py`.

## Amendment 2026-11-24: a new name is at most 24 characters after `ocp4-`

Every create starts provision-cluster (ADR-0042's 2026-11-23 amendment), and
provision-cluster refuses a name whose part after `ocp4-` is longer than 24
characters (team-redbull/workflows `shared/cluster_names.py`,
`MAX_HOSTED_CLUSTER_NAME_LENGTH`, since 2026-11-11), counting a HostedCluster
named `openshift-<cn>` as the chart in Git names it. Wingman's own rule, the
63-character control-plane namespace with the `ocp4-<cn>` HostedCluster seen
live (ADR-0015), allowed 26, so a 25- or 26-character name got the
workflow's 422 after the form had accepted it. A new name is now refused at
25 characters (`MAX_NEW_CLUSTER_NAME`, `domain/names.py`), and the name
suggestion cuts a flavor's name until it fits: `agent-standard` gives
`ocp4-prod-agent-stand-site1-a`. The DNS-label checks stay as they were, and
an existing cluster's name is never refused for its length. If production's
HostedClusters really are `ocp4-<cn>` and the workflows team raises its limit
to 26, this constant follows it.
