# Architecture decision records

One file per decision, numbered, never deleted. A decision that changes is
superseded by a new ADR that says so; the old one stays and gets a
`Superseded by` status line. Every ADR uses the template below. The
**Verification** section names the test or measurement that pins the
decision, so the next person can tell it is still true.

```
# ADR-NNNN: <the decision, as a sentence>

Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by ADR-NNNN | Superseded in part by ADR-NNNN

## Context
## Decision
## Alternatives rejected
## Consequences
## Verification
```

| ADR | Decision |
|---|---|
| [0001](0001-layered-packages-with-ports.md) | Code is layered (domain, ports, application, infrastructure, web) and import-linter enforces it |
| [0002](0002-gitlab-adapter-on-httpx.md) | GitLab is reached through an async httpx adapter, not python-gitlab |
| [0003](0003-exact-pins-one-lockfile.md) | Dependencies are pinned exactly, in one workspace lockfile |
| [0004](0004-rfc9457-error-envelope.md) | API errors are RFC 9457 problems with an append-only error code |
| [0005](0005-fake-gitlab-and-contract-suite.md) | Tests run against an in-memory GitLab held honest by a contract suite |
| [0006](0006-write-semantics.md) | Writes are guarded by `last_commit_id` and never retried |
| [0007](0007-merge-request-identity-and-conventions.md) | An MR is `(project, iid)`; branch, title and description formats are a contract |
| [0008](0008-ty-type-checker.md) | ty is the type checker, as in server-scan |
| [0009](0009-settings-fail-closed.md) | Settings refuse insecure or fake-in-production configurations at start-up |
| [0010](0010-metrics-are-a-contract.md) | Metrics follow one catalogue with bounded labels, served off the public Route |
| [0011](0011-per-replica-read-cache.md) | GitLab reads are cached per replica for seconds; writes clear what they made stale (files and trees: ADR-0035) |
| [0012](0012-day1-values-file-and-key-ownership.md) | A cluster file is a chart values file; people and automation own disjoint keys |
| [0013](0013-sandboxed-template-and-spec-presets.md) | The cluster file is rendered from the shared template in a sandbox; specs are value presets (its release list superseded by ADR-0034) |
| [0014](0014-cluster-and-mce-naming-rules.md) | New cluster names follow `ocp4-<env>-<name>-<site>[-<seq>]`; existing ones are flagged, not hidden |
| [0015](0015-cluster-name-derivation-setting.md) | How a file stem becomes the chart's `clusterName` is a setting; production's rule is the default |
| [0016](0016-day1-records-addons-and-drift-is-addon-drift.md) | Day1 records a spec's addons and overrides, never writes day2, and unknown drift is not "in sync" |
| [0017](0017-cluster-provisioner-port.md) | Provisioning is a `ClusterProvisioner` port: a merge request today, the `create-cluster` workflow later |
| [0018](0018-sites-and-mces-are-read-only.md) | Sites and MCEs are read-only folders in Wingman |
| [0019](0019-hub-api-over-httpx.md) | MCE hubs, OpenShift OAuth and day2 are reached over httpx, behind ports, with failures reported |
| [0020](0020-day2-four-destination-kinds.md) | day2 models four destination kinds, discovered from folders and day1, each with an id that carries its position |
| [0021](0021-value-stacks-with-provenance-checked-by-the-oracle.md) | The values preview is the platform's exact stack with Helm's merge and per-key provenance, held to render_chain.py by an oracle test |
| [0022](0022-what-day2-writes.md) | day2 writes the minimum per change, never pins a version per cluster by default, and says that removal orphans |
| [0023](0023-day2-lints.md) | day2 lints are render_chain.py's rules as errors plus Wingman's own; a change that adds an error is refused |
| [0024](0024-chart-versions-and-defaults.md) | Chart versions and defaults come from the chart repo on the same GitLab, at the resolved revision and path |
| [0025](0025-version-differences-are-reported-not-drift.md) | A chart version other than the spec's is reported, never drift; a fix only installs a missing chart |
| [0026](0026-a-flavor-lock-is-a-fixed-value.md) | A flavor lock is a fixed value the flavor enforces; `locked_paths` replaces `immutable_paths`, which is still read |
| [0027](0027-machine-configs-from-mc-files-and-nodepool-defaults.md) | Machine configs come from mc-files and are checked; new nodepools start from the team's defaults |
| [0028](0028-owner-fields-are-numbers.md) | The owner fields are numbers |
| [0029](0029-a-configs-rule-locks-every-nodepool.md) | A flavor can lock every nodepool's configs as one rule (`nodepools[*].configs`), compared exactly by name, in any order |
| [0030](0030-releases-from-version-forward-only.md) | A release is a VERSION bump that only moves forward; images build on every PR and publish from main (superseded in part by 0031) |
| [0031](0031-commit-derived-versions.md) | Every merge to main is a release whose version comes from Conventional Commits, as in server-scan |
| [0032](0032-ci-supply-chain.md) | CI checks its own supply chain: zizmor-enforced SHA pins, checksum-verified tools, an npm audit that only shrinks |
| [0033](0033-delete-cluster-workflow-contract.md) | The delete-cluster workflow has a contract and a ready web panel; both say "not available yet" until it exists |
| [0034](0034-openshift-versions-from-the-upgrade-ladder.md) | A new cluster's OpenShift versions come from the upgrade ladder, per MCE; an MCE without its file offers none |
| [0035](0035-read-each-repo-once-per-commit.md) | The day1, specs and team repos are read once per commit, from GitLab's archive; a read's `last_commit_id` is the commit read at |
| [0036](0036-day1-drift-is-locked-values-and-missing-addons.md) | Day1 drift is the flavor's locked values the file does not hold, and its missing add-ons; unknown is never in sync |
| [0037](0037-import-and-sync-edit-the-cluster-file-text.md) | Existing clusters join a flavor by one MR that writes only the link and sync to it by one MR each, removals confirmed; cluster files are edited as text, checked, never round-tripped |
| [0038](0038-cluster-nodes-from-server-scan-and-the-uninstall-workflow.md) | A cluster's nodes come from its MCE by NodePool, joined to server-scan's servers; Wingman starts the platform's uninstall workflow on one and shows its run, and the procedure and its checks stay the workflow's |
| [0040](0040-create-from-a-flavor-ratio-name-and-letter-sequence.md) | A flavor may size its nodepools by a ratio; day1 suggests a new cluster's name from flavor, site and env with the next free letter; a new sequence is one letter, never a number |
