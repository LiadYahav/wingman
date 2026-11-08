# ADR-0021: The values preview is the platform's exact stack with Helm's merge and per-key provenance, held to render_chain.py by an oracle test

Date: 2026-11-07
Status: Accepted

## Context

The legacy preview merged three layers (chart, team, cluster) where the
platform merges up to ten, ignored the deploy config's `path` and
`ocp-versions/` pins, and assumed branch `main`. A preview that differs from
what ArgoCD renders is worse than none: it is the screen people decide on.

The order of the layers is defined in the platform charts
(`deploy/templates/deployApp.yaml` for workload values,
`operators/templates/operators.yaml` and `mces/templates/inClusterAppset.yaml`
for the deploy config), and the team already simulates the whole chain
offline in `tools/render-verify/render_chain.py`.

## Decision

- `wingman_day2.domain.stacks` lists each kind's layers in the templates'
  order, each with a role: hosted clusters have `team`, `team-ocp-version`,
  `site`, `site-env`, `fleet`, `fleet-env`, `fleet-target`, `mce`,
  `cluster-wide`, `cluster`; MCE hubs, UPI clusters (`upi-wide` at 8) and the
  hub (`hub`, `team`, `cluster`) have their own. The deploy config stacks are
  team default, OCP-version pin, fleet default, the cluster's folder.
- `wingman_day2.domain.merge` is Helm's merge, in Helm's two steps: the `-f`
  files with `mergeMaps` (null kept), then coalesced onto the chart's own
  `values.yaml` (null deletes). Provenance has the merged values' shape, each
  leaf the role of the layer that set it. The chart layer is the chart repo's
  `<path>/values.yaml` at the resolved `targetRevision` (ADR-0024).
- An **oracle test** runs a vendored copy of `render_chain.py`
  (gitops-day2-prod @ 979e306, public; only its CLI, `compare` and file
  output removed) with the vendored platform charts through `helm template`,
  on the fixture trees, and requires Wingman's discovery to produce the same
  leaf apps, the same value-file lists and resolved subsets, the same
  wrapper deploy-config lists, the same identity fields and OCP-version
  labels, and the same failing rules on 13 broken trees.

## Alternatives rejected

- **Hand-written expectations only.** They encode our reading of the
  templates, which is what is being tested. The oracle is the team's own
  simulation running the real templates.
- **Calling helm from the service.** An air-gapped runtime dependency and a
  subprocess per preview, to answer what a pure function answers.
- **A naive left fold for the merge.** It differs from Helm when a layer
  sets `null` and a later one sets a map again.

## Consequences

- A change to the platform charts is picked up by refreshing the vendored
  copies; a moved layer then fails the oracle instead of mislabelling values.
- The oracle needs `helm` (CI installs the pinned, checksum-verified 4.3.1 the
  chart job uses); it skips locally without helm and fails in CI.

## Verification

- `apps/day2-service/tests/oracle/test_render_chain_oracle.py` (17 tests).
  Checked to bite: moving the `site` layer below `fleet` fails it.
- `tests/unit/domain/test_merge_and_stacks.py`: the stacks per kind, Helm's
  null semantics, and hypothesis properties (provenance is truthful: every
  leaf's labelled layer holds that value; no nulls survive; an empty layer
  changes nothing).
